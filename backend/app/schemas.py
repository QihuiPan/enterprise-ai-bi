from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.currency import CurrencyCode


class IngestionSummary(BaseModel):
    rows_loaded: int
    date_min: str
    date_max: str
    revenue_total: float
    replaced_existing: bool


class InsightQuery(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    currency: CurrencyCode = "USD"


class EvidenceItem(BaseModel):
    source: str
    metric: str
    value: Any
    context: str


class QueryPlan(BaseModel):
    operation: str
    metric: str
    dimension: str | None = None
    period: dict[str, Any]
    direction: str | None = None
    limit: int | None = None
    grain: str | None = None
    read_only: bool
    result_count: int
    total_points: int | None = None
    total_results: int | None = None
    truncated: bool = False


class InsightChart(BaseModel):
    type: str
    title: str
    x_key: str
    y_key: str
    data: list[dict[str, Any]]
    total_points: int | None = None
    total_results: int | None = None
    truncated: bool = False


class InsightResponse(BaseModel):
    question: str
    answer: str
    agents_used: list[str]
    tools_used: list[str]
    evidence: list[EvidenceItem]
    query_plan: QueryPlan | None = None
    chart: InsightChart | None = None
    explanation: str | None = None
    generated_at: str
