from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import event, select

from backend.app.api import data as data_api
from backend.app.database import SessionLocal, engine
from backend.app.models import SalesRecord
from data_pipeline.sample import build_demo_frame


def test_end_to_end_demo_analytics_and_grounded_answer(client) -> None:
    ingestion = client.post("/api/data/demo")
    assert ingestion.status_code == 200
    assert ingestion.json()["rows_loaded"] == 720

    kpis = client.get("/api/analytics/kpis")
    assert kpis.status_code == 200
    assert kpis.json()["order_count"] == 720

    insight = client.post(
        "/api/insights/query",
        json={"question": "Why did revenue change in the latest month?"},
    )
    assert insight.status_code == 200
    payload = insight.json()
    assert payload["evidence"]
    assert payload["tools_used"] == ["explain_revenue_change"]
    assert "sql" not in " ".join(payload["tools_used"]).lower()


def test_plan_flagship_last_quarter_question_uses_complete_quarters(client) -> None:
    assert client.post("/api/data/demo").status_code == 200

    response = client.post(
        "/api/insights/query",
        json={"question": "Why did sales drop last quarter?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tools_used"] == ["explain_revenue_change"]
    assert payload["evidence"][0]["metric"] == "quarter_over_quarter_change_pct"
    assert "2026-Q1" in payload["answer"]
    assert "2026-Q2" in payload["answer"]
    assert "quarter over quarter" in payload["answer"]


def test_revenue_summary_last_quarter_uses_latest_complete_quarter(client) -> None:
    assert client.post("/api/data/demo").status_code == 200

    response = client.post(
        "/api/insights/query",
        json={"question": "What was revenue last quarter?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tools_used"] == ["approved_analytics_query"]
    period = payload["query_plan"]["period"]
    assert period["kind"] == "previous_quarter"
    assert period["label"] == "latest complete data quarter (2026-Q2)"
    assert period["resolved_start"] == "2026-04-01"
    assert period["resolved_end"] == "2026-06-30"
    assert "2026-Q2" in payload["answer"]


@pytest.mark.parametrize(
    ("first_date", "second_date", "first_price", "expected_text"),
    [
        ("2026-01-15", "2026-02-15", 0, "zero baseline"),
        ("2026-01-15", "2026-03-15", 10, "not consecutive"),
    ],
)
def test_change_insight_degrades_without_comparable_months(
    client, first_date, second_date, first_price, expected_text
) -> None:
    content = (
        "order_id,order_date,customer_id,region,category,product,quantity,unit_price,discount\n"
        f"A-1,{first_date},C-1,North,Analytics,Insight Pro,1,{first_price},0\n"
        f"A-2,{second_date},C-2,South,Services,Advisory,1,20,0\n"
    ).encode()
    assert client.post(
        "/api/data/upload",
        files={"file": ("comparison.csv", content, "text/csv")},
    ).status_code == 200

    response = client.post(
        "/api/insights/query",
        json={"question": "Why did revenue change in the latest month?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence"][0]["value"] is None
    assert expected_text in payload["answer"]


def test_upload_rejects_invalid_schema(client) -> None:
    response = client.post(
        "/api/data/upload",
        files={"file": ("bad.csv", b"order_id,amount\nA-1,10\n", "text/csv")},
    )
    assert response.status_code == 422
    assert any("Missing required columns" in issue for issue in response.json()["detail"])


def test_upload_rejects_normalized_duplicate_headers_as_validation_error(client) -> None:
    content = (
        b"order_id,order-id,order_date,customer_id,region,category,product,quantity,unit_price,discount\n"
        b"A-1,A-2,2026-01-01,C-1,North,Analytics,Insight Pro,1,10,0\n"
    )
    response = client.post(
        "/api/data/upload",
        files={"file": ("duplicate-headers.csv", content, "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == [
        "Column names collide after normalization: order_id."
    ]


def test_upload_rejects_exact_duplicate_headers_before_pandas_mangling(client) -> None:
    content = (
        b'\xef\xbb\xbf"order_id","order_id",order_date,customer_id,region,category,'
        b"product,quantity,unit_price,discount\n"
        b"A-1,A-2,2026-01-01,C-1,North,Analytics,Insight Pro,1,10,0\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("exact-duplicate-headers.csv", content, "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == [
        "Column names collide after normalization: order_id."
    ]


def test_legacy_upload_rejects_rows_wider_than_the_header(client) -> None:
    content = (
        b"order_id,order_date,customer_id,region,category,product,quantity,unit_price,discount\n"
        b"EXTRA,A-1,2026-01-01,C-1,North,Hardware,Widget,2,10,0.1\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("ragged.csv", content, "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == [
        "Data row 1 has 10 fields; the header defines 9."
    ]


def test_legacy_upload_does_not_infer_provenance_from_order_id_prefix(client) -> None:
    content = (
        b"order_id,order_date,customer_id,region,category,product,quantity,unit_price,discount\n"
        b"UCI-SPOOF,2026-01-01,C-1,North,Hardware,Widget,2,10,0\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("ordinary.csv", content, "text/csv")},
    )
    profile = client.get("/api/data/profile")

    assert response.status_code == 200
    assert profile.status_code == 200
    assert profile.json()["dataset_name"] == "Uploaded order-level sales"
    assert profile.json()["aggregate_record_proxy"] is False
    assert profile.json()["record_count_label"] == "Orders"
    assert profile.json()["currency"] == "USD"


def test_legacy_prepared_profile_rejects_conflicting_currency(
    client, monkeypatch
) -> None:
    monkeypatch.setitem(
        data_api.KNOWN_SOURCE_EXPECTED_SUMMARIES,
        "uci",
        (1, date(2009, 12, 1), date(2009, 12, 1)),
    )
    content = (
        b"order_id,order_date,customer_id,region,category,product,quantity,unit_price,discount\n"
        b"UCI-00000001,2009-12-01,UCI-12345,UK,Online Retail,Daily online retail basket,2,10,0\n"
    )

    response = client.post(
        "/api/data/upload",
        data={"source_profile": "uci", "source_currency": "USD"},
        files={"file": ("uci.csv", content, "text/csv")},
    )

    assert response.status_code == 422
    assert "uses GBP" in " ".join(response.json()["detail"])


def test_legacy_upload_rejects_extra_currency_column_before_relabelling(client) -> None:
    content = (
        b"order_id,order_date,customer_id,region,category,product,quantity,unit_price,discount,currency\n"
        b"A-1,2026-01-01,C-1,North,Hardware,Widget,2,10,0,GBP\n"
    )

    response = client.post(
        "/api/data/upload",
        data={"source_currency": "USD"},
        files={"file": ("extra-currency.csv", content, "text/csv")},
    )

    assert response.status_code == 422
    assert "unexpected columns: currency" in " ".join(response.json()["detail"])


def test_csv_upload_preserves_na_like_identity_literals(client) -> None:
    content = (
        b"order_id,order_date,customer_id,region,category,product,quantity,unit_price,discount\n"
        b"NULL,2026-01-01,NA,N/A,NaN,NULL,1,10,0\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("na-like-identities.csv", content, "text/csv")},
    )

    assert response.status_code == 200
    with SessionLocal() as session:
        record = session.scalar(select(SalesRecord))
    assert record is not None
    assert record.order_id == "NULL"
    assert record.customer_id == "NA"
    assert record.region == "N/A"
    assert record.category == "NaN"
    assert record.product == "NULL"


def test_csv_upload_still_rejects_genuinely_blank_identity(client) -> None:
    content = (
        b"order_id,order_date,customer_id,region,category,product,quantity,unit_price,discount\n"
        b"A-1,2026-01-01,,North,Analytics,Insight Pro,1,10,0\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("blank-identity.csv", content, "text/csv")},
    )

    assert response.status_code == 422
    assert "Column 'customer_id' has 1 blank values." in response.json()["detail"]


def test_csv_upload_rejects_postgresql_unsafe_nul_identity(client) -> None:
    content = (
        b"order_id,order_date,customer_id,region,category,product,quantity,unit_price,discount\n"
        b"A-1,2026-01-01,C-1,North,Analytics,Unsafe\x00Product,1,10,0\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("nul-identity.csv", content, "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == [
        "The uploaded CSV contains a NUL control character."
    ]


def test_csv_upload_preserves_leading_zero_ids_and_compact_calendar_date(client) -> None:
    content = (
        b"order_id,order_date,customer_id,region,category,product,quantity,unit_price,discount\n"
        b"0001,20260101,0007,001,Analytics,Insight Pro,1,10,0\n"
    )

    response = client.post(
        "/api/data/upload",
        files={"file": ("identity-strings.csv", content, "text/csv")},
    )

    assert response.status_code == 200
    with SessionLocal() as session:
        record = session.scalar(select(SalesRecord))
    assert record is not None
    assert record.order_id == "0001"
    assert record.customer_id == "0007"
    assert record.region == "001"
    assert record.order_date.isoformat() == "2026-01-01"


def test_upload_rejects_values_longer_than_database_contract(client) -> None:
    content = (
        "order_id,order_date,customer_id,region,category,product,quantity,unit_price,discount\n"
        f"{'X' * 81},2026-01-01,C-1,North,Analytics,Insight Pro,1,10,0\n"
    ).encode()
    response = client.post(
        "/api/data/upload",
        files={"file": ("too-long.csv", content, "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == [
        "Column 'order_id' has 1 values longer than 80 characters."
    ]


def test_upload_disables_append_before_combined_totals_can_become_unsafe(client) -> None:
    header = (
        "order_id,order_date,customer_id,region,category,product,quantity,"
        "unit_price,discount\n"
    )

    def batch(prefix: str) -> bytes:
        rows = "".join(
            f"{prefix}-{index},2026-01-01,C-{prefix}-{index},North,Analytics,"
            "Extreme,50,1000000000000,0\n"
            for index in range(12)
        )
        return (header + rows).encode()

    first = client.post(
        "/api/data/upload",
        files={"file": ("first.csv", batch("A"), "text/csv")},
    )
    append = client.post(
        "/api/data/upload?replace=false",
        files={"file": ("second.csv", batch("B"), "text/csv")},
    )

    assert first.status_code == 200
    assert first.json()["revenue_total"] == 600_000_000_000_000
    assert append.status_code == 400
    assert "Append ingestion is disabled" in append.json()["detail"]
    kpis = client.get("/api/analytics/kpis")
    assert kpis.status_code == 200
    assert kpis.json()["total_revenue"] == 600_000_000_000_000


def test_dashboard_remains_serializable_at_high_but_supported_values(client) -> None:
    header = (
        "order_id,order_date,customer_id,region,category,product,quantity,"
        "unit_price,discount\n"
    )
    rows = "".join(
        f"HIGH-{index},2026-{index // 4 + 1:02d}-01,C-{index},North,Analytics,"
        f"Extreme,{20 + index % 5},1000000000000,0\n"
        for index in range(24)
    )
    upload = client.post(
        "/api/data/upload",
        files={"file": ("high-values.csv", (header + rows).encode(), "text/csv")},
    )

    assert upload.status_code == 200
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    payload = response.json()
    assert payload["kpis"]["total_revenue"] < 1_000_000_000_000_000
    assert payload["forecast"]["evaluation"]["rmse"] >= 0


def test_analytics_requires_loaded_data(client) -> None:
    response = client.get("/api/analytics/kpis")
    assert response.status_code == 409


@pytest.mark.parametrize(
    ("question", "expected_tool"),
    [
        ("Forecast revenue for the next quarter", "revenue_forecast"),
        ("Which customer segments create the most value?", "customer_segments"),
        ("Show me unusual transactions to investigate", "sales_anomalies"),
    ],
)
def test_specialist_agent_routes_are_grounded(client, question, expected_tool) -> None:
    assert client.post("/api/data/demo").status_code == 200
    response = client.post("/api/insights/query", json={"question": question})
    assert response.status_code == 200
    payload = response.json()
    assert payload["tools_used"] == [expected_tool]
    assert payload["evidence"]


def test_next_quarter_forecast_returns_all_months_and_total(client) -> None:
    assert client.post("/api/data/demo").status_code == 200

    response = client.post(
        "/api/insights/query",
        json={"question": "Forecast revenue for the next quarter"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tools_used"] == ["revenue_forecast"]
    forecast_evidence = payload["evidence"][0]
    assert forecast_evidence["metric"] == "next_quarter_forecast"
    forecast_value = forecast_evidence["value"]
    assert len(forecast_value["periods"]) == 3
    assert forecast_value["total_revenue"] == round(
        sum(period["revenue"] for period in forecast_value["periods"]), 2
    )
    for period in forecast_value["periods"]:
        assert period["period"] in payload["answer"]
    assert "three-month revenue forecast" in payload["answer"]
    assert "totaling" in payload["answer"]
    assert "not a joint quarter-level prediction interval" in payload["answer"]


def test_ml_and_executive_report_endpoints(client) -> None:
    assert client.post("/api/data/demo").status_code == 200
    assert client.get("/api/ml/forecast?horizon=3").status_code == 200
    assert client.get("/api/ml/segments").status_code == 200
    assert client.get("/api/ml/anomalies?limit=5").status_code == 200

    report = client.get("/api/reports/executive")
    assert report.status_code == 200
    payload = report.json()
    assert payload["evidence"]
    assert "Executive Agent" in payload["agents_used"]
    assert len(payload["recommendations"]) == 4


def test_invalid_breakdown_dimension_is_rejected(client) -> None:
    assert client.post("/api/data/demo").status_code == 200
    response = client.get("/api/analytics/breakdown/unsupported")
    assert response.status_code == 400


def test_dashboard_filters_share_one_backend_contract(client) -> None:
    assert client.post("/api/data/demo").status_code == 200
    options = client.get("/api/analytics/filter-options")
    assert options.status_code == 200
    payload = options.json()
    assert payload["regions"]
    assert payload["categories"]
    assert payload["products"]
    profile = client.get("/api/data/profile").json()
    assert payload["dataset_version"]["content_sha256"] == profile["content_sha256"]
    assert payload["dataset_version"]["currency"] == profile["currency"]
    assert len(payload["dataset_version"]["profile_sha256"]) == 64
    assert payload["dataset_version"] == profile["dataset_version"]

    dashboard = client.get("/api/dashboard").json()
    assert dashboard["dataset_version"] == payload["dataset_version"]

    region = payload["regions"][0]
    filtered = client.get("/api/analytics/kpis", params={"region": region})
    assert filtered.status_code == 200
    region_breakdown = client.get("/api/analytics/breakdown/region").json()
    expected = next(row for row in region_breakdown if row["name"] == region)
    assert filtered.json()["total_revenue"] == expected["revenue"]
    report = client.get("/api/reports/executive", params={"region": region})
    assert report.status_code == 200
    assert report.json()["kpis"]["total_revenue"] == expected["revenue"]

    missing = client.get("/api/analytics/kpis", params={"region": "Not a region"})
    assert missing.status_code == 404
    invalid_dates = client.get(
        "/api/analytics/kpis",
        params={"start_date": "2025-01-02", "end_date": "2025-01-01"},
    )
    assert invalid_dates.status_code == 400


def test_dashboard_bundle_reuses_one_snapshot_and_degrades_small_models(client) -> None:
    assert client.post("/api/data/demo").status_code == 200
    first = build_demo_frame().iloc[0]
    params = {
        "start_date": first["order_date"].date().isoformat(),
        "end_date": first["order_date"].date().isoformat(),
        "region": first["region"],
        "category": first["category"],
        "product": first["product"],
    }
    sales_queries: list[str] = []

    def capture_sales_select(_, __, statement, ___, ____, _____):
        normalized = statement.upper()
        if normalized.startswith("SELECT") and "FROM SALES_RECORDS" in normalized:
            sales_queries.append(statement)

    event.listen(engine, "before_cursor_execute", capture_sales_select)
    try:
        response = client.get("/api/dashboard", params=params)
    finally:
        event.remove(engine, "before_cursor_execute", capture_sales_select)

    assert response.status_code == 200
    payload = response.json()
    assert payload["kpis"]["order_count"] >= 1
    assert payload["kpis"]["month_over_month_available"] is False
    assert payload["kpis"]["month_over_month_change_pct"] is None
    assert payload["forecast"] is None
    assert "forecast" in payload["model_errors"]
    assert payload["trends"]
    assert payload["regions"]
    assert payload["products"]
    assert len(payload["products"]) <= 10
    assert len(sales_queries) == 1


def test_dashboard_preserves_complete_monthly_aggregate_semantics(
    client, monkeypatch
) -> None:
    header = (
        "order_id,order_date,customer_id,region,category,product,quantity,"
        "unit_price,discount\n"
    )
    rows = "".join(
        f"IA2024-{((month - 1) * 2 + store):08d},2024-{month:02d}-01,"
        f"IA-STORE-{store},Iowa,Liquor,Monthly spirits basket,1,"
        f"{month * 10 + store},0\n"
        for month in range(1, 13)
        for store in (1, 2)
    )
    monkeypatch.setitem(
        data_api.KNOWN_SOURCE_EXPECTED_SUMMARIES,
        "iowa",
        (24, date(2024, 1, 1), date(2024, 12, 1)),
    )
    assert client.post(
        "/api/data/upload",
        data={"source_profile": "iowa"},
        files={"file": ("iowa-monthly.csv", (header + rows).encode(), "text/csv")},
    ).status_code == 200

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["kpis"]["month_over_month_available"] is True
    assert payload["kpis"]["month_over_month_status"] == "available"
    assert payload["kpis"]["record_semantics"]["aggregate_record_proxy"] is True
    assert payload["kpis"]["record_semantics"]["entity_count_label"] == "Stores"
    assert payload["forecast"]["input_grain"] == "monthly_aggregate"
    assert payload["forecast"]["excluded_periods"] == []
    assert payload["forecast"]["forecast"][0]["period"] == "2025-01"

    insight = client.post(
        "/api/insights/query",
        json={"question": "What was average order value?"},
    )
    assert insight.status_code == 200
    assert "average aggregate record value" in insight.json()["answer"].lower()
    assert "not source average order value" in insight.json()["answer"].lower()

    segment = client.post(
        "/api/insights/query", json={"question": "Show store segments"}
    )
    anomaly = client.post(
        "/api/insights/query", json={"question": "Show unusual transactions"}
    )
    report = client.get("/api/reports/executive")
    assert segment.status_code == 200
    assert "stores" in segment.json()["answer"].lower()
    assert "source stores" in segment.json()["answer"].lower()
    assert anomaly.status_code == 200
    assert "store-county-category-month records" in anomaly.json()["answer"].lower()
    assert report.status_code == 200
    assert "high-value stores" in " ".join(report.json()["recommendations"]).lower()


def test_active_profile_currency_overrides_insight_and_report_relabelling(client) -> None:
    assert client.post("/api/data/demo").status_code == 200
    insight = client.post(
        "/api/insights/query",
        json={"question": "What was total revenue?", "currency": "GBP"},
    )
    report = client.get("/api/reports/executive", params={"currency": "GBP"})
    invalid = client.post(
        "/api/insights/query",
        json={"question": "What was total revenue?", "currency": "EUR"},
    )

    assert insight.status_code == 200
    assert "$" in insight.json()["answer"]
    assert "£" not in insight.json()["answer"]
    assert report.status_code == 200
    assert "$" in report.json()["summary"]
    assert "£" not in report.json()["summary"]
    assert invalid.status_code == 422


def test_specialists_and_executive_report_degrade_on_narrow_filters(client) -> None:
    assert client.post("/api/data/demo").status_code == 200
    first = build_demo_frame().iloc[0]
    params = {
        "start_date": first["order_date"].date().isoformat(),
        "end_date": first["order_date"].date().isoformat(),
        "region": first["region"],
        "category": first["category"],
        "product": first["product"],
    }

    insight = client.post(
        "/api/insights/query",
        params=params,
        json={"question": "Forecast revenue for the next quarter"},
    )
    report = client.get("/api/reports/executive", params=params)

    assert insight.status_code == 200
    insight_payload = insight.json()
    assert insight_payload["tools_used"] == []
    assert "unavailable for the current selection" in insight_payload["answer"]
    assert insight_payload["evidence"][0]["metric"] == "forecast_unavailable"
    assert insight_payload["evidence"][0]["value"]["available"] is False

    assert report.status_code == 200
    report_payload = report.json()
    assert report_payload["kpis"]["order_count"] >= 1
    assert report_payload["kpis"]["month_over_month_change_pct"] is None
    assert report_payload["recommendations"][0].startswith("Load at least two")
    assert "Executive Agent" in report_payload["agents_used"]
    unavailable = [
        item
        for item in report_payload["evidence"]
        if item["source"] == "agent.data_precondition"
    ]
    assert unavailable
    assert all(item["value"]["available"] is False for item in unavailable)
    assert all(
        recommendation.startswith("Expand the data window")
        for recommendation in report_payload["recommendations"][1:]
    )
