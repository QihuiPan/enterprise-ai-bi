from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.services.business import BusinessIntelligence

AgentResult = tuple[str, list[dict], list[str]]


def _currency(value: float) -> str:
    return f"${value:,.2f}"


@dataclass(frozen=True)
class AgentSpec:
    name: str
    handler: Callable[[], AgentResult]


class AgentOrchestrator:
    """Routes questions to registered, read-only analytical specialists."""

    INTENT_TERMS = {
        "executive": ("executive", "report", "overview", "summary"),
        "forecast": ("forecast", "predict", "future", "next month"),
        "customer": ("customer", "segment", "rfm", "churn"),
        "anomaly": ("anomaly", "unusual", "outlier", "fraud"),
    }
    EXECUTIVE_SEQUENCE = ("analyst", "forecast", "customer", "anomaly")

    def __init__(self, business: BusinessIntelligence):
        self.business = business
        self.handlers = {
            "analyst": AgentSpec("Data Analyst Agent", self._analyst_result),
            "forecast": AgentSpec("Forecasting Agent", self._forecast_result),
            "customer": AgentSpec(
                "Customer Intelligence Agent", self._customer_result
            ),
            "anomaly": AgentSpec("Anomaly Detection Agent", self._anomaly_result),
        }

    def _select_agents(self, question: str) -> tuple[str, ...]:
        normalized = question.lower()
        if any(term in normalized for term in self.INTENT_TERMS["executive"]):
            return self.EXECUTIVE_SEQUENCE
        for intent in ("forecast", "customer", "anomaly"):
            if any(term in normalized for term in self.INTENT_TERMS[intent]):
                return (intent,)
        return ("analyst",)

    def _analyst_result(self) -> AgentResult:
        change = self.business.analytics.explain_revenue_change()
        direction = "rose" if change["change"] >= 0 else "fell"
        region = change["contributors"]["region"][0]
        category = change["contributors"]["category"][0]
        answer = (
            f"Revenue {direction} {abs(change['change_pct']):.2f}% from "
            f"{change['previous_period']} to {change['current_period']} "
            f"({_currency(change['previous_revenue'])} to "
            f"{_currency(change['current_revenue'])}). The weakest regional "
            f"contribution was {region['name']} ({_currency(region['change'])}), "
            f"while the weakest category contribution was {category['name']} "
            f"({_currency(category['change'])})."
        )
        evidence = [
            {
                "source": "analytics.explain_revenue_change",
                "metric": "month_over_month_change_pct",
                "value": change["change_pct"],
                "context": (
                    f"{change['previous_period']} compared with "
                    f"{change['current_period']}"
                ),
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

    def _forecast_result(self) -> AgentResult:
        result = self.business.machine_learning.revenue_forecast(horizon=3)
        first = result["forecast"][0]
        metrics = result["evaluation"]
        answer = (
            f"The linear baseline forecasts {_currency(first['revenue'])} for "
            f"{first['period']}, with a residual-based 95% range of "
            f"{_currency(first['lower_95'])} to {_currency(first['upper_95'])}. "
            f"Holdout MAE is {_currency(metrics['mae'])}; treat the forecast as "
            "a baseline rather than causal certainty."
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

    def _customer_result(self) -> AgentResult:
        result = self.business.machine_learning.customer_segments()
        leading = result["segments"][0]
        answer = (
            f"The highest-revenue segment is {leading['name']}, containing "
            f"{leading['customers']} customers and "
            f"{_currency(leading['total_revenue'])} in observed revenue. Segment "
            "labels rank observed monetary value and should guide, not replace, "
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

    def _anomaly_result(self) -> AgentResult:
        result = self.business.machine_learning.sales_anomalies(limit=5)
        top = result["anomalies"][0] if result["anomalies"] else None
        top_text = (
            f" The highest-ranked record is {top['order_id']} with revenue "
            f"{_currency(top['revenue'])}."
            if top
            else ""
        )
        answer = (
            f"Isolation Forest flagged {result['anomaly_count']} of "
            f"{result['records_evaluated']} transactions for investigation."
            f"{top_text} A flag indicates statistical unusualness, not fraud or "
            "an error."
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

    def answer(self, question: str) -> dict:
        requested = self._select_agents(question)
        answers: list[str] = []
        evidence: list[dict] = []
        tools: list[str] = []
        agents: list[str] = []
        for key in requested:
            spec = self.handlers[key]
            answer, agent_evidence, agent_tools = spec.handler()
            answers.append(answer)
            evidence.extend(agent_evidence)
            tools.extend(agent_tools)
            agents.append(spec.name)

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


def answer_question(question: str, session: Session) -> dict:
    business = BusinessIntelligence(session)
    return AgentOrchestrator(business).answer(question)
