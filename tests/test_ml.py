from __future__ import annotations

from data_pipeline.sample import build_demo_frame
from ml.anomaly_detection import detect_anomalies
from ml.forecasting import forecast_revenue
from ml.segmentation import segment_customers


def test_forecast_exposes_holdout_metrics_and_intervals() -> None:
    result = forecast_revenue(build_demo_frame(), horizon=3)
    assert len(result["forecast"]) == 3
    assert result["evaluation"]["mae"] >= 0
    assert result["forecast"][0]["lower_95"] <= result["forecast"][0]["revenue"]


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
