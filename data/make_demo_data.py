"""Generate SAMPLE data so the app runs with no accounts or downloads.

Nothing here is a real Vélib' reading. Station positions, names and bike counts
are all invented, and the app shows a banner saying so.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from common import SNAPSHOT_COLUMNS, STATION_COLUMNS, add_local_time

OUT = Path(__file__).parent / "demo"
SEED = 75
N_STATIONS = 1500
START = "2026-10-28"
DAYS = 9
# Rough course of the Seine: leaving a gap here lets the river appear in the dots.
SEINE = np.array([
    (48.800, 2.430), (48.816, 2.405), (48.829, 2.385), (48.838, 2.373), (48.846, 2.364),
    (48.853, 2.349), (48.859, 2.336), (48.864, 2.320), (48.864, 2.303), (48.858, 2.290),
    (48.850, 2.280), (48.838, 2.263), (48.829, 2.245), (48.842, 2.226), (48.870, 2.222),
    (48.892, 2.250), (48.910, 2.290), (48.930, 2.340),
])
OUTLINE = np.array([
    (48.902, 2.320), (48.901, 2.370), (48.885, 2.408), (48.860, 2.416), (48.835, 2.414), (48.818, 2.380),
    (48.816, 2.340), (48.822, 2.300), (48.833, 2.266), (48.847, 2.252), (48.866, 2.258), (48.879, 2.280),
    (48.895, 2.300),
])
AREAS = ["Bastille", "Belleville", "Montmartre", "Nation", "Montparnasse", "Opéra", "Passy",
         "Batignolles", "Gobelins", "Marais", "Vaugirard", "La Villette", "Auteuil", "Bercy"]


def river_distance(lat, lon):
    """Approximate distance in degrees from each point to the river line."""
    best = np.full(lat.shape, np.inf)
    for (a_lat, a_lon), (b_lat, b_lon) in zip(SEINE[:-1], SEINE[1:]):
        d_lat, d_lon = b_lat - a_lat, b_lon - a_lon
        t = ((lat - a_lat) * d_lat + (lon - a_lon) * d_lon) / (d_lat**2 + d_lon**2)
        t = np.clip(t, 0, 1)
        best = np.minimum(best, np.hypot(lat - (a_lat + t * d_lat), lon - (a_lon + t * d_lon)))
    return best


def inside_paris(lat, lon):
    """Ray-casting test against a rough outline of the city."""
    inside = np.zeros(lat.shape, dtype=bool)
    edges = zip(OUTLINE, np.roll(OUTLINE, -1, axis=0))
    for (a_lat, a_lon), (b_lat, b_lon) in edges:
        crosses = (a_lat > lat) != (b_lat > lat)
        with np.errstate(divide="ignore", invalid="ignore"):
            inside ^= crosses & (lon < a_lon + (lat - a_lat) * (b_lon - a_lon) / (b_lat - a_lat))
    return inside


def make_stations(rng):
    lat = rng.uniform(48.76, 48.96, 90000)
    lon = rng.uniform(2.16, 2.52, 90000)
    clear = river_distance(lat, lon) > 0.0036
    in_city = inside_paris(lat, lon)
    near = ((lat - 48.858) / 0.082) ** 2 + ((lon - 2.34) / 0.145) ** 2 < 1
    city = np.flatnonzero(in_city & clear)[:1200]
    suburbs = np.flatnonzero(~in_city & near & clear)[:N_STATIONS - 1200]
    chosen = rng.permutation(np.concatenate([city, suburbs]))
    lat, lon = lat[chosen], lon[chosen]
    ids = np.arange(100001, 100001 + N_STATIONS)
    return pd.DataFrame({
        "station_id": ids,
        "station_code": [str(i - 100000) for i in ids],
        "name": [f"Sample {AREAS[i % len(AREAS)]} {i + 1}" for i in range(N_STATIONS)],
        "lat": lat.round(6),
        "lon": lon.round(6),
        "city": "Sample city",
        "capacity": rng.integers(14, 62, N_STATIONS),
    })[STATION_COLUMNS]


def make_snapshots(stations, rng):
    slots = pd.date_range(START, periods=DAYS * 96, freq="15min", tz="Europe/Paris").tz_convert("UTC")
    local = slots.tz_convert("Europe/Paris")
    hours = np.asarray(local.hour + local.minute / 60)
    weekend = np.asarray(local.dayofweek >= 5)
    n = len(stations)
    # Central stations fill for work in the morning; outer ones empty as people leave.
    centrality = np.exp(-(((stations.lat - 48.869) / 0.022) ** 2 + ((stations.lon - 2.325) / 0.04) ** 2)).to_numpy()
    jobs = np.clip(centrality + rng.normal(0, 0.12, n), 0, 1)
    home = 1 - jobs
    base = rng.beta(3.0, 2.6, n)
    capacity = stations.capacity.to_numpy()
    fill = base.copy()
    ebike_share = rng.uniform(0.2, 0.5, n)
    frames = []
    for i, slot in enumerate(slots):
        h = hours[i]
        morning = np.exp(-((h - 9.3) / 2.7) ** 2)
        evening = np.exp(-((h - 19.2) / 2.8) ** 2)
        strength = 0.3 if weekend[i] else 1.0
        swing = strength * (jobs * 0.62 * (morning - 0.7 * evening) - home * 0.48 * (morning - 0.85 * evening))
        target = base + swing
        fill = 0.88 * fill + 0.12 * target + rng.normal(0, 0.028, n)
        fill = np.clip(fill, -0.05, 1.03)
        bikes = np.clip(np.rint(fill * capacity), 0, capacity).astype(int)
        ebike = np.minimum(bikes, rng.binomial(bikes, ebike_share))
        frames.append(pd.DataFrame({
            "slot": slot, "station_id": stations.station_id.to_numpy(), "bikes": bikes,
            "docks": capacity - bikes, "mechanical": bikes - ebike, "ebike": ebike,
            "is_renting": 1, "is_returning": 1,
        }))
    df = pd.concat(frames, ignore_index=True)
    df = df[rng.random(len(df)) > 0.004]  # Real feeds have gaps, so the sample does too.
    return add_local_time(df)[SNAPSHOT_COLUMNS]


def main():
    rng = np.random.default_rng(SEED)
    OUT.mkdir(exist_ok=True)
    stations = make_stations(rng)
    snapshots = make_snapshots(stations, rng)
    stations.to_parquet(OUT / "stations.parquet", index=False)
    snapshots.to_parquet(OUT / "snapshots.parquet", index=False)
    print(f"Sample data: {len(stations)} stations, {len(snapshots)} rows in {OUT}")


if __name__ == "__main__":
    main()
