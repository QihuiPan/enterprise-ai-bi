from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.currency import CurrencyCode, format_currency, resolve_source_currency
from backend.app.services.analytics import NoDataError
from backend.app.services.business import BusinessIntelligence
from backend.app.services.filtering import SalesFilters
from backend.app.services.natural_language import (
    ApprovedAnalyticsService,
    BusinessQuestionParser,
)

AgentResult = tuple[str, list[dict], list[str]]


@dataclass(frozen=True)
class AgentSpec:
    name: str
    handler: Callable[[], AgentResult]


class AgentOrchestrator:
    """Routes questions to registered, read-only analytical specialists."""

    INTENT_TERMS = {
        "executive": (
            "executive",
            "business performance overview",
            "business performance report",
            "高管",
            "管理層",
            "管理层",
            "執行摘要",
            "执行摘要",
            "經營概覽",
            "经营概览",
            "業務概覽",
            "业务概览",
        ),
        "forecast": (
            "forecast",
            "predict",
            "future",
            "next month",
            "next quarter",
            "預測",
            "预测",
        ),
        "customer": (
            "segment",
            "segmentation",
            "rfm",
            "分群",
            "客群",
            "分段",
        ),
        "anomaly": (
            "anomaly",
            "unusual",
            "outlier",
            "fraud",
            "異常",
            "异常",
            "離群",
            "离群",
        ),
    }
    EXECUTIVE_SEQUENCE = ("analyst", "forecast", "customer", "anomaly")
    _SPECIALIST_SCOPE_TERMS = {
        "customer": (
            frozenset(
                {
                    "which",
                    "what",
                    "show",
                    "give",
                    "me",
                    "the",
                    "customer",
                    "customers",
                    "entity",
                    "entities",
                    "account",
                    "accounts",
                    "store",
                    "stores",
                    "shop",
                    "shops",
                    "branch",
                    "branches",
                    "segment",
                    "segments",
                    "segmentation",
                    "rfm",
                    "create",
                    "creates",
                    "most",
                    "value",
                    "high",
                    "highest",
                    "revenue",
                    "sales",
                    "please",
                }
            ),
            frozenset(
                {
                    "哪些",
                    "哪個",
                    "哪个",
                    "顯示",
                    "显示",
                    "請",
                    "请",
                    "給我",
                    "给我",
                    "客戶",
                    "客户",
                    "客群",
                    "分群",
                    "分段",
                    "細分",
                    "细分",
                    "商店",
                    "門店",
                    "门店",
                    "分店",
                    "帳戶",
                    "账户",
                    "價值",
                    "价值",
                    "最高",
                    "最多",
                    "營收",
                    "营收",
                    "銷售額",
                    "销售额",
                }
            ),
        ),
        "anomaly": (
            frozenset(
                {
                    "show",
                    "find",
                    "identify",
                    "me",
                    "a",
                    "an",
                    "the",
                    "unusual",
                    "anomaly",
                    "anomalies",
                    "outlier",
                    "outliers",
                    "fraud",
                    "detection",
                    "detect",
                    "sales",
                    "record",
                    "records",
                    "transaction",
                    "transactions",
                    "order",
                    "orders",
                    "revenue",
                    "investigate",
                    "investigation",
                    "review",
                    "reviews",
                    "to",
                    "for",
                    "flag",
                    "flagged",
                    "please",
                }
            ),
            frozenset(
                {
                    "顯示",
                    "显示",
                    "找出",
                    "尋找",
                    "寻找",
                    "異常",
                    "异常",
                    "離群",
                    "离群",
                    "可疑",
                    "銷售",
                    "销售",
                    "交易",
                    "訂單",
                    "订单",
                    "紀錄",
                    "记录",
                    "調查",
                    "调查",
                    "偵測",
                    "检测",
                    "欺詐",
                    "欺诈",
                }
            ),
        ),
        "executive": (
            frozenset(
                {
                    "executive",
                    "business",
                    "performance",
                    "overview",
                    "report",
                    "summary",
                    "brief",
                    "briefing",
                    "create",
                    "give",
                    "show",
                    "me",
                    "an",
                    "a",
                    "the",
                    "revenue",
                    "sales",
                    "please",
                    "our",
                    "company",
                    "what",
                    "is",
                }
            ),
            frozenset(
                {
                    "高管",
                    "管理層",
                    "管理层",
                    "執行摘要",
                    "执行摘要",
                    "經營概覽",
                    "经营概览",
                    "業務概覽",
                    "业务概览",
                    "報告",
                    "报告",
                    "摘要",
                    "顯示",
                    "显示",
                    "生成",
                    "請",
                    "请",
                    "給我",
                    "给我",
                    "營收",
                    "营收",
                    "銷售",
                    "销售",
                }
            ),
        ),
    }

    def __init__(
        self, business: BusinessIntelligence, currency: CurrencyCode = "USD"
    ):
        self.business = business
        self.currency = currency
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

    @classmethod
    def _specialist_scope_supported(
        cls, requested: tuple[str, ...], question: str
    ) -> bool:
        normalized = " ".join(question.lower().split())
        if requested == ("forecast",):
            return BusinessQuestionParser.supports_revenue_forecast(normalized)

        intent = (
            "executive"
            if requested == cls.EXECUTIVE_SEQUENCE
            else requested[0]
            if requested in (("customer",), ("anomaly",))
            else None
        )
        if intent is None:
            return True

        if (
            BusinessQuestionParser.requests_unsupported_metric(normalized)
            or BusinessQuestionParser.requests_unsupported_qualifier_or_time(
                normalized
            )
            or BusinessQuestionParser.requests_unknown_dimension(normalized)
            or BusinessQuestionParser._period(normalized).kind != "all"
        ):
            return False

        dimension = BusinessQuestionParser._dimension(normalized)
        if intent in {"executive", "anomaly"} and dimension is not None:
            return False
        if intent == "customer" and dimension not in {None, "customer"}:
            return False

        english_terms, cjk_terms = cls._SPECIALIST_SCOPE_TERMS[intent]
        return BusinessQuestionParser.scope_terms_supported(
            normalized, english_terms, cjk_terms
        )

    def _analyst_result(self, question: str = "") -> AgentResult:
        normalized = question.lower()
        quarter_requested = bool(
            re.search(r"\bquarters?\b", normalized)
            or any(term in normalized for term in ("季度", "上季", "上一季"))
        )
        completed_only = quarter_requested and bool(
            re.search(r"\b(last|previous)\s+quarter\b", normalized)
            or any(term in normalized for term in ("上季度", "上季", "上一季"))
        )
        period = BusinessQuestionParser._period(normalized)
        period_offset = 1 if period.kind == "previous_month" else 0
        grain = "quarter" if quarter_requested else "month"
        change = self.business.analytics.explain_revenue_change(
            grain,
            completed_only=completed_only,
            period_offset=period_offset,
        )
        direction = (
            "rose"
            if change["change"] > 0
            else "fell"
            if change["change"] < 0
            else "was unchanged"
        )
        comparison_label = (
            "quarter over quarter" if grain == "quarter" else "month over month"
        )
        region = change["contributors"]["region"][0]
        category = change["contributors"]["category"][0]
        if change["change_pct_available"]:
            percentage_text = (
                f"{direction} {abs(change['change_pct']):.2f}% {comparison_label}"
            )
        elif change["comparison_status"] == "zero_baseline":
            percentage_text = (
                "moved from a zero baseline, so percentage change is undefined"
            )
        elif change["comparison_status"] == "non_consecutive_periods":
            percentage_text = (
                f"cannot be expressed {comparison_label} because the latest observed "
                "periods are not consecutive"
            )
        else:
            percentage_text = (
                f"{direction} by {format_currency(abs(change['change']), self.currency)}, "
                f"but {comparison_label} percentage is unavailable because at least "
                "one observed period is incomplete"
            )
        answer = (
            f"Revenue {percentage_text} from {change['previous_period']} to "
            f"{change['current_period']} "
            f"({format_currency(change['previous_revenue'], self.currency)} to "
            f"{format_currency(change['current_revenue'], self.currency)}). "
            f"The weakest regional contribution was {region['name']} "
            f"({format_currency(region['change'], self.currency)}), "
            f"while the weakest category contribution was {category['name']} "
            f"({format_currency(category['change'], self.currency)})."
        )
        evidence = [
            {
                "source": "analytics.explain_revenue_change",
                "metric": f"{grain}_over_{grain}_change_pct",
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

    def _forecast_result(self, question: str = "") -> AgentResult:
        normalized = question.lower()
        quarter_requested = bool(
            re.search(r"\bquarters?\b", normalized)
            or any(term in normalized for term in ("季度", "下一季", "下季"))
        )
        horizon = 3 if quarter_requested else 1
        result = self.business.machine_learning.revenue_forecast(horizon=horizon)
        forecasts = result["forecast"]
        first = forecasts[0]
        metrics = result["evaluation"]
        model = result.get("model", "forecasting baseline").replace("_", " ")
        if quarter_requested:
            total_revenue = round(
                sum(float(item["revenue"]) for item in forecasts), 2
            )
            summed_lower = round(
                sum(float(item["lower_95"]) for item in forecasts), 2
            )
            summed_upper = round(
                sum(float(item["upper_95"]) for item in forecasts), 2
            )
            period_values = ", ".join(
                f"{item['period']} {format_currency(item['revenue'], self.currency)}"
                for item in forecasts
            )
            answer = (
                f"The {model} three-month revenue forecast is {period_values}, totaling "
                f"{format_currency(total_revenue, self.currency)}. Summing the three "
                "monthly residual-based ranges gives "
                f"{format_currency(summed_lower, self.currency)} to "
                f"{format_currency(summed_upper, self.currency)}; this is not a joint "
                "quarter-level prediction interval. Holdout MAE is "
                f"{format_currency(metrics['mae'], self.currency)}; treat the forecast "
                "as a baseline rather than causal certainty."
            )
            forecast_metric = "next_quarter_forecast"
            forecast_value = {
                "periods": forecasts,
                "total_revenue": total_revenue,
                "summed_monthly_lower_95": summed_lower,
                "summed_monthly_upper_95": summed_upper,
            }
        else:
            answer = (
                f"The {model} forecasts revenue of "
                f"{format_currency(first['revenue'], self.currency)} for "
                f"{first['period']}, with a residual-based 95% range of "
                f"{format_currency(first['lower_95'], self.currency)} to "
                f"{format_currency(first['upper_95'], self.currency)}. Holdout MAE is "
                f"{format_currency(metrics['mae'], self.currency)}; treat the forecast "
                "as a baseline rather than causal certainty."
            )
            forecast_metric = "next_month_forecast"
            forecast_value = first
        evidence = [
            {
                "source": "ml.forecast_revenue",
                "metric": forecast_metric,
                "value": forecast_value,
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
        semantics = self.business.analytics.record_semantics()
        entity_label = semantics["entity_count_label"].lower()
        entity_context = (
            f" {semantics['entity_warning']}" if semantics["entity_warning"] else ""
        )
        leading = result["segments"][0]
        answer = (
            f"The highest-revenue segment is {leading['name']}, containing "
            f"{leading['customers']} {entity_label} and "
            f"{format_currency(leading['total_revenue'], self.currency)} in observed "
            "revenue. Segment "
            "labels rank observed monetary value and should guide, not replace, "
            f"individual {entity_label} review.{entity_context}"
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
        record_label = self.business.analytics.record_semantics()[
            "record_count_label"
        ].lower()
        top = result["anomalies"][0] if result["anomalies"] else None
        top_text = (
            f" The highest-ranked record is {top['order_id']} with revenue "
            f"{format_currency(top['revenue'], self.currency)}."
            if top
            else ""
        )
        answer = (
            f"Isolation Forest flagged {result['anomaly_count']} of "
            f"{result['records_evaluated']} {record_label} for investigation."
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

    def _policy_result(self, question: str) -> dict:
        return {
            "question": question,
            "answer": (
                "I cannot execute SQL or database-changing instructions. Ask for an "
                "approved metric such as revenue, orders, units, customers, or average "
                "order value, optionally by period, region, category, product, or customer."
            ),
            "agents_used": ["Data Analyst Agent"],
            "tools_used": [],
            "evidence": [
                {
                    "source": "analytics.query_policy",
                    "metric": "request_rejected",
                    "value": {"read_only": True, "executed": False},
                    "context": "Arbitrary SQL and database mutations are not permitted.",
                }
            ],
            "query_plan": None,
            "chart": None,
            "explanation": (
                "The request was blocked before any sales data was read because it fell "
                "outside the deterministic read-only analytics grammar."
            ),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _unsupported_question_result(question: str) -> dict:
        return {
            "question": question,
            "answer": (
                "I could not map that question to an approved business metric. "
                "Ask explicitly for revenue, orders or records, units, customers or "
                "entities, or average order or record value. Use the dashboard "
                "filters to apply date, region, category, or product scope."
            ),
            "agents_used": ["Data Analyst Agent"],
            "tools_used": [],
            "evidence": [
                {
                    "source": "analytics.query_policy",
                    "metric": "unsupported_business_metric",
                    "value": {"read_only": True, "executed": False},
                    "context": (
                        "The request did not name a metric in the approved analytical "
                        "grammar, so no substitute metric was inferred."
                    ),
                }
            ],
            "query_plan": None,
            "chart": None,
            "explanation": (
                "The bounded planner asks for a supported metric instead of silently "
                "substituting revenue."
            ),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _semantic_unavailable_result(question: str, reason: str) -> dict:
        return {
            "question": question,
            "answer": reason,
            "agents_used": ["Data Analyst Agent"],
            "tools_used": [],
            "evidence": [
                {
                    "source": "analytics.dataset_profile",
                    "metric": "semantic_metric_unavailable",
                    "value": {"available": False},
                    "context": reason,
                }
            ],
            "query_plan": None,
            "chart": None,
            "explanation": (
                "The active dataset profile prevented a synthesized field from being "
                "presented as an observed business metric."
            ),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _unavailable_result(key: str, name: str, reason: str) -> AgentResult:
        readable_name = name.removesuffix(" Agent")
        return (
            f"{readable_name} is unavailable for the current selection: {reason}",
            [
                {
                    "source": "agent.data_precondition",
                    "metric": f"{key}_unavailable",
                    "value": {"available": False, "reason": reason},
                    "context": (
                        "No model or analytical output was generated for this "
                        "specialist because its minimum data requirement was not met."
                    ),
                }
            ],
            [],
        )

    @staticmethod
    def _requested_entity_label(question: str) -> str | None:
        normalized = question.casefold()
        entity_patterns = (
            (
                "Customers",
                r"\b(?:customer|customers|client|clients|buyer|buyers)\b",
                ("客户", "客戶", "顾客", "顧客"),
            ),
            (
                "Stores",
                r"\b(?:store|stores|shop|shops|branch|branches)\b",
                ("门店", "門店", "商店", "分店"),
            ),
            (
                "Accounts",
                r"\b(?:account|accounts)\b",
                ("账户", "帳戶"),
            ),
            (
                "Entities",
                r"\b(?:entity|entities)\b",
                ("实体", "實體"),
            ),
        )
        for label, english_pattern, cjk_terms in entity_patterns:
            if re.search(english_pattern, normalized) or any(
                term in normalized for term in cjk_terms
            ):
                return label
        return None

    def answer(self, question: str) -> dict:
        if BusinessQuestionParser.requests_database_access(question):
            return self._policy_result(question)

        requested = self._select_agents(question)
        if not self._specialist_scope_supported(requested, question):
            return self._unsupported_question_result(question)
        semantics = self.business.analytics.record_semantics()
        requested_entity_label = self._requested_entity_label(question)
        entity_label = semantics["entity_count_label"]
        entity_mismatch = bool(
            requested_entity_label
            and (
                (
                    requested_entity_label == "Entities"
                    and entity_label == "Unspecified entities"
                )
                or (
                    requested_entity_label != "Entities"
                    and entity_label != requested_entity_label
                )
            )
        )
        if (
            requested != self.EXECUTIVE_SEQUENCE
            and entity_mismatch
        ):
            return self._semantic_unavailable_result(
                question,
                f"{requested_entity_label} analytics are unavailable because "
                f"the active entity field represents {entity_label.lower()}. "
                f"Ask about {entity_label.lower()} instead.",
            )
        if requested == ("analyst",):
            parsed_query = BusinessQuestionParser().parse(question)
            if (
                parsed_query is not None
                and parsed_query.metric == "units"
                and not semantics.get("units_available", True)
            ):
                return self._semantic_unavailable_result(
                    question,
                    semantics.get("unit_warning")
                    or "Unit analytics are unavailable because quantity was not mapped.",
                )
        answers: list[str] = []
        evidence: list[dict] = []
        tools: list[str] = []
        agents: list[str] = []
        natural_language_result = None
        if requested == ("analyst",):
            natural_language_result = ApprovedAnalyticsService(
                self.business.analytics, self.currency
            ).answer(question)

        if natural_language_result:
            return {
                "question": question,
                "answer": natural_language_result["answer"],
                "agents_used": [self.handlers["analyst"].name],
                "tools_used": natural_language_result["tools"],
                "evidence": natural_language_result["evidence"],
                "query_plan": natural_language_result["query_plan"],
                "chart": natural_language_result["chart"],
                "explanation": natural_language_result["explanation"],
                "generated_at": datetime.now(UTC).isoformat(),
            }

        if requested == (
            "analyst",
        ) and not BusinessQuestionParser.supports_revenue_change_explanation(question):
            return self._unsupported_question_result(question)

        for key in requested:
            spec = self.handlers[key]
            try:
                if key == "analyst":
                    answer, agent_evidence, agent_tools = self._analyst_result(question)
                elif key == "forecast":
                    answer, agent_evidence, agent_tools = self._forecast_result(question)
                else:
                    answer, agent_evidence, agent_tools = spec.handler()
            except (NoDataError, ValueError) as exc:
                answer, agent_evidence, agent_tools = self._unavailable_result(
                    key, spec.name, str(exc)
                )
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
            "query_plan": None,
            "chart": None,
            "explanation": (
                "The request was routed to deterministic read-only specialist services "
                "and grounded in the returned evidence."
            ),
            "generated_at": datetime.now(UTC).isoformat(),
        }


def answer_question(
    question: str,
    session: Session,
    filters: SalesFilters | None = None,
    currency: CurrencyCode = "USD",
) -> dict:
    business = BusinessIntelligence(session, filters)
    return AgentOrchestrator(
        business, resolve_source_currency(session, currency)
    ).answer(question)
