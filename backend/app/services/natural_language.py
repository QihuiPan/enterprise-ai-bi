from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from backend.app.currency import CurrencyCode, format_currency
from backend.app.services.analytics import NoDataError, SalesAnalytics, period_is_complete

APPROVED_METRICS = frozenset(
    {"revenue", "orders", "units", "customers", "average_order_value"}
)
APPROVED_DIMENSIONS = frozenset({"region", "category", "product", "customer"})
APPROVED_OPERATIONS = frozenset({"summary", "breakdown", "ranking", "trend"})
MAX_RANKING_ROWS = 20
MAX_DAILY_POINTS = 366
MAX_MONTHLY_POINTS = 120

_DIMENSION_COLUMNS = {
    "region": "region",
    "category": "category",
    "product": "product",
    "customer": "customer_id",
}
_DIMENSION_TITLES = {
    "region": "Regions",
    "category": "Categories",
    "product": "Products",
    "customer": "Customers",
}
_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH_PATTERN = "|".join(_MONTHS)


@dataclass(frozen=True)
class PeriodSpec:
    kind: str = "all"
    value: str | int | None = None


@dataclass(frozen=True)
class ApprovedAnalyticsQuery:
    operation: str
    metric: str
    period: PeriodSpec
    dimension: str | None = None
    direction: str = "desc"
    limit: int | None = None
    grain: str | None = None

    def __post_init__(self) -> None:
        if self.operation not in APPROVED_OPERATIONS:
            raise ValueError("Unsupported analytics operation.")
        if self.metric not in APPROVED_METRICS:
            raise ValueError("Unsupported analytics metric.")
        if self.dimension is not None and self.dimension not in APPROVED_DIMENSIONS:
            raise ValueError("Unsupported analytics dimension.")
        if self.direction not in {"asc", "desc"}:
            raise ValueError("Unsupported ranking direction.")
        if self.grain not in {None, "day", "month"}:
            raise ValueError("Unsupported trend grain.")
        if self.limit is not None and not 1 <= self.limit <= MAX_RANKING_ROWS:
            raise ValueError(f"Result limit must be between 1 and {MAX_RANKING_ROWS}.")


class BusinessQuestionParser:
    """Parse a bounded business-question grammar without generating SQL."""

    _DATABASE_MUTATION = re.compile(
        r"\b(?:delete\s+from|insert\s+into|update\s+[a-z_][\w.]*\s+"
        r"(?:and\s+)?set|alter\s+(?:table|database|schema|view|index)|"
        r"truncate\s+(?:table\s+)?[a-z_][\w.]*|(?:grant|revoke)\b.+\bon)\b",
        re.IGNORECASE,
    )
    _DROP_OBJECT = re.compile(
        r"\bdrop\s+(table|database|schema|view|index|column)\b", re.IGNORECASE
    )
    _SELECT_FROM = re.compile(r"\bselect\b.+\bfrom\b", re.IGNORECASE | re.DOTALL)
    _UNSUPPORTED_METRIC = re.compile(
        r"\b(?:profit|margin|gross income|net income|cash flow|ebitda|headcount|"
        r"inventory|churn|"
        r"(?:average|mean)\s+(?:revenue|sales)|"
        r"(?:revenue|sales)\s+(?:per|/)\s*"
        r"(?:customers?|units?|orders?|records?|products?))\b",
        re.IGNORECASE,
    )
    _DIMENSION_CLAUSE = re.compile(
        r"\b(?:by|across|for\s+each)\s+(?:the\s+)?"
        r"(?:(?:top|bottom)\s+(?:\d+\s+)?)?([a-z][a-z_-]*)\b",
        re.IGNORECASE,
    )
    _UNSUPPORTED_QUALIFIER = re.compile(
        r"\b(?:average|avg|mean|median|minimum|min|maximum|max|share|ratio|"
        r"rate|per|price|percentile|variance|standard\s+deviation)\b",
        re.IGNORECASE,
    )
    _UNSUPPORTED_TIME = re.compile(
        r"\b(?:weeks?|weekly|quarterly|yearly|annual|annually|yesterday|today|"
        r"yoy|year[- ]over[- ]year|week[- ]over[- ]week)\b|"
        r"\b(?:last|latest|past|previous|prior)\s+\d+\s+"
        r"(?:days?|weeks?|quarters?|years?)\b|"
        r"\b(?:last|previous|prior)\s+year\b",
        re.IGNORECASE,
    )
    _APPROVED_CLAUSE_NOUNS = frozenset(
        {
            "region",
            "regions",
            "regional",
            "category",
            "categories",
            "product",
            "products",
            "item",
            "items",
            "customer",
            "customers",
            "revenue",
            "sales",
            "orders",
            "units",
            "month",
            "months",
            "day",
            "days",
        }
    )
    _METRICLESS_FORECAST_WORDS = frozenset(
        {
            "a",
            "can",
            "could",
            "forecast",
            "forecasting",
            "for",
            "give",
            "is",
            "me",
            "month",
            "months",
            "next",
            "please",
            "predict",
            "prediction",
            "projection",
            "quarter",
            "quarters",
            "show",
            "the",
            "what",
            "will",
            "you",
            "revenue",
            "sales",
            "value",
            "amount",
        }
    )
    _METRICLESS_FORECAST_CJK = frozenset(
        {
            "预测",
            "預測",
            "请",
            "請",
            "帮我",
            "幫我",
            "给我",
            "給我",
            "显示",
            "顯示",
            "下个月",
            "下個月",
            "下月",
            "下季度",
            "下一季度",
            "下一季",
            "下季",
            "营收",
            "營收",
            "销售额",
            "銷售額",
        }
    )
    _CHANGE_SCOPE_WORDS = frozenset(
        {
            "why",
            "what",
            "did",
            "do",
            "does",
            "has",
            "have",
            "is",
            "was",
            "explain",
            "revenue",
            "sales",
            "value",
            "amount",
            "change",
            "changed",
            "changes",
            "growth",
            "grew",
            "decline",
            "declined",
            "increase",
            "increased",
            "decrease",
            "decreased",
            "drop",
            "dropped",
            "fall",
            "fell",
            "rise",
            "rose",
            "down",
            "up",
            "in",
            "a",
            "the",
            "latest",
            "current",
            "this",
            "last",
            "previous",
            "prior",
            "month",
            "monthly",
            "quarter",
            "over",
            "time",
            "trend",
            "from",
            "to",
        }
    )
    _CHANGE_SCOPE_CJK = frozenset(
        {
            "為什麼",
            "为什么",
            "什麼",
            "什么",
            "解釋",
            "解释",
            "營收",
            "营收",
            "銷售額",
            "销售额",
            "變化",
            "变化",
            "增長",
            "增长",
            "上升",
            "下降",
            "增加",
            "減少",
            "减少",
            "最新",
            "本月",
            "這個月",
            "这个月",
            "上個月",
            "上个月",
            "上月",
            "本季度",
            "本季",
            "上季度",
            "上一季度",
            "上季",
            "上一季",
            "季度",
            "每月",
            "按月",
            "趨勢",
            "趋势",
        }
    )

    @classmethod
    def requests_database_access(cls, question: str) -> bool:
        normalized = " ".join(question.split())
        return bool(
            re.search(r"\bsql\b", normalized, re.IGNORECASE)
            or cls._DATABASE_MUTATION.search(normalized)
            or cls._DROP_OBJECT.search(normalized)
            or cls._SELECT_FROM.search(normalized)
        )

    def parse(self, question: str) -> ApprovedAnalyticsQuery | None:
        normalized = " ".join(question.lower().split())
        if (
            not normalized
            or self.requests_database_access(normalized)
            or self.requests_unsupported_metric(normalized)
            or self.requests_unsupported_qualifier_or_time(normalized)
            or self.requests_unknown_dimension(normalized)
        ):
            return None
        if self.is_change_explanation(normalized):
            return None

        metric, metric_matched = self._metric(normalized)
        if not metric_matched:
            return None
        dimension = self._dimension(normalized)
        period = self._period(normalized)
        direction, limit, ranking_matched = self._ranking(normalized)
        grain, trend_matched = self._grain(normalized)

        recognized = any(
            (
                metric_matched,
                dimension is not None,
                period.kind != "all",
                ranking_matched,
                trend_matched,
            )
        )
        if not recognized:
            return None

        if trend_matched:
            operation = "trend"
            dimension = None
            limit = None
        elif dimension and ranking_matched:
            operation = "ranking"
        elif dimension:
            operation = "breakdown"
            limit = MAX_RANKING_ROWS
        else:
            operation = "summary"
            limit = None

        return ApprovedAnalyticsQuery(
            operation=operation,
            metric=metric,
            period=period,
            dimension=dimension,
            direction=direction,
            limit=limit,
            grain=grain if operation == "trend" else None,
        )

    @staticmethod
    def is_change_explanation(question: str) -> bool:
        question = question.lower()
        return bool(
            re.search(
                r"\b(why|change[ds]?|growth|grew|declin(?:e|ed)|increase[ds]?|"
                r"decrease[ds]?|drop(?:s|ped)?|falls?|fell|rises?|rose|up|down)\b",
                question,
            )
            or any(
                term in question
                for term in (
                    "為什麼",
                    "为什么",
                    "變化",
                    "变化",
                    "增長",
                    "增长",
                    "上升",
                    "下降",
                    "增加",
                    "減少",
                    "减少",
                )
            )
        )

    @classmethod
    def requests_unsupported_metric(cls, question: str) -> bool:
        return bool(
            cls._UNSUPPORTED_METRIC.search(question)
            or any(
                term in question
                for term in (
                    "利润",
                    "利潤",
                    "毛利",
                    "现金流",
                    "現金流",
                    "人数",
                    "人數",
                    "库存",
                    "庫存",
                    "流失",
                )
            )
        )

    @classmethod
    def requests_unknown_dimension(cls, question: str) -> bool:
        english_unknown = any(
            match.group(1).lower() not in cls._APPROVED_CLAUSE_NOUNS
            for match in cls._DIMENSION_CLAUSE.finditer(question)
        )
        allowed = (
            "地區",
            "地区",
            "區域",
            "区域",
            "類別",
            "类别",
            "品類",
            "品类",
            "產品",
            "产品",
            "商品",
            "客戶",
            "客户",
            "年",
            "月",
            "季度",
            "季",
        )
        metric_terms = r"(?:營收|营收|銷售額|销售额|銷量|销量|訂單|订单)"
        chinese_matches = re.findall(
            rf"(?:按|依|根據|根据)([\u3400-\u9fff]{{1,8}}?)(?:看|查看|分析)?{metric_terms}|"
            rf"([\u3400-\u9fff]{{1,8}}?)的{metric_terms}",
            question,
        )
        chinese_clauses = [first or second for first, second in chinese_matches]
        unsupported_dimension_terms = (
            "销售员",
            "銷售員",
            "业务员",
            "業務員",
            "员工",
            "員工",
            "渠道",
            "通路",
            "门店",
            "門店",
            "城市",
            "省份",
            "供应商",
            "供應商",
        )
        explicit_unknown_dimension = any(
            re.search(
                rf"(?:各)?{term}(?:的)?{metric_terms}",
                question,
            )
            for term in unsupported_dimension_terms
        )
        chinese_unknown = any(
            clause and not any(clause.endswith(term) for term in allowed)
            for clause in chinese_clauses
        )
        return english_unknown or chinese_unknown or explicit_unknown_dimension

    @classmethod
    def requests_unsupported_qualifier_or_time(cls, question: str) -> bool:
        without_aov = re.sub(
            r"\b(?:average order value|aov)\b", "", question, flags=re.IGNORECASE
        )
        without_aov = re.sub(
            r"(?:平均訂單價值|平均订单价值|客單價|客单价)", "", without_aov
        )
        chinese_qualifiers = (
            "平均",
            "中位數",
            "中位数",
            "最大",
            "最小",
            "佔比",
            "占比",
            "比率",
            "比例",
            "單價",
            "单价",
            "價格",
            "价格",
            "同比",
            "環比",
            "环比",
            "人均",
            "標準差",
            "标准差",
            "百分位",
        )
        chinese_time = (
            "每周",
            "每週",
            "按周",
            "按週",
            "周度",
            "週度",
            "每季",
            "按季",
            "每季度",
            "按季度",
            "每年",
            "按年",
            "上周",
            "上週",
            "本周",
            "本週",
            "去年",
            "上一年",
            "今天",
            "今日",
            "昨日",
            "昨天",
            "年度",
        )
        return bool(
            cls._UNSUPPORTED_QUALIFIER.search(without_aov)
            or cls._UNSUPPORTED_TIME.search(question)
            or re.search(
                r"\b(?:tomorrow|year\s+to\s+date|month\s+to\s+date|ytd|mtd)\b",
                question,
                flags=re.IGNORECASE,
            )
            or (
                re.search(r"\bq[1-4]\b", question, flags=re.IGNORECASE)
                and not re.search(
                    r"\b20\d{2}\s*[- ]?q[1-4]\b", question, flags=re.IGNORECASE
                )
            )
            or any(term in without_aov for term in chinese_qualifiers)
            or any(term in question for term in chinese_time)
            or re.search(
                r"(?:最近|近|過去|过去)\s*\d+\s*(?:天|日|周|週|季|年)",
                question,
            )
        )

    @staticmethod
    def scope_terms_supported(
        question: str,
        english_terms: frozenset[str],
        cjk_terms: frozenset[str],
    ) -> bool:
        if re.search(r"\d", question):
            return False
        words = set(re.findall(r"[a-z]+", question.lower()))
        if not words.issubset(english_terms):
            return False
        cjk_text = "".join(re.findall(r"[\u3400-\u9fff]", question))
        for term in sorted(cjk_terms, key=len, reverse=True):
            cjk_text = cjk_text.replace(term, "")
        return not cjk_text

    @classmethod
    def supports_revenue_forecast(cls, question: str) -> bool:
        normalized = question.lower()
        if cls.requests_unsupported_metric(
            normalized
        ) or cls.requests_unsupported_qualifier_or_time(normalized):
            return False
        if cls._dimension(normalized) is not None:
            return False
        if cls._period(normalized).kind != "all":
            return False
        if re.search(
            r"\b(?:next|for)\s+\d+\s+(?:days?|weeks?|months?|quarters?|years?)\b|"
            r"\bnext\s+(?:week|year)\b|\b20\d{2}\b",
            normalized,
        ) or re.search(
            r"(?:未来|未來|接下来|接下來)\s*\d+\s*(?:天|日|月|季|年)",
            normalized,
        ):
            return False
        metric, metric_matched = cls._metric(normalized)
        if metric_matched and metric != "revenue":
            return False
        return cls.scope_terms_supported(
            normalized,
            cls._METRICLESS_FORECAST_WORDS,
            cls._METRICLESS_FORECAST_CJK,
        )

    @classmethod
    def supports_revenue_change_explanation(cls, question: str) -> bool:
        normalized = " ".join(question.lower().split())
        if not cls.is_change_explanation(normalized):
            return False
        if cls.requests_unsupported_metric(
            normalized
        ) or cls.requests_unsupported_qualifier_or_time(normalized):
            return False
        if cls.requests_unknown_dimension(normalized) or cls._dimension(normalized):
            return False
        if cls._period(normalized).kind not in {
            "all",
            "latest_month",
            "previous_month",
            "latest_quarter",
            "previous_quarter",
        }:
            return False
        grain, grain_matched = cls._grain(normalized)
        if grain_matched and grain != "month":
            return False
        metric, metric_matched = cls._metric(normalized)
        return (
            metric_matched
            and metric == "revenue"
            and cls.scope_terms_supported(
                normalized, cls._CHANGE_SCOPE_WORDS, cls._CHANGE_SCOPE_CJK
            )
        )

    @staticmethod
    def _metric(question: str) -> tuple[str, bool]:
        metric_patterns = (
            (
                "average_order_value",
                (
                    r"\baverage order value\b",
                    r"\baov\b",
                    "平均訂單價值",
                    "平均订单价值",
                    "客單價",
                    "客单价",
                ),
            ),
            (
                "revenue",
                (
                    r"\brevenue\b",
                    r"\bsales(?: value| amount)?\b",
                    "營收",
                    "营收",
                    "銷售額",
                    "销售额",
                ),
            ),
            (
                "units",
                (
                    r"\bunits?\b",
                    r"\bquantity\b",
                    r"\bbottles?\b",
                    "銷量",
                    "销量",
                    "件數",
                    "件数",
                ),
            ),
            (
                "orders",
                (r"\border count\b", r"\borders?\b", "訂單", "订单"),
            ),
            (
                "customers",
                (
                    r"\bcustomer count\b",
                    r"\bnumber of customers\b",
                    r"\bhow many customers\b",
                    "客戶數",
                    "客户数",
                ),
            ),
        )
        for metric, patterns in metric_patterns:
            if any(
                re.search(pattern, question) if pattern.startswith(r"\b") else pattern in question
                for pattern in patterns
            ):
                return metric, True
        return "revenue", False

    @staticmethod
    def _dimension(question: str) -> str | None:
        patterns = {
            "region": (r"\bregions?\b", r"\bregional\b", "地區", "地区", "區域", "区域"),
            "category": (
                r"\bcategor(?:y|ies)\b",
                "類別",
                "类别",
                "品類",
                "品类",
            ),
            "product": (r"\bproducts?\b", r"\bitems?\b", "產品", "产品", "商品"),
            "customer": (r"\bcustomers?\b", "客戶", "客户"),
        }
        for dimension, candidates in patterns.items():
            if any(
                re.search(candidate, question)
                if candidate.startswith(r"\b")
                else candidate in question
                for candidate in candidates
            ):
                if dimension == "customer" and re.search(
                    r"\b(customer count|number of customers|how many customers)\b",
                    question,
                ):
                    continue
                if dimension == "customer" and any(
                    term in question for term in ("客戶數", "客户数")
                ):
                    continue
                return dimension
        return None

    @staticmethod
    def _ranking(question: str) -> tuple[str, int, bool]:
        descending = re.search(r"\b(top|highest|best|most)\b", question) or any(
            term in question for term in ("最高", "最多", "前")
        )
        ascending = re.search(r"\b(bottom|lowest|worst|least)\b", question) or any(
            term in question for term in ("最低", "最少", "後", "后")
        )
        matched = bool(descending or ascending)
        direction = "asc" if ascending else "desc"

        limit_match = re.search(r"\b(?:top|bottom)\s*(\d{1,3})\b", question)
        if not limit_match:
            limit_match = re.search(r"(?:前|後|后)\s*(\d{1,3})", question)
        requested = int(limit_match.group(1)) if limit_match else 5
        return direction, min(max(requested, 1), MAX_RANKING_ROWS), matched

    @staticmethod
    def _grain(question: str) -> tuple[str, bool]:
        daily = re.search(r"\b(daily|by day|each day)\b", question) or any(
            term in question for term in ("按日", "每日", "每天")
        )
        monthly = re.search(r"\b(monthly|by month|each month)\b", question) or any(
            term in question for term in ("按月", "每月")
        )
        trend = re.search(r"\b(trend|over time|timeline)\b", question) or any(
            term in question for term in ("趨勢", "趋势", "走勢", "走势")
        )
        matched = bool(daily or monthly or trend)
        return ("day" if daily else "month"), matched

    @staticmethod
    def _period(question: str) -> PeriodSpec:
        explicit_quarter = re.search(r"\b(20\d{2})\s*[- ]?q([1-4])\b", question)
        if not explicit_quarter:
            explicit_quarter = re.search(
                r"(20\d{2})\s*年\s*第?\s*([1-4])\s*季(?:度)?", question
            )
        if explicit_quarter:
            return PeriodSpec(
                "quarter",
                f"{int(explicit_quarter.group(1)):04d}Q{int(explicit_quarter.group(2))}",
            )

        chinese_month = re.search(r"\b(20\d{2})\s*年\s*(1[0-2]|0?[1-9])\s*月", question)
        if chinese_month:
            return PeriodSpec(
                "month", f"{int(chinese_month.group(1)):04d}-{int(chinese_month.group(2)):02d}"
            )

        iso_month = re.search(r"\b(20\d{2})[-/](1[0-2]|0[1-9])\b", question)
        if iso_month:
            return PeriodSpec(
                "month", f"{int(iso_month.group(1)):04d}-{int(iso_month.group(2)):02d}"
            )

        named_month = re.search(rf"\b({_MONTH_PATTERN})\s+(20\d{{2}})\b", question)
        if named_month:
            return PeriodSpec(
                "month",
                f"{int(named_month.group(2)):04d}-{_MONTHS[named_month.group(1)]:02d}",
            )

        trailing = re.search(
            r"\b(?:last|latest|past)\s+(\d{1,2})\s+months?\b", question
        )
        if not trailing:
            trailing = re.search(
                r"(?:最近|近|過去|过去)\s*(\d{1,2})\s*(?:個|个)?月", question
            )
        if trailing:
            return PeriodSpec("trailing_months", min(max(int(trailing.group(1)), 1), 24))

        if re.search(r"\b(previous|prior|last) quarter\b", question) or any(
            term in question for term in ("上季度", "上一季度", "上季", "上一季")
        ):
            return PeriodSpec("previous_quarter")
        if re.search(r"\b(latest|current|this) quarter\b", question) or any(
            term in question
            for term in (
                "最新季度",
                "當前季度",
                "当前季度",
                "本季度",
                "本季",
                "這個季度",
                "这个季度",
            )
        ):
            return PeriodSpec("latest_quarter")
        if re.search(r"\b(previous|prior|last) month\b", question) or any(
            term in question for term in ("上個月", "上个月", "上月")
        ):
            return PeriodSpec("previous_month")
        if re.search(r"\b(latest|current|this) month\b", question) or any(
            term in question for term in ("最新月份", "本月", "這個月", "这个月")
        ):
            return PeriodSpec("latest_month")
        if re.search(r"\b(latest|current|this) year\b", question) or any(
            term in question for term in ("最新年度", "今年", "本年")
        ):
            return PeriodSpec("latest_year")

        year = re.search(r"(20\d{2})\s*年", question)
        if not year:
            year = re.search(r"\b(20\d{2})\b", question)
        if year:
            return PeriodSpec("year", int(year.group(1)))
        return PeriodSpec()


class ApprovedAnalyticsService:
    """Execute only enumerated read-only operations over a validated snapshot."""

    def __init__(self, analytics: SalesAnalytics, currency: CurrencyCode = "USD"):
        self.analytics = analytics
        self.currency = currency

    def answer(self, question: str) -> dict | None:
        query = BusinessQuestionParser().parse(question)
        if query is None:
            return None
        return self.execute(query)

    def execute(self, query: ApprovedAnalyticsQuery) -> dict:
        filtered, period = self._filtered_frame(query.period)
        total_points: int | None = None
        total_results: int | None = None
        truncated = False
        if query.operation == "summary":
            data = [{"label": period["label"], query.metric: self._metric(filtered, query.metric)}]
            chart_type = "metric"
            x_key = "label"
        elif query.operation == "trend":
            data, total_points, truncated = self._trend(
                filtered, query.metric, query.grain or "month"
            )
            chart_type = "line"
            x_key = "period"
        else:
            if query.dimension is None:
                raise ValueError("A dimension is required for a breakdown or ranking.")
            data, total_results, truncated = self._breakdown(filtered, query)
            chart_type = "bar"
            x_key = query.dimension

        plan = self._plan(
            query,
            period,
            result_count=len(data),
            total_points=total_points,
            total_results=total_results,
            truncated=truncated,
        )
        chart = {
            "type": chart_type,
            "title": self._chart_title(query, period["label"]),
            "x_key": x_key,
            "y_key": query.metric,
            "data": data,
            "total_points": total_points,
            "total_results": total_results,
            "truncated": truncated,
        }
        truncation_note = (
            f" The chart returns the latest {len(data)} of {total_points} points; "
            "use a narrower period to inspect earlier points."
            if truncated and query.operation == "trend"
            else f" The chart shows {len(data)} of {total_results} ranked results."
            if truncated
            else ""
        )
        semantic_note = self._semantic_note(query.metric)
        return {
            "answer": self._answer_text(
                query,
                period["label"],
                data,
                total_points=total_points,
                total_results=total_results,
                truncated=truncated,
            ),
            "explanation": (
                f"I interpreted the request as an approved read-only {query.operation} "
                f"of {self._metric_label(query.metric)} for {period['label']}. "
                "The result was computed from validated sales records; no generated SQL "
                f"or database mutation was executed.{truncation_note}{semantic_note}"
            ),
            "query_plan": plan,
            "chart": chart,
            "evidence": [
                {
                    "source": "analytics.approved_query",
                    "metric": query.metric,
                    "value": {
                        "query_plan": plan,
                        "result_count": len(data),
                        "total_points": total_points,
                        "total_results": total_results,
                        "truncated": truncated,
                        "data": data,
                    },
                    "context": (
                        f"Requested window {period['resolved_start']} through "
                        f"{period['resolved_end']}; observed validated sales records "
                        f"span {period['observed_start']} through "
                        f"{period['observed_end']}."
                    ),
                }
            ],
            "tools": ["approved_analytics_query"],
        }

    def _filtered_frame(self, period: PeriodSpec) -> tuple[pd.DataFrame, dict]:
        frame = self.analytics.frame
        dates = frame["order_date"]
        data_min = pd.Timestamp(dates.min()).normalize()
        data_max = pd.Timestamp(dates.max()).normalize()
        latest_month = data_max.to_period("M")
        latest_quarter = data_max.to_period("Q")
        observed_quarters = sorted(dates.dt.to_period("Q").unique())
        complete_quarters = [
            quarter
            for quarter in observed_quarters
            if period_is_complete(dates, quarter)
        ]

        if period.kind == "all":
            start, end, label = data_min, data_max + pd.Timedelta(days=1), "all available data"
        elif period.kind == "year":
            start = pd.Timestamp(year=int(period.value), month=1, day=1)
            end = start + pd.DateOffset(years=1)
            label = str(period.value)
        elif period.kind == "month":
            start = pd.Period(str(period.value), freq="M").start_time
            end = start + pd.DateOffset(months=1)
            label = str(period.value)
        elif period.kind == "quarter":
            requested_quarter = pd.Period(str(period.value), freq="Q")
            start = requested_quarter.start_time
            end = requested_quarter.end_time + pd.Timedelta(nanoseconds=1)
            label = str(requested_quarter).replace("Q", "-Q")
        elif period.kind == "previous_quarter":
            if not complete_quarters:
                raise NoDataError(
                    "No complete calendar quarter is available in the selected data."
                )
            latest_complete_quarter = complete_quarters[-1]
            start = latest_complete_quarter.start_time
            end = latest_complete_quarter.end_time + pd.Timedelta(nanoseconds=1)
            quarter_label = str(latest_complete_quarter).replace("Q", "-Q")
            label = f"latest complete data quarter ({quarter_label})"
        elif period.kind == "latest_quarter":
            start = latest_quarter.start_time
            end = latest_quarter.end_time + pd.Timedelta(nanoseconds=1)
            quarter_label = str(latest_quarter).replace("Q", "-Q")
            label = f"latest data quarter ({quarter_label})"
        elif period.kind == "latest_month":
            start = latest_month.start_time
            end = start + pd.DateOffset(months=1)
            label = f"latest data month ({latest_month})"
        elif period.kind == "previous_month":
            previous = latest_month - 1
            start = previous.start_time
            end = start + pd.DateOffset(months=1)
            label = f"previous data month ({previous})"
        elif period.kind == "trailing_months":
            month_count = int(period.value)
            start = (latest_month - (month_count - 1)).start_time
            end = latest_month.end_time + pd.Timedelta(nanoseconds=1)
            label = f"latest {month_count} data months"
        elif period.kind == "latest_year":
            start = pd.Timestamp(year=data_max.year, month=1, day=1)
            end = start + pd.DateOffset(years=1)
            label = f"latest data year ({data_max.year})"
        else:
            raise ValueError("Unsupported period selector.")

        selected = frame[(dates >= start) & (dates < end)].copy()
        if selected.empty:
            raise NoDataError(f"No sales data matches the requested period: {label}.")
        return selected, {
            "kind": period.kind,
            "value": period.value,
            "label": label,
            "resolved_start": pd.Timestamp(start).normalize().date().isoformat(),
            "resolved_end": (
                pd.Timestamp(end) - pd.Timedelta(nanoseconds=1)
            ).normalize().date().isoformat(),
            "observed_start": selected["order_date"].min().date().isoformat(),
            "observed_end": selected["order_date"].max().date().isoformat(),
        }

    def _trend(
        self, frame: pd.DataFrame, metric: str, grain: str
    ) -> tuple[list[dict], int, bool]:
        frequency = "D" if grain == "day" else "M"
        grouped = frame.assign(_period=frame["order_date"].dt.to_period(frequency)).groupby(
            "_period", sort=True
        )
        data = [
            {"period": str(period), metric: self._metric(group, metric)}
            for period, group in grouped
        ]
        max_points = MAX_DAILY_POINTS if grain == "day" else MAX_MONTHLY_POINTS
        total_points = len(data)
        return data[-max_points:], total_points, total_points > max_points

    def _breakdown(
        self, frame: pd.DataFrame, query: ApprovedAnalyticsQuery
    ) -> tuple[list[dict], int, bool]:
        if query.dimension is None:
            raise ValueError("A dimension is required for a breakdown.")
        column = _DIMENSION_COLUMNS[query.dimension]
        rows = [
            {query.dimension: str(name), query.metric: self._metric(group, query.metric)}
            for name, group in frame.groupby(column, dropna=False)
        ]
        rows.sort(
            key=lambda row: (row[query.metric], row[query.dimension]),
            reverse=query.direction == "desc",
        )
        limit = query.limit or MAX_RANKING_ROWS
        total_results = len(rows)
        return rows[:limit], total_results, total_results > limit

    @staticmethod
    def _metric(frame: pd.DataFrame, metric: str) -> float | int:
        if metric == "revenue":
            return round(float(frame["revenue"].sum()), 2)
        if metric == "orders":
            return int(frame["order_id"].nunique())
        if metric == "units":
            return int(frame["quantity"].sum())
        if metric == "customers":
            return int(frame["customer_id"].nunique())
        if metric == "average_order_value":
            order_revenue = frame.groupby("order_id")["revenue"].sum()
            return round(float(order_revenue.mean()), 2)
        raise ValueError("Unsupported analytics metric.")

    @staticmethod
    def _plan(
        query: ApprovedAnalyticsQuery,
        period: dict,
        *,
        result_count: int,
        total_points: int | None,
        total_results: int | None,
        truncated: bool,
    ) -> dict:
        return {
            "operation": query.operation,
            "metric": query.metric,
            "dimension": query.dimension,
            "period": period,
            "direction": query.direction if query.operation == "ranking" else None,
            "limit": query.limit,
            "grain": query.grain,
            "read_only": True,
            "result_count": result_count,
            "total_points": total_points,
            "total_results": total_results,
            "truncated": truncated,
        }

    def _answer_text(
        self,
        query: ApprovedAnalyticsQuery,
        period: str,
        data: list[dict],
        *,
        total_points: int | None,
        total_results: int | None,
        truncated: bool,
    ) -> str:
        label = self._metric_label(query.metric)
        semantic_note = self._semantic_note(query.metric)
        if query.operation == "summary":
            value = self._format_metric(query.metric, data[0][query.metric])
            return f"{label.capitalize()} for {period} was {value}.{semantic_note}"
        if query.operation == "trend":
            first, last = data[0], data[-1]
            grain_label = "daily" if query.grain == "day" else "monthly"
            point_description = (
                f"returns the latest {len(data)} of {total_points} points"
                if truncated
                else f"contains {len(data)} points"
            )
            return (
                f"The {grain_label} {label} trend for {period} {point_description}, "
                "moving from "
                f"{self._format_metric(query.metric, first[query.metric])} in "
                f"{first['period']} to "
                f"{self._format_metric(query.metric, last[query.metric])} in "
                f"{last['period']}.{semantic_note}"
            )

        dimension = query.dimension or "dimension"
        leader = data[0]
        qualifier = "lowest" if query.direction == "asc" else "highest"
        result_description = (
            f"shows the first {len(data)} of {total_results} ranked results"
            if truncated
            else f"contains {len(data)} {dimension} "
            f"{'result' if len(data) == 1 else 'results'}"
        )
        return (
            f"{leader[dimension]} had the {qualifier} {label} for {period} at "
            f"{self._format_metric(query.metric, leader[query.metric])}. "
            f"The chart {result_description}.{semantic_note}"
        )

    def _chart_title(self, query: ApprovedAnalyticsQuery, period: str) -> str:
        label = self._metric_label(query.metric).title()
        if query.operation == "trend":
            return f"{label} Trend — {period}"
        if query.dimension:
            prefix = "Bottom" if query.direction == "asc" else "Top"
            dimension = (
                self.analytics.record_semantics()["entity_count_label"]
                if query.dimension == "customer"
                else _DIMENSION_TITLES[query.dimension]
            )
            return f"{prefix} {dimension} by {label} — {period}"
        return f"{label} — {period}"

    def _metric_label(self, metric: str) -> str:
        semantics = self.analytics.record_semantics()
        if metric == "orders":
            return semantics["record_count_label"].lower()
        if metric == "customers":
            return semantics["entity_count_label"].lower()
        if metric == "average_order_value":
            return semantics["average_value_label"].lower()
        return metric.replace("_", " ")

    def _semantic_note(self, metric: str) -> str:
        semantics = self.analytics.record_semantics()
        if semantics["aggregate_record_proxy"] and metric in {
            "orders",
            "average_order_value",
        }:
            return f" {semantics['warning']}"
        if metric == "customers" and semantics["entity_warning"]:
            return f" {semantics['entity_warning']}"
        return ""

    def _format_metric(self, metric: str, value: float | int) -> str:
        if metric in {"revenue", "average_order_value"}:
            return format_currency(value, self.currency)
        return f"{int(value):,}"
