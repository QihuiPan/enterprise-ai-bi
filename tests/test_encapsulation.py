from __future__ import annotations

from sqlalchemy import event

from backend.app.config import Settings
from backend.app.database import engine
from backend.app.services.business import BusinessIntelligence
from data_pipeline.sample import build_demo_frame
from data_pipeline.validation import SalesFrameValidator
from ml.anomaly_detection import SalesAnomalyDetector
from ml.forecasting import RevenueForecaster
from ml.segmentation import CustomerSegmenter


def test_business_context_caches_one_sales_snapshot(monkeypatch) -> None:
    frame = build_demo_frame()
    calls = 0

    def fake_sales_frame(_):
        nonlocal calls
        calls += 1
        return frame

    monkeypatch.setattr("backend.app.services.business.sales_frame", fake_sales_frame)
    business = BusinessIntelligence(session=object())
    assert business.analytics.kpis()["order_count"] == len(frame)
    assert business.machine_learning.revenue_forecast(1)["forecast"]
    assert business.frame is frame
    assert calls == 1


def test_executive_report_queries_sales_table_once(client) -> None:
    assert client.post("/api/data/demo").status_code == 200
    sales_queries: list[str] = []

    def capture_sales_select(_, __, statement, ___, ____, _____):
        normalized = statement.upper()
        if normalized.startswith("SELECT") and "FROM SALES_RECORDS" in normalized:
            sales_queries.append(statement)

    event.listen(engine, "before_cursor_execute", capture_sales_select)
    try:
        response = client.get("/api/reports/executive")
    finally:
        event.remove(engine, "before_cursor_execute", capture_sales_select)

    assert response.status_code == 200
    assert len(sales_queries) == 1


def test_configurable_model_facades_preserve_contracts() -> None:
    frame = build_demo_frame()
    assert len(RevenueForecaster(horizon=2).run(frame)["forecast"]) == 2
    assert CustomerSegmenter(requested_clusters=3).run(frame)["cluster_count"] == 3
    assert SalesAnomalyDetector(limit=3).run(frame)["records_evaluated"] == len(frame)


def test_settings_and_validator_are_explicitly_configurable(monkeypatch) -> None:
    monkeypatch.setenv("APP_NAME", "Test BI")
    monkeypatch.setenv("CORS_ORIGINS", "https://one.example, https://two.example")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "4096")
    settings = Settings.from_env()
    assert settings.app_name == "Test BI"
    assert settings.cors_origins == ["https://one.example", "https://two.example"]
    assert settings.max_upload_bytes == 4096
    assert SalesFrameValidator.canonical_name(" Unit Price ($) ") == "unit_price"
