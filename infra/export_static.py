"""Export the files for the static GitHub Pages demo into web/public/data.

Run from the project root after `python run.py --real`:
    .venv/bin/python infra/export_static.py

It needs api/model.joblib and api/eval_runs/google_genai_gemini-3.5-flash.json.
No keys or LLM calls are used: saved answers come from SQL that Gemini wrote earlier.
"""
import json
import shutil
import sys
from pathlib import Path

import joblib
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
import queries
from features import FEATURES, add_features
from guard import check_sql
from store import as_utc, make_store

OUT = ROOT / "web" / "public" / "data"
SAVED_SQL = ROOT / "api" / "eval_runs" / "google_genai_gemini-3.5-flash.json"
MODEL_NAME = "Gemini 3.5 Flash"


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, separators=(",", ":"), default=str), encoding="utf-8")


def risk_table(store, bundle) -> pd.DataFrame:
    """Chance of no bikes in 30 minutes for every station and slot, as a whole percent."""
    df = store.query("SELECT slot, station_id, bikes, docks FROM snapshots")
    df["slot"] = as_utc(df["slot"])
    df = add_features(df)
    df["risk"] = (bundle["model"].predict_proba(df[FEATURES])[:, 1] * 100).round().astype(int)
    return df[["slot", "station_id", "risk"]]


def label(key: str) -> str:
    return "result" if "(" in key or key.startswith("f0_") else key.replace("_", " ")


def show(value) -> str:
    if isinstance(value, float):
        return f"{value:,.1f}".removesuffix(".0")
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)[:10] if str(value)[:4].isdigit() and "T" in str(value) else str(value)


def summary(rows: list[dict]) -> str:
    """A plain sentence from the real query result. No LLM writes it in the static demo."""
    if not rows:
        return "The query found no rows."
    first = {k: v for k, v in rows[0].items() if k != "station_id"}
    text = ", ".join(show(v) if k == "name" else f"{label(k)} {show(v)}" for k, v in first.items())
    if len(rows) == 1:
        return text[0].upper() + text[1:] + "."
    return f"Top result: {text}. The query returned {len(rows)} rows."


def saved_answers(store) -> list[dict]:
    if not SAVED_SQL.exists():
        print("No saved Gemini SQL found, so Ask the city will have no examples.")
        return []
    answers = []
    for item in json.loads(SAVED_SQL.read_text()):
        if not item.get("sql"):
            continue
        df = store.run_agent_sql(check_sql(item["sql"]))
        rows = json.loads(df.head(20).to_json(orient="records", date_format="iso"))
        answers.append({
            "question": item["q"], "model": MODEL_NAME, "answer": summary(rows), "sql": item["sql"], "rows": rows,
            "station_ids": [r["station_id"] for r in rows if "station_id" in r], "uses_llm": True, "saved": True,
        })
    return answers


def main() -> None:
    store = make_store()
    if store.mode != "real":
        raise SystemExit("Run `python3 run.py --real` first, so the demo uses real data.")
    bundle = joblib.load(ROOT / "api" / "model.joblib")
    shutil.rmtree(OUT, ignore_errors=True)

    days = queries.days(store)
    write(OUT / "meta.json", {"mode": "real", "days": days, "llm": None, "staticDemo": True})
    stations = queries.stations(store)
    write(OUT / "stations.json", {
        "as_of": stations.attrs["as_of"].isoformat(),
        "stations": stations.astype(object).where(stations.notna(), None).to_dict("records"),
    })

    risks = risk_table(store, bundle)
    for day in days:
        replay = queries.replay(store, pd.Timestamp(day).date())
        slots = pd.to_datetime(replay["slots"], utc=True)
        grid = (risks[risks["slot"].isin(slots)]
                .pivot_table(index="slot", columns="station_id", values="risk", aggfunc="last")
                .reindex(index=slots, columns=replay["station_ids"]))
        replay["risk"] = [[None if pd.isna(v) else int(v) for v in row] for row in grid.to_numpy().tolist()]
        write(OUT / "replay" / f"{day}.json", replay)

    answers = saved_answers(store)
    write(OUT / "answers.json", answers)
    size = sum(f.stat().st_size for f in OUT.rglob("*.json")) / 1e6
    print(f"Exported {len(days)} days, {len(stations)} stations and {len(answers)} saved answers ({size:.1f} MB) to {OUT}")


if __name__ == "__main__":
    main()
