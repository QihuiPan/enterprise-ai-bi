from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from io import StringIO
from pathlib import Path
from threading import Event, Timer

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from backend.app import database
from backend.app import health as health_checks
from backend.app.api import data as data_api
from backend.app.config import settings
from backend.app.currency import resolve_source_currency
from backend.app.main import _same_database_url, create_app
from backend.app.models import DatasetProfile, SalesRecord
from backend.app.observability import PrometheusMetrics, access_logger
from backend.app.security import InMemoryRateLimiter


def test_postgresql_engine_uses_repeatable_read_snapshot(monkeypatch) -> None:
    captured: dict = {}
    sentinel = object()

    def fake_create_engine(database_url, **options):
        captured["database_url"] = database_url
        captured["options"] = options
        return sentinel

    monkeypatch.setattr(database, "create_engine", fake_create_engine)

    result = database.build_engine("postgresql+psycopg://app:test@db/app")

    assert result is sentinel
    assert captured["options"]["isolation_level"] == "REPEATABLE READ"
    assert captured["options"]["pool_pre_ping"] is True


def _app_client(**overrides) -> TestClient:
    values = {"rate_limit_requests": 0, **overrides}
    app_settings = replace(settings, **values)
    return TestClient(create_app(app_settings))


def _sales_record(*, revenue: float = 10.0) -> SalesRecord:
    return SalesRecord(
        order_id="LEGACY-1",
        order_date=date(2026, 1, 1),
        customer_id="C-1",
        region="North",
        category="Hardware",
        product="Widget",
        quantity=1,
        unit_price=revenue,
        discount=0,
        revenue=revenue,
    )


def test_startup_backfills_profile_without_deleting_legacy_sales(tmp_path) -> None:
    legacy_engine = database.build_engine(
        f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    )
    try:
        database.Base.metadata.create_all(legacy_engine)
        with Session(legacy_engine) as session:
            session.add(_sales_record())
            session.commit()

        database.create_tables(legacy_engine)

        with Session(legacy_engine) as session:
            profile = session.get(DatasetProfile, 1)
            rows = list(session.scalars(select(SalesRecord)))
        assert len(rows) == 1
        assert profile is not None
        assert profile.dataset_name == "Legacy sales snapshot"
        assert profile.currency == "USD"
        assert len(profile.content_sha256) == 64
        assert "backfilled" in profile.semantic_warning.lower()
        assert data_api._profile_dict(profile)["currency_verified"] is False
        with Session(legacy_engine) as session:
            assert resolve_source_currency(session, "GBP") == "GBP"
    finally:
        database.Base.metadata.drop_all(legacy_engine)
        legacy_engine.dispose()


def test_startup_normalizes_older_inferred_legacy_profile(tmp_path) -> None:
    legacy_engine = database.build_engine(
        f"sqlite:///{(tmp_path / 'inferred-legacy.db').as_posix()}"
    )
    try:
        database.Base.metadata.create_all(legacy_engine)
        with Session(legacy_engine) as session:
            record = _sales_record()
            session.add(record)
            session.add(
                DatasetProfile(
                    id=1,
                    dataset_name="UCI Online Retail II",
                    source_format="database",
                    source_sheet=None,
                    original_filename="legacy-database-snapshot",
                    content_sha256="a" * 64,
                    rows_loaded=1,
                    date_min=record.order_date,
                    date_max=record.order_date,
                    revenue_total=record.revenue,
                    currency="GBP",
                    metric_mode="components",
                    mapped_fields={},
                    generated_fields=["revenue"],
                    warnings=[],
                    aggregate_record_proxy=True,
                    record_count_label="Customer-country-day records",
                    entity_count_label="Customers",
                    average_value_label="Average aggregate record value",
                    average_frequency_label="Average aggregate records",
                    semantic_warning="Previously inferred.",
                    entity_warning="Previously inferred.",
                    units_available=True,
                    units_label="Units sold",
                    unit_warning=None,
                    anomaly_features=["revenue"],
                )
            )
            session.commit()

        database.create_tables(legacy_engine)

        with Session(legacy_engine) as session:
            profile = session.get(DatasetProfile, 1)
        assert profile.dataset_name == "Legacy sales snapshot"
        assert profile.currency == "USD"
        assert profile.entity_count_label == "Entities"
        assert data_api._profile_dict(profile)["currency_verified"] is False
    finally:
        database.Base.metadata.drop_all(legacy_engine)
        legacy_engine.dispose()


def test_concurrent_sqlite_startups_have_one_legacy_backfill_winner(tmp_path) -> None:
    database_path = tmp_path / "concurrent-startup.db"
    seed_engine = database.build_engine(f"sqlite:///{database_path.as_posix()}")
    database.Base.metadata.create_all(seed_engine)
    with Session(seed_engine) as session:
        session.add(_sales_record())
        session.commit()
    seed_engine.dispose()

    engines = [
        database.build_engine(f"sqlite:///{database_path.as_posix()}")
        for _ in range(2)
    ]
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(database.create_tables, engine) for engine in engines]
            for future in futures:
                future.result(timeout=10)

        with Session(engines[0]) as session:
            profiles = list(session.scalars(select(DatasetProfile)))
            records = list(session.scalars(select(SalesRecord)))
        assert len(profiles) == 1
        assert profiles[0].dataset_name == "Legacy sales snapshot"
        assert len(records) == 1
    finally:
        for engine in engines:
            database.Base.metadata.drop_all(engine)
            engine.dispose()


def test_nginx_body_limit_exceeds_api_file_limit_plus_multipart_overhead() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    nginx = (repository_root / "frontend" / "nginx.conf").read_text(
        encoding="utf-8"
    )

    assert "client_max_body_size 65m;" in nginx
    assert 65 * 1024 * 1024 > settings.max_upload_bytes + 256 * 1024


def test_sqlite_reader_keeps_one_snapshot_during_concurrent_write(tmp_path) -> None:
    snapshot_engine = database.build_engine(
        f"sqlite:///{(tmp_path / 'snapshot.db').as_posix()}"
    )
    try:
        database.Base.metadata.create_all(snapshot_engine)
        with Session(snapshot_engine) as session:
            session.add(_sales_record(revenue=10))
            session.commit()

        with Session(snapshot_engine) as reader:
            first = reader.scalar(select(SalesRecord.revenue))
            with Session(snapshot_engine) as writer:
                record = writer.scalar(select(SalesRecord))
                record.revenue = 20
                writer.commit()
            second = reader.scalar(select(SalesRecord.revenue))

        assert first == 10
        assert second == 10
    finally:
        database.Base.metadata.drop_all(snapshot_engine)
        snapshot_engine.dispose()


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


def test_chunked_upload_is_bounded_before_multipart_parsing() -> None:
    boundary = "bounded-upload-test"
    chunks = iter(
        [
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="file"; filename="large.csv"\r\n'
                "Content-Type: text/csv\r\n\r\n"
            ).encode(),
            b"x" * (128 * 1024),
            b"x" * (128 * 1024),
            b"x" * (128 * 1024),
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    with _app_client(max_upload_bytes=4) as client:
        response = client.post(
            "/api/data/upload",
            content=chunks,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

    assert response.status_code == 413
    assert "request body" in response.json()["detail"].lower()


def test_declared_small_content_length_cannot_bypass_streamed_body_limit() -> None:
    boundary = "spoofed-length-test"
    chunks = iter(
        [
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="file"; filename="large.csv"\r\n'
                "Content-Type: text/csv\r\n\r\n"
            ).encode(),
            b"x" * (128 * 1024),
            b"x" * (128 * 1024),
            b"x" * (128 * 1024),
            f"\r\n--{boundary}--\r\n".encode(),
        ]
    )
    with _app_client(max_upload_bytes=4) as client:
        response = client.post(
            "/api/data/upload",
            content=chunks,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": "1",
            },
        )

    assert response.status_code == 413
    assert "request body" in response.json()["detail"].lower()


def test_unauthorized_upload_body_is_not_consumed_before_authentication() -> None:
    consumed = 0

    def body_chunks():
        nonlocal consumed
        consumed += 1
        yield b"untrusted upload body"

    with _app_client(api_key="required-secret") as client:
        response = client.post(
            "/api/data/upload",
            content=body_chunks(),
            headers={"Content-Type": "application/octet-stream"},
        )

    assert response.status_code == 401
    assert consumed == 0


def test_large_sync_ingestion_does_not_block_liveness(monkeypatch) -> None:
    started = Event()
    release = Event()

    def slow_load(frame, session, *, replace=True, profile=None):
        assert profile is not None
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
