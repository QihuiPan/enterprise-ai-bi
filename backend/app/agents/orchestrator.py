from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.services import analytics, machine_learning


def _currency(value: float) -> str:
    return f"${value:,.2f}"


def _analyst_result(session: Session) -> tuple[str, list[dict], list[str]]:
    change = analytics.explain_revenue_change(session)
    direction = "rose" if change["change"] >= 0 else "fell"
    region = change["contributors"]["region"][0]
    category = change["contributors"]["category"][0]
    answer = (
        f"Revenue {direction} {abs(change['change_pct']):.2f}% from "
        f"{change['previous_period']} to {change['current_period']} "
        f"({_currency(change['previous_revenue'])} to {_currency(change['current_revenue'])}). "
        f"The weakest regional contribution was {region['name']} "
        f"({_currency(region['change'])}), while the weakest category contribution was "
        f"{category['name']} ({_currency(category['change'])})."
    )
    evidence = [
        {
            "source": "analytics.explain_revenue_change",
            "metric": "month_over_month_change_pct",
            "value": change["change_pct"],
            "context": f"{change['previous_period']} compared with {change['current_period']}",
        },
        {
            "source": "analytics.explain_revenue_change",
            "metric": "weakest_region_change",
            "value": region,
            "context": "Revenue change by region in the same comparison window",
        },
        {
            "source": "analytics.explain_revenue_change",
            "metric": "weakest_category_change",
            "value": category,
            "context": "Revenue change by category in the same comparison window",
        },
    ]
    return answer, evidence, ["explain_revenue_change"]


def _forecast_result(session: Session) -> tuple[str, list[dict], list[str]]:
    result = machine_learning.revenue_forecast(session, horizon=3)
    first = result["forecast"][0]
    metrics = result["evaluation"]
    answer = (
        f"The linear baseline forecasts {_currency(first['revenue'])} for {first['period']}, "
        f"with a residual-based 95% range of {_currency(first['lower_95'])} to "
        f"{_currency(first['upper_95'])}. Holdout MAE is {_currency(metrics['mae'])}; "
        "treat the forecast as a baseline rather than causal certainty."
    )
    evidence = [
        {
            "source": "ml.forecast_revenue",
            "metric": "next_month_forecast",
            "value": first,
            "context": result["caveat"],
        },
        {
            "source": "ml.forecast_revenue",
            "metric": "holdout_evaluation",
            "value": metrics,
            "context": "Metrics were calculated on the latest held-out months.",
        },
    ]
    return answer, evidence, ["revenue_forecast"]


def _customer_result(session: Session) -> tuple[str, list[dict], list[str]]:
    result = machine_learning.customer_segments(session)
    leading = result["segments"][0]
    answer = (
        f"The highest-revenue segment is {leading['name']}, containing "
        f"{leading['customers']} customers and {_currency(leading['total_revenue'])} in observed "
        "revenue. Segment labels rank observed monetary value and should guide, not replace, "
        "customer-level review."
    )
    evidence = [
        {
            "source": "ml.segment_customers",
            "metric": "segment_summary",
            "value": result["segments"],
            "context": result["method"],
        }
    ]
    return answer, evidence, ["customer_segments"]


def _anomaly_result(session: Session) -> tuple[str, list[dict], list[str]]:
    result = machine_learning.sales_anomalies(session, limit=5)
    top = result["anomalies"][0] if result["anomalies"] else None
    top_text = (
        f" The highest-ranked record is {top['order_id']} with revenue {_currency(top['revenue'])}."
        if top
        else ""
    )
    answer = (
        f"Isolation Forest flagged {result['anomaly_count']} of "
        f"{result['records_evaluated']} transactions for investigation.{top_text} "
        "A flag indicates statistical unusualness, not fraud or an error."
    )
    evidence = [
        {
            "source": "ml.detect_anomalies",
            "metric": "ranked_anomalies",
            "value": result["anomalies"],
            "context": result["method"],
        }
    ]
    return answer, evidence, ["sales_anomalies"]


def answer_question(question: str, session: Session) -> dict:
    normalized = question.lower()
    requested: list[str]
    if any(term in normalized for term in ("executive", "report", "overview", "summary")):
        requested = ["analyst", "forecast", "customer", "anomaly"]
    elif any(term in normalized for term in ("forecast", "predict", "future", "next month")):
        requested = ["forecast"]
    elif any(term in normalized for term in ("customer", "segment", "rfm", "churn")):
        requested = ["customer"]
    elif any(term in normalized for term in ("anomaly", "unusual", "outlier", "fraud")):
        requested = ["anomaly"]
    else:
        requested = ["analyst"]

    handlers = {
        "analyst": ("Data Analyst Agent", _analyst_result),
        "forecast": ("Forecasting Agent", _forecast_result),
        "customer": ("Customer Intelligence Agent", _customer_result),
        "anomaly": ("Anomaly Detection Agent", _anomaly_result),
    }
    answers: list[str] = []
    evidence: list[dict] = []
    tools: list[str] = []
    agents: list[str] = []
    for key in requested:
        agent_name, handler = handlers[key]
        answer, agent_evidence, agent_tools = handler(session)
        answers.append(answer)
        evidence.extend(agent_evidence)
        tools.extend(agent_tools)
        agents.append(agent_name)

    if len(requested) > 1:
        agents.append("Executive Agent")
    return {
        "question": question,
        "answer": " ".join(answers),
        "agents_used": agents,
        "tools_used": tools,
        "evidence": evidence,
        "generated_at": datetime.now(UTC).isoformat(),
    }
