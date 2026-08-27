from __future__ import annotations

import re

import pandas as pd

REQUIRED_COLUMNS = (
    "order_id",
    "order_date",
    "customer_id",
    "region",
    "category",
    "product",
    "quantity",
    "unit_price",
    "discount",
)


class DataValidationError(ValueError):
    def __init__(self, issues: list[str]):
        super().__init__("; ".join(issues))
        self.issues = issues


def _canonical_name(value: object) -> str:
    name = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower())
    return name.strip("_")


def validate_and_transform(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        raise DataValidationError(["The uploaded CSV contains no data rows."])

    data = frame.copy()
    data.columns = [_canonical_name(column) for column in data.columns]
    missing = [column for column in REQUIRED_COLUMNS if column not in data.columns]
    if missing:
        raise DataValidationError([f"Missing required columns: {', '.join(missing)}."])

    data = data.loc[:, REQUIRED_COLUMNS].copy()
    issues: list[str] = []

    for column in ("order_id", "customer_id", "region", "category", "product"):
        data[column] = data[column].astype("string").str.strip()
        invalid = data[column].isna() | data[column].eq("")
        if invalid.any():
            issues.append(f"Column '{column}' has {int(invalid.sum())} blank values.")

    parsed_dates = pd.to_datetime(data["order_date"], errors="coerce", utc=True)
    if parsed_dates.isna().any():
        issues.append(f"Column 'order_date' has {int(parsed_dates.isna().sum())} invalid dates.")
    data["order_date"] = parsed_dates.dt.tz_localize(None).dt.normalize()

    for column in ("quantity", "unit_price", "discount"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
        if data[column].isna().any():
            issues.append(
                f"Column '{column}' has {int(data[column].isna().sum())} non-numeric values."
            )

    if data["order_id"].duplicated().any():
        issues.append(
            f"Column 'order_id' has {int(data['order_id'].duplicated().sum())} duplicates."
        )
    if data["quantity"].notna().any() and (data["quantity"] <= 0).any():
        issues.append("Column 'quantity' must contain positive values.")
    if data["unit_price"].notna().any() and (data["unit_price"] < 0).any():
        issues.append("Column 'unit_price' cannot contain negative values.")
    if data["discount"].notna().any() and (~data["discount"].between(0, 1)).any():
        issues.append("Column 'discount' must be between 0 and 1.")

    if issues:
        raise DataValidationError(issues)

    data["quantity"] = data["quantity"].astype(int)
    data["unit_price"] = data["unit_price"].astype(float).round(2)
    data["discount"] = data["discount"].astype(float).round(4)
    data["revenue"] = (data["quantity"] * data["unit_price"] * (1 - data["discount"])).round(2)
    return data
