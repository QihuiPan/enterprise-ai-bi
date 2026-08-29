from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.engine import URL

from backend.app.config import Settings
from backend.app.database import engine
from backend.app.services.business import BusinessIntelligence
from data_pipeline.sample import build_demo_frame
from data_pipeline.validation import SalesFrameValidator
from ml.anomaly_detection import SalesAnomalyDetector
from ml.forecasting import RevenueForecaster
from ml.segmentation import CustomerSegmenter


def test_intelligence_card_does_not_mislabel_every_answer_as_executive() -> None:
    component = Path("frontend/src/components/IntelligenceSection.jsx").read_text(
        encoding="utf-8"
    )

    assert "<strong>Agent response</strong>" in component
    assert "<strong>Executive Agent</strong>" not in component


def test_business_context_caches_one_sales_snapshot(monkeypatch) -> None:
    frame = build_demo_frame()
    calls = 0

    def fake_sales_frame(_, __=None):
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
    monkeypatch.setenv("API_KEY", "test-secret")
    monkeypatch.setenv("API_KEY_HEADER", "X-Demo-Key")
    monkeypatch.setenv("RATE_LIMIT_REQUESTS", "25")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "30")
    monkeypatch.setenv("RATE_LIMIT_MAX_CLIENTS", "500")
    settings = Settings.from_env()
    assert settings.app_name == "Test BI"
    assert settings.cors_origins == ["https://one.example", "https://two.example"]
    assert settings.max_upload_bytes == 4096
    assert settings.api_key == "test-secret"
    assert settings.api_key_header == "X-Demo-Key"
    assert settings.rate_limit_requests == 25
    assert settings.rate_limit_window_seconds == 30
    assert settings.rate_limit_max_clients == 500
    assert SalesFrameValidator.canonical_name(" Unit Price ($) ") == "unit_price"


def test_database_components_safely_preserve_reserved_password_characters(
    monkeypatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_HOST", "postgres")
    monkeypatch.setenv("DATABASE_PORT", "5432")
    monkeypatch.setenv("DATABASE_NAME", "enterprise_bi")
    monkeypatch.setenv("DATABASE_USER", "enterprise_bi")
    monkeypatch.setenv("DATABASE_PASSWORD", "p@ss:/#%word")

    configured = Settings.from_env()

    assert isinstance(configured.database_url, URL)
    assert configured.database_url.password == "p@ss:/#%word"
    assert configured.database_url.host == "postgres"


@pytest.mark.parametrize(
    ("api_key", "cors_origins", "message"),
    [
        ("short", "https://dashboard.example", "at least 32"),
        ("x" * 32, "*", "explicit origin allowlist"),
        ("x" * 32, "https://dashboard.example/path", "exact HTTP\(S\) origins"),
    ],
)
def test_production_settings_fail_closed_for_weak_access_controls(
    monkeypatch, api_key, cors_origins, message
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_KEY", api_key)
    monkeypatch.setenv("CORS_ORIGINS", cors_origins)

    with pytest.raises(ValueError, match=message):
        Settings.from_env()


def test_production_settings_accept_strong_key_and_exact_origins(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("API_KEY", "x" * 32)
    monkeypatch.setenv(
        "CORS_ORIGINS", "https://dashboard.example,http://127.0.0.1:8080"
    )

    configured = Settings.from_env()

    assert configured.api_key == "x" * 32
    assert configured.cors_origins == [
        "https://dashboard.example",
        "http://127.0.0.1:8080",
    ]
