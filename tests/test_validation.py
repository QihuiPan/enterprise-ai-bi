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
