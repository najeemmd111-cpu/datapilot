"""Predict whether a station will have no bikes 30 minutes from now."""
import json
import os
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, confusion_matrix, precision_score, recall_score

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "api"))
from features import FEATURES, add_features
from store import make_store

HORIZON = pd.Timedelta(minutes=30)
TEST_DAYS = 2
THRESHOLD = 0.5


def load() -> pd.DataFrame:
    df = make_store().query("SELECT slot, station_id, bikes, docks FROM snapshots WHERE is_renting = 1")
    slot = pd.to_datetime(df["slot"])
    df["slot"] = slot.dt.tz_localize("UTC") if slot.dt.tz is None else slot.dt.tz_convert("UTC")
    return df


def with_target(df: pd.DataFrame) -> pd.DataFrame:
    """Match the exact later time, so a gap in the data can't create a wrong label."""
    future = df[["station_id", "slot", "bikes"]].rename(columns={"bikes": "future_bikes"})
    future["slot"] = future["slot"] - HORIZON
    df = add_features(df).merge(future, on=["station_id", "slot"])
    df["target"] = (df["future_bikes"] == 0).astype(int)
    return df


def split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Train on the past, test on the future, with a gap so labels can't overlap."""
    cut = df["slot"].max() - pd.Timedelta(days=TEST_DAYS)
    return df[df["slot"] < cut - HORIZON], df[df["slot"] >= cut]


def score(y_true, y_pred, y_score) -> dict:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "pr_auc": round(float(average_precision_score(y_true, y_score)), 4),
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def log_to_mlflow(results: dict, mode: str) -> None:
    try:
        import mlflow
    except ImportError:
        print("MLflow isn't installed, so runs were saved to ml/metrics.json only.")
        return
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{(ROOT / 'ml' / 'mlflow.db').as_posix()}"))
    mlflow.set_experiment("datapilot")
    for name, metrics in results.items():
        with mlflow.start_run(run_name=name):
            mlflow.log_param("data", mode)
            mlflow.log_params({"horizon_minutes": 30, "test_days": TEST_DAYS, "threshold": THRESHOLD})
            mlflow.log_metrics({k: v for k, v in metrics.items() if k != "confusion"})
            mlflow.log_metrics({f"confusion_{k}": v for k, v in metrics["confusion"].items()})


def main() -> None:
    mode = make_store().mode
    train, test = split(with_target(load()))
    model = HistGradientBoostingClassifier(random_state=42, max_iter=150)
    model.fit(train[FEATURES], train["target"])
    probability = model.predict_proba(test[FEATURES])[:, 1]
    results = {
        "baseline_empty_stays_empty": score(test["target"], test["is_empty_now"], test["is_empty_now"]),
        "hist_gradient_boosting": score(test["target"], (probability >= THRESHOLD).astype(int), probability),
    }
    (ROOT / "ml" / "metrics.json").write_text(json.dumps({"data": mode, **results}, indent=2))
    log_to_mlflow(results, mode)
    joblib.dump({"model": model, "data": mode}, ROOT / "api" / "model.joblib")
    print(f"Data used: {mode}")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
