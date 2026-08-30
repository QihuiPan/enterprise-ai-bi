from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.database import Base
from data_pipeline.validation import IDENTITY_MAX_LENGTHS


class SalesRecord(Base):
    __tablename__ = "sales_records"
    __table_args__ = (
        Index("ix_sales_order_date", "order_date"),
        Index("ix_sales_customer_id", "customer_id"),
        Index("ix_sales_region_category", "region", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(IDENTITY_MAX_LENGTHS["order_id"]), unique=True, nullable=False
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    customer_id: Mapped[str] = mapped_column(
        String(IDENTITY_MAX_LENGTHS["customer_id"]), nullable=False
    )
    region: Mapped[str] = mapped_column(
        String(IDENTITY_MAX_LENGTHS["region"]), nullable=False
    )
    category: Mapped[str] = mapped_column(
        String(IDENTITY_MAX_LENGTHS["category"]), nullable=False
    )
    product: Mapped[str] = mapped_column(
        String(IDENTITY_MAX_LENGTHS["product"]), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    discount: Mapped[float] = mapped_column(Float, nullable=False)
    revenue: Mapped[float] = mapped_column(Float, nullable=False)


class DatasetProfile(Base):
    """Metadata and semantic labels for the single active analytical snapshot."""

    __tablename__ = "dataset_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    dataset_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_format: Mapped[str] = mapped_column(String(16), nullable=False)
    source_sheet: Mapped[str | None] = mapped_column(String(31), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    rows_loaded: Mapped[int] = mapped_column(Integer, nullable=False)
    date_min: Mapped[date] = mapped_column(Date, nullable=False)
    date_max: Mapped[date] = mapped_column(Date, nullable=False)
    revenue_total: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    metric_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    mapped_fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    generated_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    aggregate_record_proxy: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    record_count_label: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_count_label: Mapped[str] = mapped_column(String(80), nullable=False)
    average_value_label: Mapped[str] = mapped_column(String(120), nullable=False)
    average_frequency_label: Mapped[str] = mapped_column(String(120), nullable=False)
    semantic_warning: Mapped[str | None] = mapped_column(String(500), nullable=True)
    entity_warning: Mapped[str | None] = mapped_column(String(500), nullable=True)
    units_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    units_label: Mapped[str] = mapped_column(
        String(80), nullable=False, default="Units sold"
    )
    unit_warning: Mapped[str | None] = mapped_column(String(500), nullable=True)
    anomaly_features: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: ["revenue", "quantity", "unit_price", "discount"],
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
