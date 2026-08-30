from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.app.currency import CurrencyCode


class IngestionSummary(BaseModel):
    rows_loaded: int
    date_min: str
    date_max: str
    revenue_total: float
    replaced_existing: bool


class TabularColumnPreview(BaseModel):
    name: str
    inferred_type: str
    non_empty_count: int
    unique_count: int
    samples: list[str]


class ImportFieldDefinition(BaseModel):
    name: str
    label: str
    required: bool
    description: str
    aliases: list[str]
    default: Any = None


class MappingSuggestion(BaseModel):
    column: str
    confidence: float = Field(ge=0, le=1)
    reason: str


class TabularPreviewResponse(BaseModel):
    filename: str
    file_format: str
    file_sha256: str
    sheets: list[str]
    selected_sheet: str | None = None
    row_count: int
    columns: list[TabularColumnPreview]
    sample_rows: list[dict[str, str]]
    field_definitions: list[ImportFieldDefinition]
    suggestions: dict[str, MappingSuggestion | None]
    warnings: list[str]


class DatasetProfileResponse(BaseModel):
    dataset_name: str
    source_format: str
    source_sheet: str | None = None
    original_filename: str
    content_sha256: str
    rows_loaded: int
    date_min: str
    date_max: str
    revenue_total: float
    currency: CurrencyCode
    currency_verified: bool
    metric_mode: str
    mapped_fields: dict[str, str]
    generated_fields: list[str]
    warnings: list[str]
    aggregate_record_proxy: bool
    record_count_label: str
    entity_count_label: str
    average_value_label: str
    average_frequency_label: str
    semantic_warning: str | None = None
    entity_warning: str | None = None
    units_available: bool
    units_label: str
    unit_warning: str | None = None
    anomaly_features: list[str]
    imported_at: datetime
    dataset_version: dict[str, str]


class FlexibleImportResponse(IngestionSummary):
    dataset_profile: DatasetProfileResponse
    mapping: dict[str, str]
    generated_fields: list[str]
    warnings: list[str]


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
