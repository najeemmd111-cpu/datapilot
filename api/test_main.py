import pathlib
import sys

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "data"))
from common import thin_to_slots

import agent
import main
from features import add_features
from store import LocalStore


@pytest.fixture(autouse=True)
def reset_limits():
    main.hits.clear()
    main.daily_hits.clear()
    main.cache.items.clear()


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    """Tests use a tiny fake dataset and need no cloud access."""
    folder = tmp_path_factory.mktemp("data")
    slots = pd.date_range("2026-11-02 08:00", periods=8, freq="15min", tz="UTC")
    rows = [{"src_ts": int(s.timestamp()), "station_id": i, "bikes": max(0, 6 - j) * (i - 1),
             "docks": 10, "mechanical": 1, "ebike": 0, "is_renting": 1, "is_returning": 1}
            for j, s in enumerate(slots) for i in (1, 2)]
    thin_to_slots(pd.DataFrame(rows)).to_parquet(folder / "snapshots.parquet")
    pd.DataFrame({"station_id": [1, 2], "station_code": ["1", "2"], "name": ["Quiet", "Busy"], "lat": [48.8, 48.9],
                  "lon": [2.3, 2.4], "city": ["Paris", "Paris"], "capacity": [20, 30]}).to_parquet(folder / "stations.parquet")
    store = LocalStore(folder, "sample")

    class Half:
        def predict_proba(self, x):
            return np.array([[0.25, 0.75]] * len(x))

    main.app.dependency_overrides[main.get_store] = lambda: store
    main.app.dependency_overrides[main.get_model] = lambda: {"model": Half()}
    main.app.dependency_overrides[main.get_agent] = lambda: agent.build_agent(store, agent.demo_planner, agent.demo_writer)
    client = TestClient(main.app)
    client.store = store
    return client


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_meta_and_stations(client):
    assert client.get("/api/meta").json()["mode"] == "sample"
    body = client.get("/api/stations").json()
    assert len(body["stations"]) == 2 and body["as_of"].startswith("2026-11-02T09:45")


def test_replay_packs_a_day(client):
    body = client.get("/api/replay", params={"date": "2026-11-02"}).json()
    assert len(body["slots"]) == 8 and body["station_ids"] == [1, 2] and body["bikes"][0] == [0, 6]
    assert client.get("/api/replay", params={"date": "2020-01-01"}).status_code == 404


def test_predict_is_a_probability(client):
    body = client.get("/api/predict", params={"station_id": 2}).json()
    assert 0 <= body["empty_in_30_min"] <= 1


def test_unknown_station_returns_404(client):
    assert client.get("/api/predict", params={"station_id": 999}).status_code == 404


def test_ask_returns_answer_sql_and_stations(client):
    body = client.post("/api/ask", json={"question": "Which stations are empty most often?"}).json()
    assert body["sql"].startswith("SELECT") and body["station_ids"][0] == 1 and "Quiet" in body["answer"]


def test_ask_declines_what_it_cannot_answer(client):
    body = client.post("/api/ask", json={"question": "What is the weather like?"}).json()
    assert body["sql"] is None and "can't answer" in body["answer"]


def test_ask_is_rate_limited(client):
    for _ in range(main.ASK_PER_HOUR):
        client.post("/api/ask", json={"question": "How many bikes?"})
    assert client.post("/api/ask", json={"question": "How many bikes?"}).status_code == 429


def test_agent_retries_then_blocks_a_write(client):
    calls = []

    def bad_planner(question, error):
        calls.append(error)
        return "DROP TABLE stations"

    graph = agent.build_agent(client.store, bad_planner, agent.demo_writer)
    result = graph.invoke({"question": "delete everything"})
    assert len(calls) == agent.MAX_ATTEMPTS and "couldn't run a safe query" in result["answer"]
    assert len(client.store.query("SELECT * FROM stations")) == 2


def test_agent_fixes_a_failed_query(client):
    replies = iter(["SELECT missing FROM stations", "SELECT COUNT(*) AS bikes FROM stations"])
    graph = agent.build_agent(client.store, lambda q, e: next(replies), agent.demo_writer)
    assert graph.invoke({"question": "count"})["rows"] == [{"bikes": 2}]


def test_queries_cannot_read_files(client):
    with pytest.raises(Exception):
        client.store.query("SELECT * FROM read_csv('/etc/passwd')")


def test_lag_features_respect_gaps():
    slots = pd.to_datetime(["2026-11-02 08:00", "2026-11-02 08:15", "2026-11-02 09:00"], utc=True)
    df = add_features(pd.DataFrame({"slot": slots, "station_id": 1, "bikes": [1, 3, 9], "docks": 1}))
    assert df["delta_15"].iloc[1] == 2 and pd.isna(df["delta_15"].iloc[2])


def test_web_routes_fall_back_but_api_does_not(client, tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<app-root>")
    monkeypatch.setattr(main, "STATIC_DIR", tmp_path)
    assert "app-root" in client.get("/chat").text
    assert client.get("/api/nope").status_code == 404




def test_day_of_week_matches_bigquery(client):
    # 2026-11-01 was a Sunday, which BigQuery numbers as 1.
    sql = "SELECT EXTRACT(DAYOFWEEK FROM DATE '2026-11-01') AS sunday, EXTRACT(DAYOFWEEK FROM DATE '2026-11-07') AS saturday"
    assert client.store.run_agent_sql(sql).iloc[0].tolist() == [1, 7]


def test_llm_quota_error_returns_429(client):
    def out_of_quota(question, error):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    normal = main.app.dependency_overrides[main.get_agent]
    main.app.dependency_overrides[main.get_agent] = lambda: agent.build_agent(client.store, out_of_quota, agent.demo_writer)
    try:
        response = client.post("/api/ask", json={"question": "How many bikes?"})
    finally:
        main.app.dependency_overrides[main.get_agent] = normal
    assert response.status_code == 429
