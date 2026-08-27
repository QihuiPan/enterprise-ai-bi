from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error


def forecast_revenue(frame: pd.DataFrame, horizon: int = 3) -> dict:
    monthly = (
        frame.assign(period=frame["order_date"].dt.to_period("M"))
        .groupby("period", as_index=False)["revenue"]
        .sum()
        .sort_values("period")
    )
    if len(monthly) < 6:
        raise ValueError("At least six months of data are required for forecasting.")
    if not 1 <= horizon <= 12:
        raise ValueError("Forecast horizon must be between 1 and 12 months.")

    values = monthly["revenue"].to_numpy(dtype=float)
    holdout = max(2, int(math.ceil(len(values) * 0.2)))
    split = len(values) - holdout
    x = np.arange(len(values)).reshape(-1, 1)

    evaluation_model = LinearRegression().fit(x[:split], values[:split])
    predicted_test = evaluation_model.predict(x[split:])
    mae = mean_absolute_error(values[split:], predicted_test)
    rmse = math.sqrt(mean_squared_error(values[split:], predicted_test))

    model = LinearRegression().fit(x, values)
    residual_std = float(np.std(values - model.predict(x)))
    future_x = np.arange(len(values), len(values) + horizon).reshape(-1, 1)
    future_values = np.maximum(0, model.predict(future_x))
    last_period = monthly["period"].iloc[-1]
    future_periods = [last_period + index for index in range(1, horizon + 1)]

    return {
        "model": "linear_trend_baseline",
        "evaluation": {
            "holdout_months": holdout,
            "mae": round(float(mae), 2),
            "rmse": round(float(rmse), 2),
        },
        "history": [
            {"period": str(row.period), "revenue": round(float(row.revenue), 2)}
            for row in monthly.itertuples(index=False)
        ],
        "forecast": [
            {
                "period": str(period),
                "revenue": round(float(value), 2),
                "lower_95": round(max(0, float(value) - 1.96 * residual_std), 2),
                "upper_95": round(float(value) + 1.96 * residual_std, 2),
            }
            for period, value in zip(future_periods, future_values, strict=True)
        ],
        "caveat": (
            "Linear trend baseline; intervals reflect historical residual spread, "
            "not causal certainty."
        ),
    }
