"""SQL used by the API. It runs unchanged on BigQuery and DuckDB."""
import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd

from features import add_features
from store import as_utc

PARIS = ZoneInfo("Europe/Paris")


def days(store) -> list[str]:
    df = store.query("SELECT DISTINCT local_date FROM snapshots ORDER BY local_date")
    return [str(d)[:10] for d in df["local_date"]]


def latest_slot(store) -> dt.datetime:
    value = store.query("SELECT MAX(slot) AS slot FROM snapshots")["slot"].iloc[0]
    return as_utc(pd.Series([value])).iloc[0].to_pydatetime()


def stations(store) -> pd.DataFrame:
    slot = latest_slot(store)
    df = store.query(
        """
        SELECT s.station_id, s.name, s.lat, s.lon, s.capacity, r.bikes, r.docks
        FROM stations AS s
        LEFT JOIN snapshots AS r ON r.station_id = s.station_id AND r.slot = @slot
        WHERE s.lat IS NOT NULL AND s.lon IS NOT NULL
        ORDER BY s.station_id
        """,
        {"slot": slot},
    )
    df.attrs["as_of"] = slot
    return df


def replay(store, day: dt.date) -> dict:
    """All stations for one Paris day, packed so the browser can animate it smoothly."""
    start = dt.datetime.combine(day, dt.time(), PARIS)
    end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(), PARIS)
    df = store.query(
        """
        SELECT slot, station_id, bikes FROM snapshots
        WHERE slot >= @start_at AND slot < @end_at
        """,
        {"start_at": start, "end_at": end},
    )
    if df.empty:
        return {}
    df["slot"] = as_utc(df["slot"])
    grid = df.pivot_table(index="slot", columns="station_id", values="bikes", aggfunc="last").sort_index()
    values = grid.astype(object).where(grid.notna(), None).to_numpy().tolist()
    return {
        "date": day.isoformat(),
        "slots": [s.isoformat() for s in grid.index],
        "station_ids": [int(i) for i in grid.columns],
        "bikes": [[None if v is None else int(v) for v in row] for row in values],
    }


def prediction_rows(store, station_id: int, slot: dt.datetime) -> pd.DataFrame:
    df = store.query(
        """
        SELECT slot, station_id, bikes, docks FROM snapshots
        WHERE station_id = @station_id AND slot >= @first_slot AND slot <= @last_slot
        ORDER BY slot
        """,
        {"station_id": station_id, "first_slot": slot - dt.timedelta(minutes=75), "last_slot": slot},
    )
    if df.empty:
        return df
    df["slot"] = as_utc(df["slot"])
    return add_features(df).tail(1)
