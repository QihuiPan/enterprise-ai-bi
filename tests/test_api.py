from __future__ import annotations

import pytest


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


def test_upload_rejects_invalid_schema(client) -> None:
    response = client.post(
        "/api/data/upload",
        files={"file": ("bad.csv", b"order_id,amount\nA-1,10\n", "text/csv")},
    )
    assert response.status_code == 400
    assert "Missing required columns" in response.json()["detail"]


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
