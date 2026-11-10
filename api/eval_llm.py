"""Compare LLMs on eval_questions.json by matching query results, not SQL text.

Run from /api, for example:
LLM_MODELS=google_genai:gemini-3.5-flash python eval_llm.py

Each model's SQL is saved in eval_runs/, so you can re-score without using more
requests. Add --fresh to ask the model again.
"""
import json
import os
import statistics
import sys
import time
import warnings
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
warnings.filterwarnings("ignore", message=".*fixed sampling defaults.*")

import agent
from guard import check_sql
from store import make_store

HERE = Path(__file__).parent
QUESTIONS = json.loads((HERE / "eval_questions.json").read_text())
RUNS = HERE / "eval_runs"


def columns(df) -> list[list[str]]:
    """Each column as sorted values. Numbers are rounded so 12.34 and 12.3 match."""
    def clean(value):
        if isinstance(value, float):
            # DuckDB returns COUNT_IF as a float, so 3.0 must match 3.
            value = round(value, 1)
            return str(int(value)) if value.is_integer() else f"{value:.1f}"
        if hasattr(value, "item"):
            return clean(value.item())
        return str(value)[:10] if hasattr(value, "isoformat") else str(value)
    return [sorted(clean(v) for v in df[c].tolist()) for c in df.columns]


def matches(expected, actual) -> bool:
    """Correct when the row count matches and every expected column appears in the answer.

    Extra columns, such as station_id or a count beside a station name, are allowed.
    """
    if len(expected.index) != len(actual.index):
        return False
    found = columns(actual)
    return all(column in found for column in columns(expected))


def generate(planner, name: str, fresh: bool) -> list[dict]:
    path = RUNS / f"{name.replace(':', '_')}.json"
    if path.exists() and not fresh:
        print(f"Re-scoring saved SQL from {path.name}. Add --fresh to ask the model again.")
        return json.loads(path.read_text())
    pause = float(os.getenv("EVAL_PAUSE_SECONDS", "15"))
    answers = []
    for item in QUESTIONS:
        started = time.perf_counter()
        try:
            sql, error = planner(item["q"], None), None
        except Exception as failure:
            sql, error = None, str(failure)[:200]
            print("  model error:", item["q"], "-", error[:120])
        answers.append({"q": item["q"], "sql": sql, "error": error, "seconds": round(time.perf_counter() - started, 2)})
        time.sleep(pause)  # Stays under free-tier per-minute limits.
    if any(a["error"] and ("429" in a["error"] or "RESOURCE_EXHAUSTED" in a["error"]) for a in answers):
        print("  Hit the free limit, so these results weren't saved. Try again after the daily reset.")
    else:
        RUNS.mkdir(exist_ok=True)
        path.write_text(json.dumps(answers, indent=2))
    return answers


def score(store, answers: list[dict]) -> dict:
    correct = 0
    for item, answer in zip(QUESTIONS, answers):
        expected = store.run_agent_sql(check_sql(item["sql"]))
        try:
            ok = answer["sql"] is not None and matches(expected, store.run_agent_sql(check_sql(answer["sql"])))
        except Exception as failure:
            ok = False
            answer["error"] = answer["error"] or str(failure)[:120]
        correct += ok
        if not ok:
            print(f"  wrong: {item['q']}\n    SQL: {answer['sql']}")
            if answer["error"]:
                print(f"    Error: {answer['error']}")
    seconds = [a["seconds"] for a in answers if not a["error"] or "429" not in a["error"]]
    return {"correct": correct, "total": len(QUESTIONS), "median_seconds": round(statistics.median(seconds or [0]), 2)}


def main() -> None:
    store = make_store()
    fresh = "--fresh" in sys.argv
    names = [n.strip() for n in os.getenv("LLM_MODELS", "").split(",") if n.strip()]
    if not names:
        raise SystemExit("Set LLM_MODELS, for example LLM_MODELS=google_genai:gemini-3.5-flash")
    rows = []
    for name in names:
        planner = agent.llm_tools(name, agent.data_note(store))[0]
        result = score(store, generate(planner, name, fresh))
        rows.append(f"| {name} | {result['correct']}/{result['total']} | {result['median_seconds']} |")
    print("\n| Model | Correct | Median seconds |\n| --- | --- | --- |")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
