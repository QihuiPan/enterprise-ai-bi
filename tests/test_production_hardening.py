from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import StringIO
from threading import Event, Timer

from fastapi.testclient import TestClient
from sqlalchemy.engine import URL

from backend.app import health as health_checks
from backend.app.api import data as data_api
from backend.app.config import settings
from backend.app.main import _same_database_url, create_app
from backend.app.observability import PrometheusMetrics, access_logger
from backend.app.security import InMemoryRateLimiter


def _app_client(**overrides) -> TestClient:
    values = {"rate_limit_requests": 0, **overrides}
    app_settings = replace(settings, **values)
    return TestClient(create_app(app_settings))


def test_api_key_is_optional_and_protects_only_business_routes() -> None:
    with _app_client(api_key="demo-secret") as client:
        unauthorized = client.get("/api/analytics/kpis")
        assert unauthorized.status_code == 401
        assert unauthorized.headers["www-authenticate"] == "ApiKey"

        wrong_key = client.get("/api/analytics/kpis", headers={"X-API-Key": "wrong"})
        assert wrong_key.status_code == 401

        authorized = client.get(
            "/api/analytics/kpis", headers={"X-API-Key": "demo-secret"}
        )
        assert authorized.status_code == 409
        assert client.get("/health/live").status_code == 200
        assert client.get("/metrics").status_code == 200

    with _app_client(api_key=None) as client:
        assert client.get("/api/analytics/kpis").status_code == 409


def test_request_id_is_returned_and_access_log_is_structured() -> None:
    output = StringIO()
    handler = logging.StreamHandler(output)
    access_logger.addHandler(handler)
    try:
        with _app_client() as client:
            response = client.get(
                "/health/live", headers={"X-Request-ID": "demo-request-7"}
            )
    finally:
        access_logger.removeHandler(handler)

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "demo-request-7"
    event = json.loads(output.getvalue().splitlines()[-1])
    assert event["event"] == "http_request"
    assert event["request_id"] == "demo-request-7"
    assert event["path"] == "/health/live"
    assert event["status_code"] == 200
    assert event["duration_ms"] >= 0


def test_invalid_request_id_is_replaced() -> None:
    with _app_client() as client:
        response = client.get("/health/live", headers={"X-Request-ID": "not safe!"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] != "not safe!"
    assert len(response.headers["x-request-id"]) == 32


def test_rate_limit_returns_standard_retry_headers() -> None:
    with _app_client(rate_limit_requests=2, rate_limit_window_seconds=60) as client:
        first = client.get("/api/analytics/kpis")
        second = client.get("/api/analytics/kpis")
        limited = client.get("/api/analytics/kpis")

    assert first.status_code == 409
    assert first.headers["ratelimit-remaining"] == "1"
    assert second.status_code == 409
    assert second.headers["ratelimit-remaining"] == "0"
    assert limited.status_code == 429
    assert limited.headers["ratelimit-limit"] == "2"
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.headers["x-request-id"]


def test_unauthenticated_requests_do_not_consume_authenticated_quota() -> None:
    with _app_client(api_key="demo-secret", rate_limit_requests=1) as client:
        for _ in range(3):
            assert client.get("/api/analytics/kpis").status_code == 401

        authorized = client.get(
            "/api/analytics/kpis", headers={"X-API-Key": "demo-secret"}
        )
        limited = client.get(
            "/api/analytics/kpis", headers={"X-API-Key": "demo-secret"}
        )

    assert authorized.status_code == 409
    assert authorized.headers["ratelimit-remaining"] == "0"
    assert limited.status_code == 429


def test_api_responses_are_never_cacheable_including_middleware_rejections(
    tmp_path,
) -> None:
    with _app_client(api_key="demo-secret", rate_limit_requests=1) as client:
        unauthorized = client.get("/api/analytics/kpis")
        authorized = client.get(
            "/api/analytics/kpis", headers={"X-API-Key": "demo-secret"}
        )
        limited = client.get(
            "/api/analytics/kpis", headers={"X-API-Key": "demo-secret"}
        )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 409
    assert limited.status_code == 429
    assert unauthorized.headers["cache-control"] == "no-store"
    assert authorized.headers["cache-control"] == "no-store"
    assert limited.headers["cache-control"] == "no-store"

    database_url = f"sqlite:///{(tmp_path / 'no-store.db').as_posix()}"
    with _app_client(database_url=database_url) as client:
        success = client.post("/api/data/demo")
        system = client.get("/health/live")

    assert success.status_code == 200
    assert success.headers["cache-control"] == "no-store"
    assert "cache-control" not in system.headers


def test_rate_limiter_bounds_client_state_and_resets_windows() -> None:
    limiter = InMemoryRateLimiter(requests=1, window_seconds=10, max_clients=2)
    assert limiter.consume("one", now=0)[0]
    assert limiter.consume("two", now=0)[0]
    assert limiter.consume("three", now=0)[0]
    assert limiter.tracked_clients == 2
    assert limiter.consume("three", now=1)[0] is False
    assert limiter.consume("three", now=11)[0] is True


def test_metrics_use_prometheus_format_and_route_templates() -> None:
    with _app_client() as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/api/analytics/kpis").status_code == 409
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "text/plain; version=0.0.4"
    )
    assert "# TYPE enterprise_ai_bi_http_requests_total counter" in response.text
    assert (
        'enterprise_ai_bi_http_requests_total{method="GET",path="/health/live",status="200"} 1'
        in response.text
    )
    assert (
        "enterprise_ai_bi_http_requests_total"
        '{method="GET",path="/api/analytics/kpis",status="409"} 1'
        in response.text
    )


def test_metrics_bound_arbitrary_http_method_cardinality() -> None:
    registry = PrometheusMetrics()
    for index in range(100):
        registry.started()
        registry.completed(
            method=f"CUSTOM-{index}",
            path="unmatched",
            status_code=405,
            duration_seconds=0.01,
        )

    rendered = registry.render()

    assert rendered.count('method="OTHER",path="unmatched",status="405"') == 3
    assert "CUSTOM-" not in rendered
    assert (
        'enterprise_ai_bi_http_requests_total{method="OTHER",path="unmatched",status="405"} 100'
        in rendered
    )


def test_readiness_checks_database_and_liveness_stays_independent(monkeypatch) -> None:
    with _app_client() as client:
        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json()["checks"] == {"database": "ok"}
        assert client.get("/health").json()["status"] == "ok"

        monkeypatch.setattr(health_checks, "database_is_ready", lambda _: False)
        unavailable = client.get("/health/ready")
        compatibility_health = client.get("/health")
        live = client.get("/health/live")

    assert unavailable.status_code == 503
    assert unavailable.json()["status"] == "not_ready"
    assert unavailable.json()["checks"] == {"database": "unavailable"}
    assert compatibility_health.status_code == 503
    assert live.status_code == 200


def test_app_factory_applies_its_own_upload_limit() -> None:
    with _app_client(max_upload_bytes=4) as client:
        response = client.post(
            "/api/data/upload",
            files={"file": ("large.csv", b"12345", "text/csv")},
        )

    assert response.status_code == 413


def test_large_sync_ingestion_does_not_block_liveness(monkeypatch) -> None:
    started = Event()
    release = Event()

    def slow_load(frame, session, *, replace=True):
        started.set()
        release.wait(timeout=5)
        return {
            "rows_loaded": len(frame),
            "date_min": "2026-01-01",
            "date_max": "2026-01-01",
            "revenue_total": 10.0,
            "replaced_existing": replace,
        }

    monkeypatch.setattr(data_api, "load_sales_frame", slow_load)
    content = (
        b"order_id,order_date,customer_id,region,category,product,quantity,unit_price,discount\n"
        b"A-1,2026-01-01,C-1,North,Analytics,Insight Pro,1,10,0\n"
    )

    with _app_client() as client, ThreadPoolExecutor(max_workers=1) as pool:
        upload = pool.submit(
            client.post,
            "/api/data/upload",
            files={"file": ("sales.csv", content, "text/csv")},
        )
        assert started.wait(timeout=2)
        fallback = Timer(2, release.set)
        fallback.start()
        try:
            live = client.get("/health/live")
            assert live.status_code == 200
            assert not release.is_set()
        finally:
            release.set()
            fallback.cancel()
        assert upload.result(timeout=2).status_code == 200


def test_app_factory_uses_its_configured_database(tmp_path) -> None:
    database_path = tmp_path / "custom-app.db"
    app_settings = replace(
        settings,
        database_url=f"sqlite:///{database_path.as_posix()}",
        rate_limit_requests=0,
    )

    with TestClient(create_app(app_settings)) as client:
        assert client.post("/api/data/demo").status_code == 200
        assert client.get("/api/analytics/kpis").json()["order_count"] == 720

    assert database_path.exists()


def test_app_factory_database_comparison_includes_hidden_passwords() -> None:
    first = URL.create(
        "postgresql+psycopg",
        username="app",
        password="first:p@ss",
        host="postgres",
        database="enterprise_bi",
    )
    rotated = URL.create(
        "postgresql+psycopg",
        username="app",
        password="rotated:p@ss",
        host="postgres",
        database="enterprise_bi",
    )

    assert str(first) == str(rotated)
    assert _same_database_url(first, rotated) is False
