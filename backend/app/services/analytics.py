from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import SalesRecord

BREAKDOWN_DIMENSIONS = frozenset({"region", "category", "product"})
TREND_FREQUENCIES = {"day": "D", "month": "M"}


class NoDataError(RuntimeError):
    pass


def sales_frame(session: Session) -> pd.DataFrame:
    records = session.scalars(select(SalesRecord).order_by(SalesRecord.order_date)).all()
    if not records:
        raise NoDataError("No sales data is loaded. Upload a CSV or load the demo dataset.")
    return pd.DataFrame(
        [
            {
                "order_id": item.order_id,
                "order_date": pd.Timestamp(item.order_date),
                "customer_id": item.customer_id,
                "region": item.region,
                "category": item.category,
                "product": item.product,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "discount": item.discount,
                "revenue": item.revenue,
            }
            for item in records
        ]
    )


@dataclass(frozen=True)
class SalesAnalytics:
    """Pure analytics over one validated, request-scoped sales snapshot."""

    frame: pd.DataFrame

    @classmethod
    def from_session(cls, session: Session) -> SalesAnalytics:
        return cls(sales_frame(session))

    def kpis(self) -> dict:
        frame = self.frame
        monthly_revenue = (
            frame.assign(period=frame["order_date"].dt.to_period("M"))
            .groupby("period")["revenue"]
            .sum()
            .sort_index()
        )
        latest_revenue = float(monthly_revenue.iloc[-1])
        previous_revenue = (
            float(monthly_revenue.iloc[-2]) if len(monthly_revenue) > 1 else 0.0
        )
        change = (
            (latest_revenue - previous_revenue) / previous_revenue * 100
            if previous_revenue
            else 0
        )
        return {
            "total_revenue": round(float(frame["revenue"].sum()), 2),
            "order_count": int(frame["order_id"].nunique()),
            "customer_count": int(frame["customer_id"].nunique()),
            "average_order_value": round(float(frame["revenue"].mean()), 2),
            "units_sold": int(frame["quantity"].sum()),
            "latest_month": str(monthly_revenue.index[-1]),
            "latest_month_revenue": round(latest_revenue, 2),
            "month_over_month_change_pct": round(float(change), 2),
            "data_start": frame["order_date"].min().date().isoformat(),
            "data_end": frame["order_date"].max().date().isoformat(),
        }

    def trend(self, grain: str = "month") -> list[dict]:
        try:
            frequency = TREND_FREQUENCIES[grain]
        except KeyError as exc:
            raise ValueError("Grain must be 'day' or 'month'.") from exc
        grouped = (
            self.frame.assign(period=self.frame["order_date"].dt.to_period(frequency))
            .groupby("period", as_index=False)
            .agg(revenue=("revenue", "sum"), orders=("order_id", "nunique"))
        )
        return [
            {
                "period": str(row.period),
                "revenue": round(float(row.revenue), 2),
                "orders": int(row.orders),
            }
            for row in grouped.itertuples(index=False)
        ]

    def breakdown(self, dimension: str) -> list[dict]:
        if dimension not in BREAKDOWN_DIMENSIONS:
            allowed = ", ".join(sorted(BREAKDOWN_DIMENSIONS))
            raise ValueError(f"Dimension must be one of: {allowed}.")
        grouped = (
            self.frame.groupby(dimension, as_index=False)
            .agg(
                revenue=("revenue", "sum"),
                orders=("order_id", "nunique"),
                units=("quantity", "sum"),
            )
            .sort_values("revenue", ascending=False)
        )
        total = float(grouped["revenue"].sum())
        return [
            {
                "name": str(getattr(row, dimension)),
                "revenue": round(float(row.revenue), 2),
                "revenue_share_pct": (
                    round(float(row.revenue) / total * 100, 2) if total else 0
                ),
                "orders": int(row.orders),
                "units": int(row.units),
            }
            for row in grouped.itertuples(index=False)
        ]

    def explain_revenue_change(self) -> dict:
        frame = self.frame.assign(
            period=self.frame["order_date"].dt.to_period("M")
        )
        periods = sorted(frame["period"].unique())
        if len(periods) < 2:
            raise NoDataError(
                "At least two months of sales are required for change analysis."
            )
        previous_period, current_period = periods[-2], periods[-1]
        comparison = frame[frame["period"].isin([previous_period, current_period])]
        totals = comparison.groupby("period")["revenue"].sum()
        previous = float(totals.get(previous_period, 0))
        current = float(totals.get(current_period, 0))
        delta = current - previous
        change_pct = delta / previous * 100 if previous else 0

        contributors: dict[str, list[dict]] = {}
        for dimension in ("region", "category"):
            pivot = comparison.pivot_table(
                index=dimension,
                columns="period",
                values="revenue",
                aggfunc="sum",
                fill_value=0,
            )
            pivot["change"] = pivot.get(current_period, 0) - pivot.get(
                previous_period, 0
            )
            contributors[dimension] = [
                {"name": str(index), "change": round(float(value), 2)}
                for index, value in pivot["change"].sort_values().items()
            ]

        return {
            "previous_period": str(previous_period),
            "current_period": str(current_period),
            "previous_revenue": round(previous, 2),
            "current_revenue": round(current, 2),
            "change": round(delta, 2),
            "change_pct": round(float(change_pct), 2),
            "contributors": contributors,
        }


def kpis(session: Session) -> dict:
    return SalesAnalytics.from_session(session).kpis()


def trend(session: Session, grain: str = "month") -> list[dict]:
    return SalesAnalytics.from_session(session).trend(grain)


def breakdown(session: Session, dimension: str) -> list[dict]:
    return SalesAnalytics.from_session(session).breakdown(dimension)


def explain_revenue_change(session: Session) -> dict:
    return SalesAnalytics.from_session(session).explain_revenue_change()
