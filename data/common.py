"""Shared table shape for sample and real data."""
import pandas as pd

PARIS = "Europe/Paris"
SLOT_MINUTES = 15
SNAPSHOT_COLUMNS = [
    "slot", "local_date", "local_hour", "is_weekend", "station_id",
    "bikes", "docks", "mechanical", "ebike", "is_renting", "is_returning",
]
STATION_COLUMNS = ["station_id", "station_code", "name", "lat", "lon", "city", "capacity"]


def add_local_time(df: pd.DataFrame) -> pd.DataFrame:
    """Paris-time columns let SQL group by hour without time zone functions."""
    local = df["slot"].dt.tz_convert(PARIS)
    df["local_date"] = local.dt.date
    df["local_hour"] = local.dt.hour
    df["is_weekend"] = (local.dt.dayofweek >= 5).astype(int)
    return df


def thin_to_slots(raw: pd.DataFrame) -> pd.DataFrame:
    """Keep the last reading of each station in each 15-minute slot."""
    df = raw.copy()
    df["ts"] = pd.to_datetime(df["src_ts"], unit="s", utc=True)
    df["slot"] = df["ts"].dt.floor(f"{SLOT_MINUTES}min")
    df = df.sort_values("ts").groupby(["station_id", "slot"], as_index=False).tail(1)
    df = add_local_time(df)
    return df[SNAPSHOT_COLUMNS].reset_index(drop=True)
