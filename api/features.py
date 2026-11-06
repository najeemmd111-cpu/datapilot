"""Features shared by training and the API, so the two cannot drift apart."""
import pandas as pd

FEATURES = [
    "bikes", "docks", "fill_ratio", "is_empty_now", "delta_15", "delta_60",
    "hour", "day_of_week", "is_weekend",
]


def _lagged_bikes(df: pd.DataFrame, minutes: int) -> pd.Series:
    """Bikes at exactly `minutes` earlier. Missing slots stay empty instead of shifting."""
    past = df[["station_id", "slot", "bikes"]].copy()
    past["slot"] = past["slot"] + pd.Timedelta(minutes=minutes)
    merged = df[["station_id", "slot"]].merge(past, on=["station_id", "slot"], how="left")
    return pd.Series(merged["bikes"].to_numpy(), index=df.index, dtype="float64")


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["station_id", "slot"]).reset_index(drop=True)
    local = df["slot"].dt.tz_convert("Europe/Paris")
    df["hour"] = local.dt.hour
    df["day_of_week"] = local.dt.dayofweek
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["fill_ratio"] = df["bikes"] / (df["bikes"] + df["docks"]).clip(lower=1)
    df["is_empty_now"] = (df["bikes"] == 0).astype(int)
    df["delta_15"] = df["bikes"] - _lagged_bikes(df, 15)
    df["delta_60"] = df["bikes"] - _lagged_bikes(df, 60)
    return df
