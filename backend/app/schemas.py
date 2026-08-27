from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IngestionSummary(BaseModel):
    rows_loaded: int
    date_min: str
    date_max: str
    revenue_total: float
    replaced_existing: bool


class InsightQuery(BaseModel):
    question: str = Field(min_length=5, max_length=500)


class EvidenceItem(BaseModel):
    source: str
    metric: str
    value: Any
    context: str


class InsightResponse(BaseModel):
    question: str
    answer: str
    agents_used: list[str]
    tools_used: list[str]
    evidence: list[EvidenceItem]
    generated_at: str
