"""Load real Vélib' history from the public dataset.

python data/ingest.py --local      saves Parquet files in data/local
python data/ingest.py --bigquery   loads the datapilot dataset in BigQuery

Data: "Vélib' Métropole station status, every minute (unofficial)", Angelo Saadeh,
https://huggingface.co/datasets/angelosaadeh/velib, from Vélib' Métropole (GBFS) and
the Base Adresse Nationale, Licence Ouverte 2.0.
"""
import argparse
import os
from pathlib import Path

import pandas as pd

from common import STATION_COLUMNS, thin_to_slots

BASE = "hf://datasets/angelosaadeh/velib"
OUT = Path(__file__).parent / "local"


def load_days(days: int) -> pd.DataFrame:
    today = pd.Timestamp.now(tz="Europe/Paris").normalize().tz_localize(None)
    frames = []
    for day in pd.date_range(end=today - pd.Timedelta(days=1), periods=days):
        name = day.strftime("%Y-%m-%d")
        try:
            frames.append(thin_to_slots(pd.read_parquet(f"{BASE}/snapshots/{name}.parquet")))
            print("Loaded", name)
        except FileNotFoundError:
            print("Not published yet:", name)
    if not frames:
        raise SystemExit("No days could be downloaded.")
    return pd.concat(frames, ignore_index=True)


def load_stations() -> pd.DataFrame:
    stations = pd.read_csv(f"{BASE}/stations.csv", dtype={"station_code": str, "postal_code": str})
    return stations.rename(columns={"capacity_official": "capacity"})[STATION_COLUMNS]


def to_bigquery(snapshots: pd.DataFrame, stations: pd.DataFrame) -> None:
    from google.cloud import bigquery

    dataset = os.getenv("BQ_DATASET", "datapilot")
    client = bigquery.Client()
    partitioned = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        time_partitioning=bigquery.TimePartitioning(field="slot"),
    )
    plain = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    client.load_table_from_dataframe(snapshots, f"{dataset}.snapshots", job_config=partitioned).result()
    client.load_table_from_dataframe(stations, f"{dataset}.stations", job_config=plain).result()


def main() -> None:
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--local", action="store_true")
    target.add_argument("--bigquery", action="store_true")
    parser.add_argument("--days", type=int, default=9)
    args = parser.parse_args()
    snapshots = load_days(args.days)
    stations = load_stations()
    if args.local:
        OUT.mkdir(exist_ok=True)
        snapshots.to_parquet(OUT / "snapshots.parquet", index=False)
        stations.to_parquet(OUT / "stations.parquet", index=False)
    else:
        to_bigquery(snapshots, stations)
    print(f"Saved {len(snapshots)} rows and {len(stations)} stations.")


if __name__ == "__main__":
    main()
