from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.agents.orchestrator import answer_question
from backend.app.services.analytics import kpis


def executive_report(session: Session) -> dict:
    metrics = kpis(session)
    insight = answer_question("Create an executive business performance overview", session)
    recommendations: list[str] = []
    if metrics["month_over_month_change_pct"] < -5:
        recommendations.append(
            "Review the weakest region and category contributors before changing "
            "the forecast baseline."
        )
    else:
        recommendations.append(
            "Validate whether the latest growth is broad-based across regions and categories."
        )
    recommendations.extend(
        [
            "Protect high-value customer relationships with targeted retention "
            "and expansion actions.",
            "Investigate ranked anomalies with source-system context before "
            "labeling them as errors.",
            "Re-train and compare the forecasting baseline after each complete reporting period.",
        ]
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
