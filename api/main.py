import datetime as dt
import os
import time
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).parent.parent / ".env")

import agent as agent_module
import queries
from features import FEATURES
from store import make_store

API_DIR = Path(__file__).parent
STATIC_DIR = API_DIR / "static"
ASK_PER_HOUR = int(os.getenv("ASK_PER_HOUR", "10"))
ASK_PER_DAY = int(os.getenv("ASK_PER_DAY", "200"))

app = FastAPI(title="DataPilot")
hits: dict[str, deque] = defaultdict(deque)
daily_hits: deque = deque()


@lru_cache
def get_store():
    return make_store()


@lru_cache
def get_model():
    return joblib.load(API_DIR / "model.joblib")


@lru_cache
def get_agent():
    model_name = os.getenv("LLM_MODEL")
    note = agent_module.data_note(get_store()) if model_name else ""
    tools = agent_module.llm_tools(model_name, note) if model_name else (agent_module.demo_planner, agent_module.demo_writer)
    return agent_module.build_agent(get_store(), *tools)


class Cache:
    """Short cache so repeated page loads don't repeat the same BigQuery query."""

    def __init__(self, seconds: int):
        self.seconds, self.items = seconds, {}

    def get(self, key, make):
        now = time.monotonic()
        if key not in self.items or now - self.items[key][0] > self.seconds:
            self.items[key] = (now, make())
        return self.items[key][1]


cache = Cache(60)


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=300)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/meta")
def meta(store=Depends(get_store)):
    return cache.get("meta", lambda: {
        "mode": store.mode,
        "days": queries.days(store),
        "llm": os.getenv("LLM_MODEL") or None,
    })


@app.get("/api/stations")
def stations(store=Depends(get_store)):
    def load():
        df = queries.stations(store)
        rows = df.astype(object).where(df.notna(), None).to_dict("records")
        return {"as_of": df.attrs["as_of"].isoformat(), "stations": rows}
    return cache.get("stations", load)


@app.get("/api/replay")
def replay(date: dt.date, store=Depends(get_store)):
    result = cache.get(("replay", date), lambda: queries.replay(store, date))
    if not result:
        raise HTTPException(404, "There is no data for that day.")
    return result


@app.get("/api/predict")
def predict(station_id: int, slot: dt.datetime | None = None, store=Depends(get_store), bundle=Depends(get_model)):
    when = slot or queries.latest_slot(store)
    if when.tzinfo is None:
        raise HTTPException(422, "The slot must include a time zone.")
    row = queries.prediction_rows(store, station_id, when)
    if row.empty or row["slot"].iloc[0] != pd.Timestamp(when).tz_convert("UTC").floor("15min"):
        raise HTTPException(404, "This station has no reading at that time.")
    probability = float(bundle["model"].predict_proba(row[FEATURES])[0, 1])
    return {
        "station_id": station_id,
        "as_of": row["slot"].iloc[0].isoformat(),
        "bikes": int(row["bikes"].iloc[0]),
        "empty_in_30_min": round(probability, 4),
    }


def limit_requests(request: Request) -> None:
    forwarded = request.headers.get("x-forwarded-for", "")
    # Cloud Run adds the real address last, so earlier values can't dodge the limit.
    ip = forwarded.split(",")[-1].strip() or (request.client.host if request.client else "unknown")
    now = time.time()
    mine = hits[ip]
    while mine and now - mine[0] > 3600:
        mine.popleft()
    while daily_hits and now - daily_hits[0] > 86400:
        daily_hits.popleft()
    if len(mine) >= ASK_PER_HOUR or len(daily_hits) >= ASK_PER_DAY:
        raise HTTPException(429, "Too many questions right now. Try again later.")
    mine.append(now)
    daily_hits.append(now)


@app.post("/api/ask", dependencies=[Depends(limit_requests)])
def ask(body: Ask, graph=Depends(get_agent)):
    config, flush = agent_module.tracing_config()
    result = graph.invoke({"question": body.question}, config=config)
    flush()
    rows = result.get("rows") or []
    return {
        "answer": result["answer"],
        "sql": result.get("sql"),
        "rows": rows[:20],
        "station_ids": [r["station_id"] for r in rows if "station_id" in r],
        "uses_llm": bool(os.getenv("LLM_MODEL")),
    }


@app.get("/api/{rest:path}", include_in_schema=False)
def unknown_api(rest: str):
    raise HTTPException(404, "Unknown API route.")


@app.get("/{path:path}", include_in_schema=False)
def web_app(path: str):
    target = (STATIC_DIR / path).resolve()
    if path and target.is_file() and target.is_relative_to(STATIC_DIR.resolve()):
        return FileResponse(target)
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(404, "The web app isn't built yet. Run: python run.py")
    return FileResponse(index)
