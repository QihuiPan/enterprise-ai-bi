from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.agents.orchestrator import AgentOrchestrator
from backend.app.currency import CurrencyCode, resolve_source_currency
from backend.app.services.business import BusinessIntelligence
from backend.app.services.filtering import SalesFilters


def executive_report(
    session: Session,
    filters: SalesFilters | None = None,
    currency: CurrencyCode = "USD",
) -> dict:
    currency = resolve_source_currency(session, currency)
    business = BusinessIntelligence(session, filters)
    metrics = business.analytics.kpis()
    semantics = metrics["record_semantics"]
    entity_label = semantics["entity_count_label"].lower()
    insight = AgentOrchestrator(business, currency).answer(
        "Create an executive business performance overview"
    )
    recommendations: list[str] = []
    month_change = metrics["month_over_month_change_pct"]
    if metrics["month_over_month_status"] == "insufficient_history":
        recommendations.append(
            "Load at least two monthly periods before drawing a month-over-month "
            "performance conclusion."
        )
    elif metrics["month_over_month_status"] == "zero_baseline":
        recommendations.append(
            "Use the absolute revenue change because the previous month was zero "
            "and a percentage comparison is undefined."
        )
    elif metrics["month_over_month_status"] == "non_consecutive_periods":
        recommendations.append(
            "Load consecutive monthly periods before drawing a month-over-month "
            "performance conclusion."
        )
    elif metrics["month_over_month_status"] == "partial_periods":
        recommendations.append(
            "Complete both observed monthly periods before drawing a "
            "month-over-month performance conclusion."
        )
    elif month_change < -5:
        recommendations.append(
            "Review the weakest region and category contributors before changing "
            "the forecast baseline."
        )
    else:
        recommendations.append(
            "Validate whether the latest growth is broad-based across regions and "
            "categories."
        )
    tools_used = set(insight["tools_used"])
    recommendations.append(
        "Prioritize evidence-based retention or expansion review for high-value "
        f"{entity_label}."
        if "customer_segments" in tools_used
        else f"Expand the data window before using {entity_label} segmentation to "
        "plan business actions."
    )
    recommendations.append(
        "Investigate ranked anomalies with source-system context before labeling "
        "them as errors."
        if "sales_anomalies" in tools_used
        else "Expand the data window before using anomaly rankings to prioritize "
        "record review."
    )
    recommendations.append(
        "Re-train and compare the forecasting baseline after each complete "
        "reporting period."
        if "revenue_forecast" in tools_used
        else "Expand the data window before using a forecasting baseline for "
        "planning."
    )
    return {
        "title": "Executive Business Intelligence Report",
        "generated_at": datetime.now(UTC).isoformat(),
        "kpis": metrics,
        "summary": insight["answer"],
        "recommendations": recommendations,
        "agents_used": insight["agents_used"],
        "evidence": insight["evidence"],
    }
