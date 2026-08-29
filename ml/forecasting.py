from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error


def _recursive_average(values: np.ndarray, steps: int, window: int = 3) -> np.ndarray:
    history = values.astype(float).tolist()
    predictions: list[float] = []
    for _ in range(steps):
        prediction = float(np.mean(history[-min(window, len(history)) :]))
        predictions.append(prediction)
        history.append(prediction)
    return np.asarray(predictions)


def _recursive_seasonal(values: np.ndarray, steps: int, season: int = 12) -> np.ndarray:
    history = values.astype(float).tolist()
    predictions: list[float] = []
    for _ in range(steps):
        prediction = float(history[-season])
        predictions.append(prediction)
        history.append(prediction)
    return np.asarray(predictions)


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    return {
        "mae": round(float(mean_absolute_error(actual, predicted)), 2),
        "rmse": round(float(math.sqrt(mean_squared_error(actual, predicted))), 2),
    }


@dataclass(frozen=True)
class RevenueForecaster:
    horizon: int = 3
    minimum_history_months: int = 6
    holdout_fraction: float = 0.2
    interval_z_score: float = 1.96

    def run(self, frame: pd.DataFrame) -> dict:
        if not 1 <= self.horizon <= 12:
            raise ValueError("Forecast horizon must be between 1 and 12 months.")
        observed = (
            frame.assign(period=frame["order_date"].dt.to_period("M"))
            .groupby("period")["revenue"]
            .sum()
            .sort_index()
        )
        data_start = pd.Timestamp(frame["order_date"].min()).normalize()
        data_end = pd.Timestamp(frame["order_date"].max()).normalize()
        monthly_aggregate_input = bool(frame["order_date"].dt.is_month_start.all())
        excluded_periods: list[dict[str, str]] = []
        excluded_labels: set[pd.Period] = set()
        first_period = observed.index[0]
        last_period = observed.index[-1]
        if (
            not monthly_aggregate_input
            and data_start > pd.Timestamp(first_period.start_time).normalize()
        ):
            excluded_labels.add(first_period)
            excluded_periods.append(
                {
                    "period": str(first_period),
                    "reason": "incomplete_start_boundary",
                    "observed_through": data_start.date().isoformat(),
                }
            )
        if (
            not monthly_aggregate_input
            and data_end < pd.Timestamp(last_period.end_time).normalize()
        ):
            excluded_labels.add(last_period)
            excluded_periods.append(
                {
                    "period": str(last_period),
                    "reason": "incomplete_end_boundary",
                    "observed_through": data_end.date().isoformat(),
                }
            )
        observed = observed.drop(list(excluded_labels), errors="ignore")
        if observed.empty:
            raise ValueError(
                "No complete monthly periods are available for forecasting."
            )
        complete_periods = pd.period_range(
            observed.index.min(), observed.index.max(), freq="M"
        )
        monthly = observed.reindex(complete_periods, fill_value=0.0)
        if len(monthly) < self.minimum_history_months:
            raise ValueError(
                f"At least {self.minimum_history_months} months of data are required "
                "for forecasting."
            )

        values = monthly.to_numpy(dtype=float)
        holdout = max(2, int(math.ceil(len(values) * self.holdout_fraction)))
        split = len(values) - holdout
        x = np.arange(len(values)).reshape(-1, 1)

        evaluation_model = LinearRegression().fit(x[:split], values[:split])
        holdout_predictions = {
            "linear_trend": np.maximum(0, evaluation_model.predict(x[split:])),
            "trailing_mean_3": np.maximum(
                0, _recursive_average(values[:split], holdout, window=3)
            ),
        }
        if split >= 12:
            holdout_predictions["seasonal_naive_12"] = np.maximum(
                0, _recursive_seasonal(values[:split], holdout, season=12)
            )
        candidate_evaluation = {
            name: _metrics(values[split:], prediction)
            for name, prediction in holdout_predictions.items()
        }
        selected_model = min(
            candidate_evaluation,
            key=lambda name: (candidate_evaluation[name]["rmse"], name),
        )

        final_linear_model = LinearRegression().fit(x, values)
        future_x = np.arange(len(values), len(values) + self.horizon).reshape(-1, 1)
        future_candidates = {
            "linear_trend": np.maximum(0, final_linear_model.predict(future_x)),
            "trailing_mean_3": np.maximum(
                0, _recursive_average(values, self.horizon, window=3)
            ),
        }
        if len(values) >= 12:
            future_candidates["seasonal_naive_12"] = np.maximum(
                0, _recursive_seasonal(values, self.horizon, season=12)
            )
        future_values = future_candidates[selected_model]
        selected_errors = values[split:] - holdout_predictions[selected_model]
        residual_std = float(np.std(selected_errors))
        baseline_rmse = candidate_evaluation["linear_trend"]["rmse"]
        selected_rmse = candidate_evaluation[selected_model]["rmse"]
        improvement = (
            (baseline_rmse - selected_rmse) / baseline_rmse * 100 if baseline_rmse else 0.0
        )
        last_period = monthly.index[-1]
        future_periods = [
            last_period + index for index in range(1, self.horizon + 1)
        ]

        return {
            "model": selected_model,
            "baseline_model": "linear_trend",
            "evaluation": {
                "holdout_months": holdout,
                **candidate_evaluation[selected_model],
                "improvement_vs_linear_rmse_pct": round(float(improvement), 2),
            },
            "candidate_evaluation": candidate_evaluation,
            "input_grain": (
                "monthly_aggregate"
                if monthly_aggregate_input
                else "transaction_observations"
            ),
            "excluded_periods": excluded_periods,
            "history": [
                {"period": str(period), "revenue": round(float(value), 2)}
                for period, value in monthly.items()
            ],
            "forecast": [
                {
                    "period": str(period),
                    "revenue": round(float(value), 2),
                    "lower_95": round(
                        max(0, float(value) - self.interval_z_score * residual_std),
                        2,
                    ),
                    "upper_95": round(
                        float(value) + self.interval_z_score * residual_std, 2
                    ),
                }
                for period, value in zip(future_periods, future_values, strict=True)
            ],
            "caveat": (
                "Chronological candidate selection against a linear baseline; "
                "month-start-only inputs are treated as complete monthly aggregates, "
                "while incomplete transaction boundary months are excluded; intervals "
                "reflect holdout residual spread, not causal certainty."
            ),
        }


def forecast_revenue(frame: pd.DataFrame, horizon: int = 3) -> dict:
    return RevenueForecaster(horizon=horizon).run(frame)
