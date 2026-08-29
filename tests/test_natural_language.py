from __future__ import annotations

import pandas as pd
import pytest

from backend.app.services.analytics import SalesAnalytics
from backend.app.services.natural_language import (
    ApprovedAnalyticsService,
    BusinessQuestionParser,
)
from data_pipeline.sample import build_demo_frame


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "Show the top 5 products by revenue in 2025",
            {
                "operation": "ranking",
                "metric": "revenue",
                "dimension": "product",
                "direction": "desc",
                "limit": 5,
                "period_kind": "year",
            },
        ),
        (
            "Bottom 3 regions by units for the latest 6 months",
            {
                "operation": "ranking",
                "metric": "units",
                "dimension": "region",
                "direction": "asc",
                "limit": 3,
                "period_kind": "trailing_months",
            },
        ),
        (
            "Show the monthly order trend in 2026",
            {
                "operation": "trend",
                "metric": "orders",
                "dimension": None,
                "direction": "desc",
                "limit": None,
                "period_kind": "year",
            },
        ),
        (
            "2026年營收最高的前3個品類",
            {
                "operation": "ranking",
                "metric": "revenue",
                "dimension": "category",
                "direction": "desc",
                "limit": 3,
                "period_kind": "year",
            },
        ),
    ],
)
def test_parser_maps_bounded_business_questions(question, expected) -> None:
    query = BusinessQuestionParser().parse(question)
    assert query is not None
    actual = {
        "operation": query.operation,
        "metric": query.metric,
        "dimension": query.dimension,
        "direction": query.direction,
        "limit": query.limit,
        "period_kind": query.period.kind,
    }
    assert actual == expected


def test_parser_caps_rankings_and_preserves_legacy_change_questions() -> None:
    capped = BusinessQuestionParser().parse("Top 500 customers by sales")
    assert capped is not None
    assert capped.limit == 20
    assert BusinessQuestionParser().parse("Why did revenue change last month?") is None
    assert not BusinessQuestionParser.requests_database_access(
        "Why did sales drop last quarter?"
    )
    update = BusinessQuestionParser().parse("Give me a sales update")
    assert update is not None
    assert update.operation == "summary"
    assert update.metric == "revenue"


@pytest.mark.parametrize(
    "question",
    [
        "Profit by region in 2026",
        "Average revenue by region",
        "Revenue per unit by product",
        "Revenue last week",
        "Weekly revenue trend",
        "Quarterly revenue trend",
        "Average units by product",
        "Median revenue by region",
        "Unit price by product",
        "Revenue share by region",
        "Revenue previous year",
    ],
)
def test_parser_does_not_substitute_revenue_for_unsupported_metrics(question) -> None:
    assert BusinessQuestionParser().parse(question) is None


@pytest.mark.parametrize(
    ("question", "expected_kind", "expected_value"),
    [
        ("What was revenue in 2025-Q4?", "quarter", "2025Q4"),
        ("2026 Q1 revenue", "quarter", "2026Q1"),
        ("2026年第2季度營收", "quarter", "2026Q2"),
        ("What was revenue last quarter?", "previous_quarter", None),
        ("上一季營收是多少？", "previous_quarter", None),
        ("Revenue for the current quarter", "latest_quarter", None),
        ("本季度營收", "latest_quarter", None),
    ],
)
def test_parser_supports_quarter_periods(
    question, expected_kind, expected_value
) -> None:
    query = BusinessQuestionParser().parse(question)

    assert query is not None
    assert query.period.kind == expected_kind
    assert query.period.value == expected_value


def test_previous_quarter_resolves_to_latest_complete_transaction_quarter() -> None:
    service = ApprovedAnalyticsService(SalesAnalytics(build_demo_frame()))

    result = service.answer("What was revenue last quarter?")

    assert result is not None
    period = result["query_plan"]["period"]
    assert period["kind"] == "previous_quarter"
    assert period["label"] == "latest complete data quarter (2026-Q2)"
    assert period["resolved_start"] == "2026-04-01"
    assert period["resolved_end"] == "2026-06-30"


def test_previous_quarter_treats_month_start_rows_as_monthly_aggregates() -> None:
    frame = build_demo_frame(rows=12)
    frame.loc[:, "order_date"] = pd.date_range("2025-01-01", periods=12, freq="MS")
    service = ApprovedAnalyticsService(SalesAnalytics(frame))

    result = service.answer("What was revenue last quarter?")

    assert result is not None
    period = result["query_plan"]["period"]
    assert period["label"] == "latest complete data quarter (2025-Q4)"
    assert period["resolved_start"] == "2025-10-01"
    assert period["resolved_end"] == "2025-12-31"


def test_previous_quarter_skips_filtered_partial_monthly_aggregate_quarter() -> None:
    frame = build_demo_frame(rows=12)
    frame.loc[:, "order_date"] = pd.date_range("2025-01-01", periods=12, freq="MS")
    frame.loc[:, "order_id"] = [f"IA2024-{index:04d}" for index in range(12)]
    filtered = frame[frame["order_date"] <= pd.Timestamp("2025-08-01")].copy()
    service = ApprovedAnalyticsService(SalesAnalytics(filtered))

    result = service.answer("What was revenue last quarter?")

    assert result is not None
    period = result["query_plan"]["period"]
    assert period["label"] == "latest complete data quarter (2025-Q2)"
    assert period["resolved_start"] == "2025-04-01"
    assert period["resolved_end"] == "2025-06-30"


def test_explicit_quarter_uses_calendar_quarter_boundaries() -> None:
    service = ApprovedAnalyticsService(SalesAnalytics(build_demo_frame()))

    result = service.answer("What was revenue in 2025-Q4?")

    assert result is not None
    period = result["query_plan"]["period"]
    assert period["kind"] == "quarter"
    assert period["label"] == "2025-Q4"
    assert period["resolved_start"] == "2025-10-01"
    assert period["resolved_end"] == "2025-12-31"


@pytest.mark.parametrize(
    "question",
    [
        "Run SQL SELECT * FROM sales_records",
        "DROP TABLE sales_records",
        "Update sales_records and set revenue to zero",
    ],
)
def test_database_requests_are_rejected_before_parsing(question) -> None:
    assert BusinessQuestionParser.requests_database_access(question)
    assert BusinessQuestionParser().parse(question) is None


def test_approved_service_returns_chart_plan_explanation_and_evidence() -> None:
    service = ApprovedAnalyticsService(SalesAnalytics(build_demo_frame()))
    result = service.answer("Top 4 categories by revenue for the latest 3 months")
    assert result is not None
    assert result["query_plan"]["read_only"] is True
    assert result["query_plan"]["limit"] == 4
    assert result["chart"]["type"] == "bar"
    assert result["chart"]["x_key"] == "category"
    assert result["chart"]["title"].startswith("Top Categories by Revenue")
    assert 1 <= len(result["chart"]["data"]) <= 4
    assert result["evidence"][0]["source"] == "analytics.approved_query"
    assert "no generated SQL" in result["explanation"]


def test_daily_trend_uses_correct_wording() -> None:
    service = ApprovedAnalyticsService(SalesAnalytics(build_demo_frame()))
    result = service.answer("Show daily revenue trend in June 2026")
    assert result is not None
    assert "daily revenue trend" in result["answer"]
    assert "dayly" not in result["answer"]
    assert result["chart"]["type"] == "line"


def test_long_daily_trend_discloses_result_truncation() -> None:
    service = ApprovedAnalyticsService(SalesAnalytics(build_demo_frame()))
    result = service.answer("Show the daily revenue trend for all available data")
    assert result is not None
    assert result["chart"]["truncated"] is True
    assert result["chart"]["total_points"] > len(result["chart"]["data"])
    assert len(result["chart"]["data"]) == 366
    assert result["query_plan"]["truncated"] is True
    assert "returns the latest 366 of" in result["answer"]


def test_large_breakdown_discloses_ranked_result_truncation() -> None:
    frame = build_demo_frame(rows=30)
    frame.loc[:, "product"] = [f"Product {index:02d}" for index in range(30)]
    service = ApprovedAnalyticsService(SalesAnalytics(frame))

    result = service.answer("Show revenue by product for all available data")

    assert result is not None
    assert len(result["chart"]["data"]) == 20
    assert result["chart"]["total_results"] == 30
    assert result["chart"]["truncated"] is True
    assert result["query_plan"]["total_results"] == 30
    assert "first 20 of 30 ranked results" in result["answer"]
    assert result["evidence"][0]["value"]["total_results"] == 30


def test_breakdown_truncation_survives_api_response_schema(client) -> None:
    header = (
        "order_id,order_date,customer_id,region,category,product,quantity,"
        "unit_price,discount\n"
    )
    rows = "".join(
        f"A-{index},2026-01-15,C-{index},North,Analytics,Product {index:02d},1,10,0\n"
        for index in range(30)
    )
    assert client.post(
        "/api/data/upload",
        files={"file": ("products.csv", (header + rows).encode(), "text/csv")},
    ).status_code == 200

    response = client.post(
        "/api/insights/query",
        json={"question": "Show revenue by product for all available data"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query_plan"]["total_results"] == 30
    assert payload["chart"]["total_results"] == 30
    assert payload["query_plan"]["truncated"] is True
    assert payload["chart"]["truncated"] is True


def test_approved_service_uses_selected_source_currency() -> None:
    service = ApprovedAnalyticsService(SalesAnalytics(build_demo_frame()), "GBP")
    result = service.answer("What was total revenue?")
    assert result is not None
    assert "£" in result["answer"]
    assert "$" not in result["answer"]


def test_insight_endpoint_executes_filter_aware_approved_query(client) -> None:
    assert client.post("/api/data/demo").status_code == 200
    params = {
        "region": "North",
        "start_date": "2026-01-01",
        "end_date": "2026-06-30",
    }
    expected = client.get("/api/analytics/kpis", params=params)
    response = client.post(
        "/api/insights/query",
        params=params,
        json={"question": "What was total revenue?"},
    )
    assert expected.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["tools_used"] == ["approved_analytics_query"]
    assert payload["query_plan"]["read_only"] is True
    assert payload["chart"]["data"][0]["revenue"] == expected.json()["total_revenue"]
    assert payload["evidence"][0]["value"]["query_plan"]["period"][
        "resolved_start"
    ] >= "2026-01-01"


def test_sql_policy_rejection_does_not_require_loaded_data(client) -> None:
    response = client.post(
        "/api/insights/query",
        json={"question": "Run SQL SELECT * FROM sales_records"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["tools_used"] == []
    assert payload["query_plan"] is None
    assert payload["evidence"][0]["value"]["executed"] is False
    assert "cannot execute SQL" in payload["answer"]


@pytest.mark.parametrize(
    "question",
    [
        "Profit by region in 2026",
        "Why did profit decline last quarter?",
        "Why did units drop last quarter?",
        "Why did revenue per customer decline?",
        "Average revenue by region",
        "Revenue per unit by product",
        "Forecast units next month",
        "Predict customer count",
        "Forecast profit",
        "Forecast cash flow next month",
        "Predict EBITDA",
        "Forecast headcount",
        "Segment products",
        "Segment employees",
        "Segment inventory",
        "Segment customers in 2024",
        "Show unusual customers",
        "Find unusual inventory",
        "Inventory anomaly",
        "Show anomalies last month",
        "Predict customer churn",
        "Executive profit report",
        "Executive report on inventory",
        "Executive report for 2024",
        "Why did revenue change by product?",
        "Why did revenue change in 2024?",
        "Why did revenue change in the latest 3 months?",
        "Forecast revenue by region next month",
        "Forecast revenue by product next month",
        "Forecast revenue for 2027",
        "Forecast next 6 months",
        "Forecast next year",
        "Revenue by salesperson",
        "Revenue last week",
        "Weekly revenue trend",
        "Quarterly revenue trend",
        "Average units by product",
        "Median revenue by region",
        "Unit price by product",
        "Revenue share by region",
        "Revenue previous year",
        "Revenue tomorrow",
        "Revenue year to date",
        "Revenue month to date",
        "Revenue in Q2",
        "Revenue by year",
        "Revenue by quarter",
        "Revenue for each quarter",
        "预测库存下个月",
        "销售员的营收",
        "按销售员看营收",
        "每周营收趋势",
        "平均销量按产品",
        "营收占比按地区",
        "營收同比",
        "营收环比",
        "今天營收",
        "昨日营收",
        "年度营收",
        "人均营收",
        "营收标准差",
        "營收百分位",
        "員工營收",
        "员工销售额",
        "各员工营收",
    ],
)
def test_unknown_or_unsupported_change_metric_returns_clarification(
    client, question
) -> None:
    assert client.post("/api/data/demo").status_code == 200

    response = client.post("/api/insights/query", json={"question": question})

    assert response.status_code == 200
    payload = response.json()
    assert payload["tools_used"] == []
    assert payload["query_plan"] is None
    assert payload["evidence"][0]["metric"] == "unsupported_business_metric"
    assert "could not map" in payload["answer"]
    assert "dashboard filters" in payload["answer"]
    assert "quarter over quarter" not in payload["answer"]


@pytest.mark.parametrize(
    ("question", "expected_tool"),
    [
        ("Forecast revenue for the next quarter", "revenue_forecast"),
        ("Which customer segments create the most value?", "customer_segments"),
        ("Show me unusual transactions to investigate", "sales_anomalies"),
        ("Show an anomaly review", "sales_anomalies"),
        ("Create an executive business performance overview", "revenue_forecast"),
        ("生成执行摘要", "revenue_forecast"),
        ("顯示經營概覽", "revenue_forecast"),
    ],
)
def test_supported_specialist_scopes_remain_available(
    client, question, expected_tool
) -> None:
    assert client.post("/api/data/demo").status_code == 200

    response = client.post("/api/insights/query", json={"question": question})

    assert response.status_code == 200
    payload = response.json()
    assert expected_tool in payload["tools_used"]
    assert payload["evidence"][0]["metric"] != "unsupported_business_metric"


@pytest.mark.parametrize(
    ("question", "previous_period", "current_period"),
    [
        ("Revenue dropped last month", "2026-04", "2026-05"),
        ("上月營收下降", "2026-04", "2026-05"),
        ("營收下降", "2026-05", "2026-06"),
    ],
)
def test_supported_change_verbs_route_to_the_requested_comparison_window(
    client, question, previous_period, current_period
) -> None:
    assert client.post("/api/data/demo").status_code == 200

    response = client.post("/api/insights/query", json={"question": question})

    assert response.status_code == 200
    payload = response.json()
    assert payload["tools_used"] == ["explain_revenue_change"]
    assert payload["query_plan"] is None
    context = payload["evidence"][0]["context"]
    assert context == f"{previous_period} compared with {current_period}"


def test_top_customers_uses_analytics_not_segmentation(client) -> None:
    assert client.post("/api/data/demo").status_code == 200
    response = client.post(
        "/api/insights/query",
        json={"question": "Top customers by revenue"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["tools_used"] == ["approved_analytics_query"]
    assert payload["query_plan"]["dimension"] == "customer"
    assert len(payload["chart"]["data"]) == 5


def test_revenue_summary_uses_approved_query_not_executive_agents(client) -> None:
    assert client.post("/api/data/demo").status_code == 200
    response = client.post(
        "/api/insights/query",
        json={"question": "Revenue summary for 2026"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["tools_used"] == ["approved_analytics_query"]
    assert payload["query_plan"]["operation"] == "summary"
    assert payload["agents_used"] == ["Data Analyst Agent"]
