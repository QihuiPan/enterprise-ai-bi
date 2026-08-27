from __future__ import annotations

import math
from datetime import timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, mean_squared_log_error

FEATURE_COLUMNS = [
    "series_code",
    "state_code",
    "store_code",
    "category_code",
    "day_number",
    "day_of_week",
    "month",
    "year",
    "wm_yr_wk",
    "event_flag",
    "snap",
    "lag_1",
    "lag_7",
    "lag_28",
    "rolling_mean_7",
    "rolling_mean_28",
]


def build_m5_features(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "series_id",
        "order_date",
        "state_id",
        "store_id",
        "category",
        "quantity",
        "day_number",
        "wm_yr_wk",
        "event_flag",
        "snap",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Prepared M5 data is missing columns: {', '.join(missing)}.")

    data = frame.copy()
    data["order_date"] = pd.to_datetime(data["order_date"], errors="raise")
    data = data.sort_values(["series_id", "order_date"]).reset_index(drop=True)
    for source, target in (
        ("series_id", "series_code"),
        ("state_id", "state_code"),
        ("store_id", "store_code"),
        ("category", "category_code"),
    ):
        values = sorted(data[source].astype(str).unique())
        mapping = {value: index for index, value in enumerate(values)}
        data[target] = data[source].astype(str).map(mapping).astype("int16")

    data["day_of_week"] = data["order_date"].dt.dayofweek.astype("int8")
    data["month"] = data["order_date"].dt.month.astype("int8")
    data["year"] = data["order_date"].dt.year.astype("int16")
    grouped = data.groupby("series_id", sort=False)["quantity"]
    for lag in (1, 7, 28):
        data[f"lag_{lag}"] = grouped.shift(lag)
    shifted = grouped.shift(1)
    data["rolling_mean_7"] = shifted.groupby(data["series_id"]).transform(
        lambda values: values.rolling(7, min_periods=7).mean()
    )
    data["rolling_mean_28"] = shifted.groupby(data["series_id"]).transform(
        lambda values: values.rolling(28, min_periods=28).mean()
    )
    return data


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    actual = np.asarray(actual, dtype="float64")
    predicted = np.maximum(0, np.asarray(predicted, dtype="float64"))
    denominator = float(np.abs(actual).sum())
    return {
        "mae": round(float(mean_absolute_error(actual, predicted)), 4),
        "rmse": round(float(math.sqrt(mean_squared_error(actual, predicted))), 4),
        "rmsle": round(
            float(math.sqrt(mean_squared_log_error(actual, predicted))), 4
        ),
        "wmape": round(float(np.abs(actual - predicted).sum() / denominator), 6)
        if denominator
        else 0.0,
    }


def train_m5_model(
    frame: pd.DataFrame,
    *,
    horizon: int = 28,
    random_state: int = 42,
) -> tuple[dict, dict, pd.DataFrame]:
    if not 7 <= horizon <= 56:
        raise ValueError("M5 holdout horizon must be between 7 and 56 days.")
    features = build_m5_features(frame).dropna(subset=FEATURE_COLUMNS).copy()
    if features.empty:
        raise ValueError("Prepared M5 data does not contain enough history for 28-day lags.")

    latest_date = features["order_date"].max()
    cutoff = latest_date - timedelta(days=horizon - 1)
    training = features[features["order_date"] < cutoff]
    holdout = features[features["order_date"] >= cutoff]
    if training.empty or holdout.empty:
        raise ValueError("Prepared M5 data cannot produce a non-empty train/holdout split.")

    model = HistGradientBoostingRegressor(
        learning_rate=0.06,
        max_iter=250,
        max_leaf_nodes=31,
        l2_regularization=0.1,
        random_state=random_state,
    )
    model.fit(training[FEATURE_COLUMNS], np.log1p(training["quantity"]))
    predicted = np.expm1(model.predict(holdout[FEATURE_COLUMNS]))
    predicted = np.maximum(0, predicted)
    baseline = np.maximum(0, holdout["lag_28"].to_numpy(dtype="float64"))
    actual = holdout["quantity"].to_numpy(dtype="float64")

    metrics = {
        "model": "hist_gradient_boosting_global_store_category",
        "target": "daily_unit_sales",
        "evaluation_scope": "store-category temporal holdout; not official WRMSSE",
        "feature_count": len(FEATURE_COLUMNS),
        "training_rows": int(len(training)),
        "holdout_rows": int(len(holdout)),
        "series": int(features["series_id"].nunique()),
        "train_start": training["order_date"].min().date().isoformat(),
        "train_end": training["order_date"].max().date().isoformat(),
        "holdout_start": holdout["order_date"].min().date().isoformat(),
        "holdout_end": holdout["order_date"].max().date().isoformat(),
        "model_metrics": _metrics(actual, predicted),
        "seasonal_naive_lag_28_metrics": _metrics(actual, baseline),
    }
    predictions = holdout[
        ["series_id", "order_date", "state_id", "store_id", "category", "quantity"]
    ].copy()
    predictions = predictions.rename(columns={"quantity": "actual_units"})
    predictions["predicted_units"] = np.round(predicted, 4)
    predictions["seasonal_naive_units"] = np.round(baseline, 4)
    artifact = {
        "model": model,
        "features": FEATURE_COLUMNS,
        "target_transform": "log1p",
        "metrics": metrics,
    }
    return artifact, metrics, predictions


def save_m5_model(artifact: dict, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, destination)
    return destination
