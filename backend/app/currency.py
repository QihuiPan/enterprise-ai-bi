from __future__ import annotations

from typing import Literal

CurrencyCode = Literal["USD", "GBP"]

_CURRENCY_SYMBOLS: dict[CurrencyCode, str] = {
    "USD": "$",
    "GBP": "£",
}


def format_currency(value: float | int, currency: CurrencyCode = "USD") -> str:
    """Format a source-denominated value without performing FX conversion."""

    return f"{_CURRENCY_SYMBOLS[currency]}{float(value):,.2f}"
