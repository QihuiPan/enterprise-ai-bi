from __future__ import annotations

import pandas as pd
import pytest

from data_pipeline.validation import DataValidationError, validate_and_transform


def valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Order ID": "A-1",
                "Order Date": "2026-01-10",
                "Customer ID": "C-1",
                "Region": "North",
                "Category": "Analytics",
                "Product": "Insight Pro",
                "Quantity": 2,
                "Unit Price": 100,
                "Discount": 0.1,
            }
        ]
    )


def test_validation_canonicalizes_and_derives_revenue() -> None:
    result = validate_and_transform(valid_frame())
    assert list(result.columns)[-1] == "revenue"
    assert result.iloc[0]["revenue"] == 180.0
    assert result.iloc[0]["quantity"] == 2


def test_validation_rejects_discount_outside_range() -> None:
    frame = valid_frame()
    frame.loc[0, "Discount"] = 1.5
    with pytest.raises(DataValidationError, match="between 0 and 1"):
        validate_and_transform(frame)


def test_validation_rejects_duplicate_orders() -> None:
    frame = pd.concat([valid_frame(), valid_frame()], ignore_index=True)
    with pytest.raises(DataValidationError, match="duplicates"):
        validate_and_transform(frame)


def test_validation_rejects_headers_that_collide_after_normalization() -> None:
    frame = valid_frame()
    frame["Order-ID"] = "A-2"

    with pytest.raises(DataValidationError, match="collide.*order_id"):
        validate_and_transform(frame)


@pytest.mark.parametrize(
    "column", ["Order ID", "Customer ID", "Region", "Category", "Product"]
)
def test_validation_rejects_postgresql_unsafe_nul_in_identity_columns(column) -> None:
    frame = valid_frame()
    frame.loc[0, column] = "unsafe\x00value"

    with pytest.raises(DataValidationError, match="NUL control character"):
        validate_and_transform(frame)


@pytest.mark.parametrize(
    "value",
    ["2024-01-01T00:30:00+14:00", "2024-01-01T00:30:00+14"],
)
def test_validation_rejects_timezone_aware_dates_without_shifting_calendar_day(
    value,
) -> None:
    frame = valid_frame()
    frame.loc[0, "Order Date"] = value

    with pytest.raises(DataValidationError, match="timezone-aware"):
        validate_and_transform(frame)


@pytest.mark.parametrize(
    ("column", "maximum"),
    [
        ("Order ID", 80),
        ("Customer ID", 80),
        ("Region", 80),
        ("Category", 80),
        ("Product", 120),
    ],
)
def test_validation_enforces_database_text_boundaries(column, maximum) -> None:
    boundary = valid_frame()
    boundary.loc[0, column] = "x" * maximum
    canonical = column.lower().replace(" ", "_")
    assert len(validate_and_transform(boundary).iloc[0][canonical]) == maximum

    too_long = valid_frame()
    too_long.loc[0, column] = "x" * (maximum + 1)
    with pytest.raises(DataValidationError, match=f"longer than {maximum}"):
        validate_and_transform(too_long)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("Quantity", 1.9, "whole numbers"),
        ("Quantity", float("inf"), "non-finite"),
        ("Unit Price", float("inf"), "non-finite"),
        ("Discount", float("-inf"), "non-finite"),
        ("Quantity", 2_147_483_648, "cannot exceed 2147483647"),
    ],
)
def test_validation_rejects_unsafe_numeric_values(column, value, message) -> None:
    frame = valid_frame()
    frame.loc[0, column] = value
    with pytest.raises(DataValidationError, match=message):
        validate_and_transform(frame)


def test_validation_accepts_maximum_database_quantity() -> None:
    frame = valid_frame()
    frame.loc[0, "Quantity"] = 2_147_483_647
    assert validate_and_transform(frame).iloc[0]["quantity"] == 2_147_483_647


def test_validation_rejects_unit_prices_above_business_safety_limit() -> None:
    frame = valid_frame()
    frame["Unit Price"] = frame["Unit Price"].astype(float)
    frame.loc[0, "Unit Price"] = 1e308
    with pytest.raises(DataValidationError, match="unit_price.*cannot exceed"):
        validate_and_transform(frame)


def test_validation_rejects_aggregate_revenue_above_business_safety_limit() -> None:
    frame = pd.concat([valid_frame()] * 2, ignore_index=True)
    frame.loc[:, "Order ID"] = ["A-1", "A-2"]
    frame.loc[:, "Quantity"] = 1_000
    frame.loc[:, "Unit Price"] = 1_000_000_000_000
    frame.loc[:, "Discount"] = 0

    with pytest.raises(DataValidationError, match="Aggregate 'revenue'.*cannot exceed"):
        validate_and_transform(frame)
