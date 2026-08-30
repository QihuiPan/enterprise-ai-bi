from __future__ import annotations

import re

import numpy as np
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
CANONICAL_COLUMNS = (*REQUIRED_COLUMNS, "revenue")
IDENTITY_COLUMNS = ("order_id", "customer_id", "region", "category", "product")
IDENTITY_MAX_LENGTHS = {
    "order_id": 80,
    "customer_id": 80,
    "region": 80,
    "category": 80,
    "product": 120,
}
NUMERIC_COLUMNS = ("quantity", "unit_price", "discount")
POSTGRES_INTEGER_MAX = 2_147_483_647
MAX_UNIT_PRICE = 1_000_000_000_000.0
MAX_DATASET_REVENUE = 1_000_000_000_000_000.0


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

    def validate(
        self,
        frame: pd.DataFrame,
        *,
        preserve_revenue: bool = False,
        preserve_component_precision: bool = False,
    ) -> pd.DataFrame:
        if frame.empty:
            raise DataValidationError(["The uploaded CSV contains no data rows."])

        data = frame.copy()
        canonical_columns = [self.canonical_name(column) for column in data.columns]
        duplicate_columns = sorted(
            set(
                pd.Index(canonical_columns)[
                    pd.Index(canonical_columns).duplicated(keep=False)
                ].tolist()
            )
        )
        if duplicate_columns:
            raise DataValidationError(
                [
                    "Column names collide after normalization: "
                    f"{', '.join(duplicate_columns)}."
                ]
            )
        data.columns = canonical_columns
        required_columns = CANONICAL_COLUMNS if preserve_revenue else REQUIRED_COLUMNS
        missing = [column for column in required_columns if column not in data.columns]
        if missing:
            raise DataValidationError(
                [f"Missing required columns: {', '.join(missing)}."]
            )

        data = data.loc[:, required_columns].copy()
        issues: list[str] = []
        self._normalize_identities(data, issues)
        self._normalize_dates(data, issues)
        self._normalize_numbers(data, issues)
        if preserve_revenue:
            self._normalize_revenue(data, issues)
        self._validate_constraints(data, issues)
        if preserve_revenue:
            self._validate_revenue_constraints(data, issues)
        if issues:
            raise DataValidationError(issues)

        data["quantity"] = data["quantity"].astype(int)
        data["unit_price"] = data["unit_price"].astype(float)
        data["discount"] = data["discount"].astype(float)
        if not preserve_revenue and not preserve_component_precision:
            data["unit_price"] = data["unit_price"].round(2)
            data["discount"] = data["discount"].round(4)
        if preserve_revenue:
            data["revenue"] = data["revenue"].astype(float)
        else:
            with np.errstate(over="ignore", invalid="ignore"):
                data["revenue"] = (
                    data["quantity"] * data["unit_price"] * (1 - data["discount"])
                ).round(2)
        non_finite_revenue = ~np.isfinite(data["revenue"])
        if non_finite_revenue.any():
            raise DataValidationError(
                [
                    "Derived 'revenue' has "
                    f"{int(non_finite_revenue.sum())} non-finite values."
                ]
            )
        with np.errstate(over="ignore", invalid="ignore"):
            revenue_total = data["revenue"].to_numpy(dtype=float).sum()
        if not np.isfinite(revenue_total):
            raise DataValidationError(
                ["Aggregate 'revenue' is non-finite for the uploaded dataset."]
            )
        if revenue_total > MAX_DATASET_REVENUE:
            raise DataValidationError(
                [
                    "Aggregate 'revenue' cannot exceed "
                    f"{MAX_DATASET_REVENUE:.0f} for one analytical dataset."
                ]
            )
        return data

    @staticmethod
    def _normalize_revenue(data: pd.DataFrame, issues: list[str]) -> None:
        data["revenue"] = pd.to_numeric(data["revenue"], errors="coerce")
        invalid_count = int(data["revenue"].isna().sum())
        if invalid_count:
            issues.append(f"Column 'revenue' has {invalid_count} non-numeric values.")
        non_finite = data["revenue"].notna() & ~np.isfinite(data["revenue"])
        if non_finite.any():
            issues.append(
                f"Column 'revenue' has {int(non_finite.sum())} non-finite values."
            )

    @staticmethod
    def _validate_revenue_constraints(
        data: pd.DataFrame, issues: list[str]
    ) -> None:
        finite_revenue = data["revenue"].notna() & np.isfinite(data["revenue"])
        if (finite_revenue & data["revenue"].lt(0)).any():
            issues.append("Column 'revenue' cannot contain negative values.")

    @staticmethod
    def _normalize_identities(data: pd.DataFrame, issues: list[str]) -> None:
        for column in IDENTITY_COLUMNS:
            data[column] = data[column].astype("string").str.strip()
            invalid = data[column].isna() | data[column].eq("")
            if invalid.any():
                issues.append(
                    f"Column '{column}' has {int(invalid.sum())} blank values."
                )
            nul_characters = data[column].str.contains("\x00", regex=False, na=False)
            if nul_characters.any():
                issues.append(
                    f"Column '{column}' has {int(nul_characters.sum())} values "
                    "containing a NUL control character."
                )
            too_long = (
                data[column]
                .str.len()
                .gt(IDENTITY_MAX_LENGTHS[column])
                .fillna(False)
            )
            if too_long.any():
                issues.append(
                    f"Column '{column}' has {int(too_long.sum())} values longer than "
                    f"{IDENTITY_MAX_LENGTHS[column]} characters."
                )

    @staticmethod
    def _normalize_dates(data: pd.DataFrame, issues: list[str]) -> None:
        parsed_for_timezone = pd.to_datetime(
            data["order_date"], errors="coerce", format="mixed"
        )
        timezone_markers = parsed_for_timezone.map(
            lambda value: not pd.isna(value)
            and getattr(value, "tzinfo", None) is not None
        )
        if timezone_markers.any():
            issues.append(
                "Column 'order_date' has "
                f"{int(timezone_markers.sum())} timezone-aware values; provide local "
                "calendar dates without offsets."
            )
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
            non_finite = data[column].notna() & ~np.isfinite(data[column])
            if non_finite.any():
                issues.append(
                    f"Column '{column}' has {int(non_finite.sum())} non-finite values."
                )

    @staticmethod
    def _validate_constraints(data: pd.DataFrame, issues: list[str]) -> None:
        duplicate_count = int(data["order_id"].duplicated().sum())
        if duplicate_count:
            issues.append(
                f"Column 'order_id' has {duplicate_count} duplicates."
            )
        finite_quantity = data["quantity"].notna() & np.isfinite(data["quantity"])
        if (finite_quantity & data["quantity"].le(0)).any():
            issues.append("Column 'quantity' must contain positive values.")
        if (finite_quantity & data["quantity"].mod(1).ne(0)).any():
            issues.append("Column 'quantity' must contain whole numbers.")
        if (finite_quantity & data["quantity"].gt(POSTGRES_INTEGER_MAX)).any():
            issues.append(
                f"Column 'quantity' cannot exceed {POSTGRES_INTEGER_MAX}."
            )

        finite_price = data["unit_price"].notna() & np.isfinite(data["unit_price"])
        if (finite_price & data["unit_price"].lt(0)).any():
            issues.append("Column 'unit_price' cannot contain negative values.")
        if (finite_price & data["unit_price"].gt(MAX_UNIT_PRICE)).any():
            issues.append(
                f"Column 'unit_price' cannot exceed {MAX_UNIT_PRICE:.0f}."
            )
        finite_discount = data["discount"].notna() & np.isfinite(data["discount"])
        if (finite_discount & ~data["discount"].between(0, 1)).any():
            issues.append("Column 'discount' must be between 0 and 1.")


default_sales_validator = SalesFrameValidator()


def validate_and_transform(frame: pd.DataFrame) -> pd.DataFrame:
    return default_sales_validator.validate(frame)
