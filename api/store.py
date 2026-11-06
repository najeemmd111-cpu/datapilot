"""One set of queries, two engines: DuckDB on your machine, BigQuery in the cloud."""
import datetime as dt
import os
from pathlib import Path

import duckdb
import pandas as pd
import sqlglot

DATA_DIR = Path(__file__).parent.parent / "data"
MAX_BYTES = 100_000_000


class LocalStore:
    def __init__(self, folder: Path, mode: str):
        self.mode = mode
        self.db = duckdb.connect(":memory:")
        for table in ("snapshots", "stations"):
            df = pd.read_parquet(folder / f"{table}.parquet")
            if "slot" in df:
                df["slot"] = df["slot"].dt.tz_convert("UTC").dt.tz_localize(None)
            self.db.register("incoming", df)
            self.db.execute(f"CREATE TABLE {table} AS SELECT * FROM incoming")
            self.db.unregister("incoming")
        # Files and network stay closed to every query, including the agent's.
        self.db.execute("SET enable_external_access = false")
        self.db.execute("SET lock_configuration = true")

    def query(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        params = {k: _naive(v) for k, v in (params or {}).items()}
        text = sql.replace("@", "$")
        return self.db.cursor().execute(text, params).fetchdf()

    def run_agent_sql(self, sql: str) -> pd.DataFrame:
        return self.db.cursor().execute(sqlglot.transpile(sql, read="bigquery", write="duckdb")[0]).fetchdf()


class BigQueryStore:
    mode = "bigquery"

    def __init__(self):
        from google.cloud import bigquery

        self.bq = bigquery
        self.client = bigquery.Client()
        self.dataset = bigquery.DatasetReference(self.client.project, os.getenv("BQ_DATASET", "datapilot"))

    def _config(self, params=None):
        types = {int: "INT64", dt.datetime: "TIMESTAMP", dt.date: "DATE", str: "STRING"}
        items = (params or {}).items()
        return self.bq.QueryJobConfig(
            default_dataset=self.dataset,
            maximum_bytes_billed=MAX_BYTES,
            query_parameters=[self.bq.ScalarQueryParameter(k, types[type(v)], v) for k, v in items],
        )

    def query(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        return self.client.query(sql, job_config=self._config(params)).to_dataframe()

    def run_agent_sql(self, sql: str) -> pd.DataFrame:
        return self.query(sql)


def _naive(value):
    if isinstance(value, dt.datetime) and value.tzinfo:
        return value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value


def as_utc(series: pd.Series) -> pd.Series:
    series = pd.to_datetime(series)
    return series.dt.tz_localize("UTC") if series.dt.tz is None else series.dt.tz_convert("UTC")


def make_store():
    backend = os.getenv("DATA_BACKEND", "auto")
    if backend == "bigquery":
        return BigQueryStore()
    if backend in ("auto", "local") and (DATA_DIR / "local" / "snapshots.parquet").exists():
        return LocalStore(DATA_DIR / "local", "real")
    if backend == "local":
        raise RuntimeError("No real data found. Run: python data/ingest.py --local")
    return LocalStore(DATA_DIR / "demo", "sample")
