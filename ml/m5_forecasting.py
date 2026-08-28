from __future__ import annotations

import math
from datetime import timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, mean_squared_log_error

LEGACY_FEATURE_COLUMNS = [
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
    "dow_sin",
    "dow_cos",
    "year_sin",
    "year_cos",
    "lag_1",
    "lag_7",
    "lag_14",
    "lag_28",
    "lag_56",
    "rolling_mean_7",
    "rolling_mean_14",
    "rolling_mean_28",
    "rolling_mean_56",
    "rolling_std_7",
    "rolling_std_28",
    "price_lag_1",
    "price_lag_7",
]

BLEND_SOURCE_NAMES = ("model", "lag_7", "lag_28", "lag_56")


def build_m5_features(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "series_id",
        "order_date",
        "state_id",
        "store_id",
        "category",
        "quantity",
        "unit_price",
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
    day_of_year = data["order_date"].dt.dayofyear
    data["dow_sin"] = np.sin(2 * np.pi * data["day_of_week"] / 7)
    data["dow_cos"] = np.cos(2 * np.pi * data["day_of_week"] / 7)
    data["year_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    data["year_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)

    grouped = data.groupby("series_id", sort=False)["quantity"]
    for lag in (1, 7, 14, 28, 56):
        data[f"lag_{lag}"] = grouped.shift(lag)
    shifted = grouped.shift(1)
    for window in (7, 14, 28, 56):
        data[f"rolling_mean_{window}"] = shifted.groupby(
            data["series_id"]
        ).transform(
            lambda values, window=window: values.rolling(
                window, min_periods=window
            ).mean()
        )
    for window in (7, 28):
        data[f"rolling_std_{window}"] = shifted.groupby(
            data["series_id"]
        ).transform(
            lambda values, window=window: values.rolling(
                window, min_periods=window
            ).std()
        )

    price_grouped = data.groupby("series_id", sort=False)["unit_price"]
    data["price_lag_1"] = price_grouped.shift(1)
    data["price_lag_7"] = price_grouped.shift(7)
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


def _candidate_models(random_state: int) -> list[dict]:
    return [
        {
            "name": "legacy_hist_gradient_boosting",
            "features": LEGACY_FEATURE_COLUMNS,
            "estimator": HistGradientBoostingRegressor(
                learning_rate=0.06,
                max_iter=250,
                max_leaf_nodes=31,
                l2_regularization=0.1,
                random_state=random_state,
            ),
        },
        {
            "name": "enhanced_hist_gradient_boosting",
            "features": FEATURE_COLUMNS,
            "estimator": HistGradientBoostingRegressor(
                learning_rate=0.04,
                max_iter=400,
                max_leaf_nodes=31,
                l2_regularization=0.5,
                random_state=random_state,
            ),
        },
        {
            "name": "enhanced_extra_trees",
            "features": FEATURE_COLUMNS,
            "estimator": ExtraTreesRegressor(
                n_estimators=300,
                min_samples_leaf=2,
                max_features=0.8,
                n_jobs=-1,
                random_state=random_state,
            ),
        },
    ]


def _prediction_sources(
    model_prediction: np.ndarray, frame: pd.DataFrame
) -> np.ndarray:
    return np.column_stack(
        [
            model_prediction,
            frame["lag_7"].to_numpy(dtype="float64"),
            frame["lag_28"].to_numpy(dtype="float64"),
            frame["lag_56"].to_numpy(dtype="float64"),
        ]
    )


def _select_blend(
    actual: np.ndarray, model_prediction: np.ndarray, frame: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray]:
    sources = _prediction_sources(model_prediction, frame)
    denominator = float(np.abs(actual).sum())
    best_score = math.inf
    best_weights = np.asarray([1.0, 0.0, 0.0, 0.0])
    for model_parts in range(5, 11):
        for lag_7_parts in range(11 - model_parts):
            for lag_28_parts in range(11 - model_parts - lag_7_parts):
                lag_56_parts = 10 - model_parts - lag_7_parts - lag_28_parts
                weights = np.asarray(
                    [model_parts, lag_7_parts, lag_28_parts, lag_56_parts],
                    dtype="float64",
                ) / 10
                predicted = np.maximum(0, sources @ weights)
                score = float(np.abs(actual - predicted).sum() / denominator)
                if score < best_score:
                    best_score = score
                    best_weights = weights
    return best_weights, np.maximum(0, sources @ best_weights)


def _fit_predict(estimator, training, evaluation, columns) -> np.ndarray:
    estimator.fit(training[columns], np.log1p(training["quantity"]))
    return np.maximum(0, np.expm1(estimator.predict(evaluation[columns])))


def train_m5_model(
    frame: pd.DataFrame,
    *,
    horizon: int = 28,
    random_state: int = 42,
) -> tuple[dict, dict, pd.DataFrame]:
    if not 7 <= horizon <= 56:
        raise ValueError("M5 holdout horizon must be between 7 and 56 days.")
    features = build_m5_features(frame)
    latest_date = features["order_date"].max()
    holdout_start = latest_date - timedelta(days=horizon - 1)
    tuning_start = holdout_start - timedelta(days=horizon)

    candidate_results = {}
    selected = None
    for candidate in _candidate_models(random_state):
        columns = candidate["features"]
        available = features.dropna(subset=columns)
        selection_training = available[available["order_date"] < tuning_start]
        tuning = available[
            (available["order_date"] >= tuning_start)
            & (available["order_date"] < holdout_start)
        ]
        if selection_training.empty or tuning.empty:
            raise ValueError(
                "Prepared M5 data needs at least two holdout horizons after "
                "the longest feature lag."
            )
        model_prediction = _fit_predict(
            candidate["estimator"], selection_training, tuning, columns
        )
        actual = tuning["quantity"].to_numpy(dtype="float64")
        weights, blended_prediction = _select_blend(
            actual, model_prediction, tuning
        )
        blended_metrics = _metrics(actual, blended_prediction)
        result = {
            "feature_count": len(columns),
            "model_metrics": _metrics(actual, model_prediction),
            "blended_metrics": blended_metrics,
            "blend_weights": dict(zip(BLEND_SOURCE_NAMES, weights.tolist(), strict=True)),
        }
        candidate_results[candidate["name"]] = result
        if selected is None or blended_metrics["wmape"] < selected["wmape"]:
            selected = {
                **candidate,
                "weights": weights,
                "wmape": blended_metrics["wmape"],
                "selection_training": selection_training,
                "tuning": tuning,
            }

    if selected is None:
        raise ValueError("No M5 model candidate could be selected.")

    selected_columns = selected["features"]
    available = features.dropna(subset=selected_columns)
    training = available[available["order_date"] < holdout_start]
    holdout = available[available["order_date"] >= holdout_start]
    if training.empty or holdout.empty:
        raise ValueError("Prepared M5 data cannot produce a non-empty train/holdout split.")

    final_candidate = next(
        candidate
        for candidate in _candidate_models(random_state)
        if candidate["name"] == selected["name"]
    )
    model = final_candidate["estimator"]
    model_prediction = _fit_predict(model, training, holdout, selected_columns)
    sources = _prediction_sources(model_prediction, holdout)
    predicted = np.maximum(0, sources @ selected["weights"])
    baseline = np.maximum(0, holdout["lag_28"].to_numpy(dtype="float64"))
    actual = holdout["quantity"].to_numpy(dtype="float64")

    selection_training = selected["selection_training"]
    tuning = selected["tuning"]
    blend_weights = dict(
        zip(BLEND_SOURCE_NAMES, selected["weights"].tolist(), strict=True)
    )
    metrics = {
        "model": selected["name"],
        "target": "daily_unit_sales",
        "evaluation_scope": (
            "store-category one-step temporal holdout; not official WRMSSE"
        ),
        "evaluation_protocol": (
            "candidate and blend selection use the preceding horizon; the final "
            "holdout is evaluated once after selection"
        ),
        "feature_count": len(selected_columns),
        "training_rows": int(len(training)),
        "holdout_rows": int(len(holdout)),
        "series": int(available["series_id"].nunique()),
        "train_start": training["order_date"].min().date().isoformat(),
        "train_end": training["order_date"].max().date().isoformat(),
        "selection_train_start": selection_training[
            "order_date"
        ].min().date().isoformat(),
        "selection_train_end": selection_training[
            "order_date"
        ].max().date().isoformat(),
        "tuning_start": tuning["order_date"].min().date().isoformat(),
        "tuning_end": tuning["order_date"].max().date().isoformat(),
        "tuning_rows": int(len(tuning)),
        "holdout_start": holdout["order_date"].min().date().isoformat(),
        "holdout_end": holdout["order_date"].max().date().isoformat(),
        "selected_blend_weights": blend_weights,
        "candidate_tuning_results": candidate_results,
        "model_metrics": _metrics(actual, predicted),
        "unblended_model_metrics": _metrics(actual, model_prediction),
        "seasonal_naive_lag_28_metrics": _metrics(actual, baseline),
    }
    predictions = holdout[
        ["series_id", "order_date", "state_id", "store_id", "category", "quantity"]
    ].copy()
    predictions = predictions.rename(columns={"quantity": "actual_units"})
    predictions["predicted_units"] = np.round(predicted, 4)
    predictions["unblended_model_units"] = np.round(model_prediction, 4)
    predictions["seasonal_naive_units"] = np.round(baseline, 4)
    artifact = {
        "model": model,
        "features": selected_columns,
        "target_transform": "log1p",
        "blend_sources": BLEND_SOURCE_NAMES,
        "blend_weights": selected["weights"],
        "metrics": metrics,
    }
    return artifact, metrics, predictions


def save_m5_model(artifact: dict, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, destination, compress=3)
    return destination
