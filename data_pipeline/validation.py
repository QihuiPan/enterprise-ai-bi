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
IDENTITY_COLUMNS = ("order_id", "customer_id", "region", "category", "product")
NUMERIC_COLUMNS = ("quantity", "unit_price", "discount")


class DataValidationError(ValueError):
    def __init__(self, issues: list[str]):
        super().__init__("; ".join(issues))
        self.issues = issues


class SalesFrameValidator:
    """Canonicalizes and validates the external sales-data contract."""

    @staticmethod
    def canonical_name(value: object) -> str:
        name = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower())
        return name.strip("_")

    def validate(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            raise DataValidationError(["The uploaded CSV contains no data rows."])

        data = frame.copy()
        data.columns = [self.canonical_name(column) for column in data.columns]
        missing = [column for column in REQUIRED_COLUMNS if column not in data.columns]
        if missing:
            raise DataValidationError(
                [f"Missing required columns: {', '.join(missing)}."]
            )

        data = data.loc[:, REQUIRED_COLUMNS].copy()
        issues: list[str] = []
        self._normalize_identities(data, issues)
        self._normalize_dates(data, issues)
        self._normalize_numbers(data, issues)
        self._validate_constraints(data, issues)
        if issues:
            raise DataValidationError(issues)

        data["quantity"] = data["quantity"].astype(int)
        data["unit_price"] = data["unit_price"].astype(float).round(2)
        data["discount"] = data["discount"].astype(float).round(4)
        data["revenue"] = (
            data["quantity"] * data["unit_price"] * (1 - data["discount"])
        ).round(2)
        return data

    @staticmethod
    def _normalize_identities(data: pd.DataFrame, issues: list[str]) -> None:
        for column in IDENTITY_COLUMNS:
            data[column] = data[column].astype("string").str.strip()
            invalid = data[column].isna() | data[column].eq("")
            if invalid.any():
                issues.append(
                    f"Column '{column}' has {int(invalid.sum())} blank values."
                )

    @staticmethod
    def _normalize_dates(data: pd.DataFrame, issues: list[str]) -> None:
        parsed_dates = pd.to_datetime(data["order_date"], errors="coerce", utc=True)
        invalid_count = int(parsed_dates.isna().sum())
        if invalid_count:
            issues.append(f"Column 'order_date' has {invalid_count} invalid dates.")
        data["order_date"] = parsed_dates.dt.tz_localize(None).dt.normalize()

    @staticmethod
    def _normalize_numbers(data: pd.DataFrame, issues: list[str]) -> None:
        for column in NUMERIC_COLUMNS:
            data[column] = pd.to_numeric(data[column], errors="coerce")
            invalid_count = int(data[column].isna().sum())
            if invalid_count:
                issues.append(
                    f"Column '{column}' has {invalid_count} non-numeric values."
                )

    @staticmethod
    def _validate_constraints(data: pd.DataFrame, issues: list[str]) -> None:
        duplicate_count = int(data["order_id"].duplicated().sum())
        if duplicate_count:
            issues.append(
                f"Column 'order_id' has {duplicate_count} duplicates."
            )
        if data["quantity"].notna().any() and (data["quantity"] <= 0).any():
            issues.append("Column 'quantity' must contain positive values.")
        if data["unit_price"].notna().any() and (data["unit_price"] < 0).any():
            issues.append("Column 'unit_price' cannot contain negative values.")
        if data["discount"].notna().any() and (
            ~data["discount"].between(0, 1)
        ).any():
            issues.append("Column 'discount' must be between 0 and 1.")


default_sales_validator = SalesFrameValidator()


def validate_and_transform(frame: pd.DataFrame) -> pd.DataFrame:
    return default_sales_validator.validate(frame)
