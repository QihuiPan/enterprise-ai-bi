from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


class NoMatchingSalesError(RuntimeError):
    pass


@dataclass(frozen=True)
class SalesFilters:
    start_date: date | None = None
    end_date: date | None = None
    region: str | None = None
    category: str | None = None
    product: str | None = None

    def apply(self, frame: pd.DataFrame) -> pd.DataFrame:
        filtered = frame
        if self.start_date is not None:
            filtered = filtered[filtered["order_date"] >= pd.Timestamp(self.start_date)]
        if self.end_date is not None:
            filtered = filtered[filtered["order_date"] <= pd.Timestamp(self.end_date)]
        for column in ("region", "category", "product"):
            value = getattr(self, column)
            if value is not None:
                filtered = filtered[filtered[column] == value]
        if filtered.empty:
            raise NoMatchingSalesError("No sales data matches the selected filters.")
        return filtered.reset_index(drop=True)

    @property
    def active(self) -> dict[str, str]:
        values = {
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "region": self.region,
            "category": self.category,
            "product": self.product,
        }
        return {key: value for key, value in values.items() if value is not None}


def filter_options(frame: pd.DataFrame) -> dict:
    return {
        "date_min": frame["order_date"].min().date().isoformat(),
        "date_max": frame["order_date"].max().date().isoformat(),
        "regions": sorted(frame["region"].dropna().astype(str).unique().tolist()),
        "categories": sorted(frame["category"].dropna().astype(str).unique().tolist()),
        "products": sorted(frame["product"].dropna().astype(str).unique().tolist()),
    }
