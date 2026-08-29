from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import SalesRecord
from backend.app.services.filtering import NoMatchingSalesError, SalesFilters

BREAKDOWN_DIMENSIONS = frozenset({"region", "category", "product"})
TREND_FREQUENCIES = {"day": "D", "month": "M"}
CHANGE_FREQUENCIES = {"month": "M", "quarter": "Q"}


class NoDataError(RuntimeError):
    pass


_SALES_COLUMNS = (
    "order_id",
    "order_date",
    "customer_id",
    "region",
    "category",
    "product",
    "quantity",
    "unit_price",
    "discount",
    "revenue",
)


def sales_frame(
    session: Session, filters: SalesFilters | None = None
) -> pd.DataFrame:
    """Read only required columns and push dashboard filters into SQL."""

    statement = select(*(getattr(SalesRecord, name) for name in _SALES_COLUMNS))
    if filters:
        if filters.start_date is not None:
            statement = statement.where(SalesRecord.order_date >= filters.start_date)
        if filters.end_date is not None:
            statement = statement.where(SalesRecord.order_date <= filters.end_date)
        for column in ("region", "category", "product"):
            value = getattr(filters, column)
            if value is not None:
                statement = statement.where(getattr(SalesRecord, column) == value)

    records = session.execute(
        statement.order_by(SalesRecord.order_date)
    ).mappings().all()
    if not records:
        if filters and filters.active:
            raise NoMatchingSalesError("No sales data matches the selected filters.")
        raise NoDataError("No sales data is loaded. Upload a CSV or load the demo dataset.")

    frame = pd.DataFrame.from_records(records, columns=_SALES_COLUMNS)
    frame["order_date"] = pd.to_datetime(frame["order_date"])
    return frame


def is_monthly_aggregate_input(dates: pd.Series) -> bool:
    """Return whether every record uses a month-start aggregate label."""

    return bool(dates.dt.is_month_start.all())


def period_is_complete(dates: pd.Series, period: pd.Period) -> bool:
    """Check calendar-period coverage for transaction or monthly aggregate data."""

    if is_monthly_aggregate_input(dates):
        calendar_start = pd.Timestamp(period.start_time).normalize()
        calendar_end = pd.Timestamp(period.end_time).normalize()
        period_dates = dates[(dates >= calendar_start) & (dates <= calendar_end)]
        observed_months = set(period_dates.dt.to_period("M").unique())
        expected_months = set(
            pd.period_range(period.start_time, period.end_time, freq="M")
        )
        return observed_months == expected_months

    calendar_start = pd.Timestamp(period.start_time).normalize()
    calendar_end = pd.Timestamp(period.end_time).normalize()
    data_start = pd.Timestamp(dates.min()).normalize()
    data_end = pd.Timestamp(dates.max()).normalize()
    return data_start <= calendar_start and data_end >= calendar_end


@dataclass(frozen=True)
class SalesAnalytics:
    """Pure analytics over one validated, request-scoped sales snapshot."""

    frame: pd.DataFrame

    @classmethod
    def from_session(
        cls, session: Session, filters: SalesFilters | None = None
    ) -> SalesAnalytics:
        return cls(sales_frame(session, filters))

    @staticmethod
    def _period_label(period: pd.Period) -> str:
        value = str(period)
        return value.replace("Q", "-Q") if "Q" in value else value

    def _period_coverage(self, period: pd.Period) -> dict:
        dates = self.frame["order_date"]
        monthly_aggregate_input = is_monthly_aggregate_input(dates)
        rows = self.frame[dates.dt.to_period(period.freqstr) == period]
        calendar_start = pd.Timestamp(period.start_time).normalize()
        calendar_end = pd.Timestamp(period.end_time).normalize()
        return {
            "period": self._period_label(period),
            "calendar_start": calendar_start.date().isoformat(),
            "calendar_end": calendar_end.date().isoformat(),
            "observed_start": rows["order_date"].min().date().isoformat(),
            "observed_end": rows["order_date"].max().date().isoformat(),
            "complete": period_is_complete(dates, period),
            "coverage_basis": (
                "monthly_aggregate_labels"
                if monthly_aggregate_input
                else "transaction_observation_window"
            ),
        }

    def record_semantics(self) -> dict:
        order_ids = self.frame["order_id"].astype(str)
        sources = (
            (
                "UCI-",
                "UCI Online Retail II",
                "Customer-country-day records",
                "Customers",
                "Average aggregate record value",
                "Average aggregate records",
                "The generated IDs represent customer-country-day aggregates, not "
                "source orders; this value is not source average order value.",
                "Customer IDs retain source customer identifiers.",
            ),
            (
                "IA2024-",
                "Iowa Liquor Sales 2024",
                "Store-county-category-month records",
                "Stores",
                "Average aggregate record value",
                "Average aggregate records",
                "The generated IDs represent store-county-category-month aggregates, "
                "not source transactions; this value is not source average order value.",
                "Entity IDs represent source stores.",
            ),
            (
                "M5-",
                "Walmart M5",
                "Store-category-day records",
                "Stores",
                "Average aggregate record value",
                "Average aggregate records",
                "The generated IDs represent store-category-day aggregates and M5 "
                "contains no order or shopper facts; this value is not average order "
                "value.",
                "Entity IDs represent stores because M5 contains no shoppers.",
            ),
        )
        for (
            prefix,
            source,
            record_label,
            entity_label,
            average_label,
            frequency_label,
            warning,
            entity_warning,
        ) in sources:
            if order_ids.str.startswith(prefix).all():
                return {
                    "source": source,
                    "aggregate_record_proxy": True,
                    "record_count_label": record_label,
                    "entity_count_label": entity_label,
                    "average_value_label": average_label,
                    "average_frequency_label": frequency_label,
                    "warning": warning,
                    "entity_warning": entity_warning,
                }
        return {
            "source": "Uploaded order-level sales",
            "aggregate_record_proxy": False,
            "record_count_label": "Orders",
            "entity_count_label": "Customers",
            "average_value_label": "Average order value",
            "average_frequency_label": "Average orders",
            "warning": None,
            "entity_warning": None,
        }

    @staticmethod
    def _comparison_status(
        *, adjacent: bool, previous: float, periods_complete: bool
    ) -> str:
        if not adjacent:
            return "non_consecutive_periods"
        if previous == 0:
            return "zero_baseline"
        if not periods_complete:
            return "partial_periods"
        return "available"

    def kpis(self) -> dict:
        frame = self.frame
        order_revenue = frame.groupby("order_id")["revenue"].sum()
        monthly_revenue = (
            frame.assign(period=frame["order_date"].dt.to_period("M"))
            .groupby("period")["revenue"]
            .sum()
            .sort_index()
        )
        latest_revenue = float(monthly_revenue.iloc[-1])
        has_comparison_period = len(monthly_revenue) > 1
        periods_are_adjacent = (
            monthly_revenue.index[-1].ordinal - monthly_revenue.index[-2].ordinal == 1
            if has_comparison_period
            else False
        )
        previous_revenue = (
            float(monthly_revenue.iloc[-2]) if has_comparison_period else None
        )
        comparison_coverage = (
            [
                self._period_coverage(monthly_revenue.index[-2]),
                self._period_coverage(monthly_revenue.index[-1]),
            ]
            if has_comparison_period
            else [self._period_coverage(monthly_revenue.index[-1])]
        )
        periods_complete = all(item["complete"] for item in comparison_coverage)
        change = None
        if (
            periods_are_adjacent
            and periods_complete
            and previous_revenue not in {None, 0.0}
        ):
            change = (latest_revenue - previous_revenue) / previous_revenue * 100
        change_status = (
            self._comparison_status(
                adjacent=periods_are_adjacent,
                previous=previous_revenue or 0.0,
                periods_complete=periods_complete,
            )
            if has_comparison_period
            else "insufficient_history"
        )
        return {
            "total_revenue": round(float(frame["revenue"].sum()), 2),
            "order_count": int(frame["order_id"].nunique()),
            "customer_count": int(frame["customer_id"].nunique()),
            "average_order_value": round(float(order_revenue.mean()), 2),
            "units_sold": int(frame["quantity"].sum()),
            "latest_month": str(monthly_revenue.index[-1]),
            "latest_month_revenue": round(latest_revenue, 2),
            "month_over_month_change_pct": (
                round(float(change), 2) if change is not None else None
            ),
            "month_over_month_available": change is not None,
            "month_over_month_status": change_status,
            "month_over_month_period_coverage": comparison_coverage,
            "record_semantics": self.record_semantics(),
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

    def explain_revenue_change(
        self,
        grain: str = "month",
        *,
        completed_only: bool = False,
        period_offset: int = 0,
    ) -> dict:
        try:
            frequency = CHANGE_FREQUENCIES[grain]
        except KeyError as exc:
            raise ValueError("Change grain must be 'month' or 'quarter'.") from exc

        frame = self.frame.assign(
            period=self.frame["order_date"].dt.to_period(frequency)
        )
        periods = sorted(frame["period"].unique())
        if completed_only:
            periods = [
                period for period in periods if self._period_coverage(period)["complete"]
            ]
        if period_offset < 0:
            raise ValueError("Change period offset cannot be negative.")
        if len(periods) < 2 + period_offset:
            raise NoDataError(
                f"At least two {'complete ' if completed_only else ''}{grain}s of "
                "sales are required for change analysis."
            )
        current_index = -(period_offset + 1)
        previous_index = -(period_offset + 2)
        previous_period, current_period = (
            periods[previous_index],
            periods[current_index],
        )
        periods_are_adjacent = current_period.ordinal - previous_period.ordinal == 1
        period_coverage = [
            self._period_coverage(previous_period),
            self._period_coverage(current_period),
        ]
        periods_complete = all(item["complete"] for item in period_coverage)
        comparison = frame[frame["period"].isin([previous_period, current_period])]
        totals = comparison.groupby("period")["revenue"].sum()
        previous = float(totals.get(previous_period, 0))
        current = float(totals.get(current_period, 0))
        delta = current - previous
        comparison_status = self._comparison_status(
            adjacent=periods_are_adjacent,
            previous=previous,
            periods_complete=periods_complete,
        )
        change_pct = delta / previous * 100 if comparison_status == "available" else None

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
            "period_grain": grain,
            "completed_periods_only": completed_only,
            "period_offset": period_offset,
            "previous_period": self._period_label(previous_period),
            "current_period": self._period_label(current_period),
            "previous_revenue": round(previous, 2),
            "current_revenue": round(current, 2),
            "change": round(delta, 2),
            "change_pct": (
                round(float(change_pct), 2) if change_pct is not None else None
            ),
            "change_pct_available": change_pct is not None,
            "comparison_status": comparison_status,
            "period_coverage": period_coverage,
            "contributors": contributors,
        }


def kpis(session: Session, filters: SalesFilters | None = None) -> dict:
    return SalesAnalytics.from_session(session, filters).kpis()


def trend(
    session: Session, grain: str = "month", filters: SalesFilters | None = None
) -> list[dict]:
    return SalesAnalytics.from_session(session, filters).trend(grain)


def breakdown(
    session: Session, dimension: str, filters: SalesFilters | None = None
) -> list[dict]:
    return SalesAnalytics.from_session(session, filters).breakdown(dimension)


def explain_revenue_change(session: Session) -> dict:
    return SalesAnalytics.from_session(session).explain_revenue_change()


def available_filters(session: Session) -> dict:
    date_min, date_max = session.execute(
        select(func.min(SalesRecord.order_date), func.max(SalesRecord.order_date))
    ).one()
    if date_min is None or date_max is None:
        raise NoDataError("No sales data is loaded. Upload a CSV or load the demo dataset.")

    def distinct_values(column: str) -> list[str]:
        field = getattr(SalesRecord, column)
        return list(session.scalars(select(field).distinct().order_by(field)).all())

    return {
        "date_min": date_min.isoformat(),
        "date_max": date_max.isoformat(),
        "regions": distinct_values("region"),
        "categories": distinct_values("category"),
        "products": distinct_values("product"),
    }
