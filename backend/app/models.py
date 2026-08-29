from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, Index, Integer, String
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
