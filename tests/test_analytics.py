from __future__ import annotations

import pandas as pd

from backend.app.services.analytics import SalesAnalytics
from data_pipeline.sample import build_demo_frame


def test_demo_frame_carries_its_declared_complete_date_boundaries() -> None:
    frame = build_demo_frame()

    assert frame["order_date"].min().date().isoformat() == "2024-07-01"
    assert frame["order_date"].max().date().isoformat() == "2026-06-30"
    assert SalesAnalytics(frame).kpis()["month_over_month_available"] is True


def test_average_order_value_aggregates_multi_line_orders() -> None:
    frame = build_demo_frame(rows=3)
    frame.loc[1, "order_id"] = frame.loc[0, "order_id"]
    order_totals = frame.groupby("order_id")["revenue"].sum()

    kpis = SalesAnalytics(frame).kpis()

    assert kpis["order_count"] == 2
    assert kpis["average_order_value"] == round(float(order_totals.mean()), 2)
    assert kpis["average_order_value"] != round(float(frame["revenue"].mean()), 2)


def test_zero_previous_month_does_not_claim_zero_percent_change() -> None:
    frame = build_demo_frame(rows=2)
    frame.loc[:, "order_date"] = ["2026-01-15", "2026-02-15"]
    frame["order_date"] = frame["order_date"].astype("datetime64[ns]")
    frame.loc[0, "revenue"] = 0.0

    analytics = SalesAnalytics(frame)
    kpis = analytics.kpis()
    change = analytics.explain_revenue_change()

    assert kpis["month_over_month_change_pct"] is None
    assert kpis["month_over_month_available"] is False
    assert kpis["month_over_month_status"] == "zero_baseline"
    assert change["change_pct"] is None
    assert change["change_pct_available"] is False


def test_non_consecutive_periods_are_not_labeled_month_over_month() -> None:
    frame = build_demo_frame(rows=2)
    frame.loc[:, "order_date"] = ["2026-01-15", "2026-03-15"]
    frame["order_date"] = frame["order_date"].astype("datetime64[ns]")

    analytics = SalesAnalytics(frame)
    kpis = analytics.kpis()
    change = analytics.explain_revenue_change()

    assert kpis["month_over_month_change_pct"] is None
    assert kpis["month_over_month_status"] == "non_consecutive_periods"
    assert change["change_pct"] is None
    assert change["comparison_status"] == "non_consecutive_periods"


def test_partial_months_do_not_produce_month_over_month_percentage() -> None:
    frame = build_demo_frame(rows=2)
    frame.loc[:, "order_date"] = ["2026-01-31", "2026-02-01"]
    frame["order_date"] = frame["order_date"].astype("datetime64[ns]")

    analytics = SalesAnalytics(frame)
    kpis = analytics.kpis()
    change = analytics.explain_revenue_change()

    assert kpis["month_over_month_change_pct"] is None
    assert kpis["month_over_month_status"] == "partial_periods"
    assert change["change_pct"] is None
    assert change["comparison_status"] == "partial_periods"
    assert all(not item["complete"] for item in change["period_coverage"])


def test_last_quarter_uses_latest_two_complete_quarters() -> None:
    analytics = SalesAnalytics(build_demo_frame())

    change = analytics.explain_revenue_change("quarter", completed_only=True)

    assert change["previous_period"] == "2026-Q1"
    assert change["current_period"] == "2026-Q2"
    assert change["completed_periods_only"] is True
    assert all(item["complete"] for item in change["period_coverage"])


def test_filtered_monthly_aggregates_exclude_partial_quarter_from_change() -> None:
    frame = build_demo_frame(rows=12)
    frame.loc[:, "order_date"] = pd.date_range("2025-01-01", periods=12, freq="MS")
    frame.loc[:, "order_id"] = [f"IA2024-{index:04d}" for index in range(12)]
    filtered = frame[frame["order_date"] <= pd.Timestamp("2025-08-01")].copy()

    change = SalesAnalytics(filtered).explain_revenue_change(
        "quarter", completed_only=True
    )

    assert change["previous_period"] == "2025-Q1"
    assert change["current_period"] == "2025-Q2"
    assert all(item["complete"] for item in change["period_coverage"])


def test_monthly_aggregate_year_requires_all_twelve_month_labels() -> None:
    frame = build_demo_frame(rows=12)
    frame.loc[:, "order_date"] = pd.date_range("2025-01-01", periods=12, freq="MS")
    analytics = SalesAnalytics(frame.iloc[:-1].copy())

    assert analytics._period_coverage(pd.Period("2025", freq="Y"))["complete"] is False
    assert (
        SalesAnalytics(frame)._period_coverage(pd.Period("2025", freq="Y"))[
            "complete"
        ]
        is True
    )
