"""Compare LLMs on eval_questions.json by matching query results, not SQL text.

Run from /api, for example:
LLM_MODELS="openai:gpt-5,anthropic:claude-sonnet-5-5" python eval_llm.py
"""
import json
import os
import statistics
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import agent
from guard import check_sql
from store import make_store

QUESTIONS = json.loads((Path(__file__).parent / "eval_questions.json").read_text())


def values(df):
    """Compare result values only, because column names vary between correct queries."""
    return sorted(tuple(str(v) for v in row) for row in df.values.tolist())


def evaluate(store, planner) -> dict:
    correct, seconds = 0, []
    for item in QUESTIONS:
        started = time.perf_counter()
        expected = values(store.run_agent_sql(check_sql(item["sql"])))
        try:
            sql = planner(item["q"], None)
            correct += sql is not None and values(store.run_agent_sql(check_sql(sql))) == expected
        except Exception as error:
            print("  failed:", item["q"], "-", str(error)[:120])
        seconds.append(time.perf_counter() - started)
    return {"correct": correct, "total": len(QUESTIONS), "median_seconds": round(statistics.median(seconds), 2)}


def main() -> None:
    store = make_store()
    names = [n.strip() for n in os.getenv("LLM_MODELS", "").split(",") if n.strip()]
    if not names:
        raise SystemExit("Set LLM_MODELS, for example LLM_MODELS=openai:gpt-5,anthropic:claude-sonnet-5-5")
    print("| Model | Correct | Median seconds |\n| --- | --- | --- |")
    for name in names:
        result = evaluate(store, agent.llm_tools(name, agent.data_note(store))[0])
        print(f"| {name} | {result['correct']}/{result['total']} | {result['median_seconds']} |")


if __name__ == "__main__":
    main()
