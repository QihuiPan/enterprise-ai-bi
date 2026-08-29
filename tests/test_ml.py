from __future__ import annotations

import numpy as np
import pandas as pd

from data_pipeline.sample import build_demo_frame
from ml.anomaly_detection import detect_anomalies
from ml.forecasting import forecast_revenue
from ml.segmentation import segment_customers


def test_forecast_exposes_holdout_metrics_and_intervals() -> None:
    result = forecast_revenue(build_demo_frame(), horizon=3)
    assert len(result["forecast"]) == 3
    assert result["evaluation"]["mae"] >= 0
    assert result["forecast"][0]["lower_95"] <= result["forecast"][0]["revenue"]
    assert result["excluded_periods"] == []
    assert result["history"][0]["period"] == "2024-07"
    assert result["history"][-1]["period"] == "2026-06"
    assert result["forecast"][0]["period"] == "2026-07"


def test_forecast_selects_seasonal_candidate_without_holdout_leakage() -> None:
    periods = pd.Series(pd.date_range("2021-01-01", periods=36, freq="MS"))
    periods.iloc[-1] = periods.iloc[-1] + pd.offsets.MonthEnd(0)
    seasonal = np.tile(np.arange(100.0, 1300.0, 100.0), 3)
    frame = pd.DataFrame({"order_date": periods, "revenue": seasonal})

    result = forecast_revenue(frame, horizon=3)

    assert result["model"] == "seasonal_naive_12"
    assert result["evaluation"]["rmse"] == 0
    assert result["candidate_evaluation"]["linear_trend"]["rmse"] > 0
    assert [item["revenue"] for item in result["forecast"]] == [100.0, 200.0, 300.0]


def test_forecast_excludes_m5_style_partial_final_month() -> None:
    periods = list(pd.date_range("2024-01-01", "2025-05-01", freq="MS"))
    periods.append(pd.Timestamp("2025-06-19"))
    frame = pd.DataFrame(
        {
            "order_date": periods,
            "revenue": np.arange(1, len(periods) + 1, dtype=float) * 100,
        }
    )

    result = forecast_revenue(frame, horizon=2)

    assert result["excluded_periods"] == [
        {
            "period": "2025-06",
            "reason": "incomplete_end_boundary",
            "observed_through": "2025-06-19",
        }
    ]
    assert result["history"][-1]["period"] == "2025-05"
    assert result["forecast"][0]["period"] == "2025-06"


def test_forecast_preserves_iowa_style_complete_monthly_aggregates() -> None:
    frame = pd.DataFrame(
        {
            "order_date": pd.date_range("2024-01-01", periods=12, freq="MS"),
            "revenue": np.arange(1, 13, dtype=float) * 1_000,
        }
    )

    result = forecast_revenue(frame, horizon=2)

    assert result["input_grain"] == "monthly_aggregate"
    assert result["excluded_periods"] == []
    assert result["history"][-1]["period"] == "2024-12"
    assert result["forecast"][0]["period"] == "2025-01"


def test_segmentation_assigns_every_customer() -> None:
    frame = build_demo_frame()
    result = segment_customers(frame)
    assert len(result["customers"]) == frame["customer_id"].nunique()
    assert sum(segment["customers"] for segment in result["segments"]) == len(result["customers"])


def test_anomaly_detection_returns_ranked_records() -> None:
    result = detect_anomalies(build_demo_frame(), limit=5)
    scores = [item["score"] for item in result["anomalies"]]
    assert 0 < result["anomaly_count"] < result["records_evaluated"]
    assert scores == sorted(scores, reverse=True)
