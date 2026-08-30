from __future__ import annotations

from typing import Literal, cast

from sqlalchemy.orm import Session

CurrencyCode = Literal["USD", "GBP"]

_CURRENCY_SYMBOLS: dict[CurrencyCode, str] = {
    "USD": "$",
    "GBP": "£",
}


def format_currency(value: float | int, currency: CurrencyCode = "USD") -> str:
    """Format a source-denominated value without performing FX conversion."""

    return f"{_CURRENCY_SYMBOLS[currency]}{float(value):,.2f}"


def resolve_source_currency(
    session: Session, requested: CurrencyCode = "USD"
) -> CurrencyCode:
    """Use persisted source provenance instead of relabelling active money."""

    from backend.app.models import DatasetProfile

    profile = session.get(DatasetProfile, 1)
    unverified_legacy = bool(
        profile is not None and profile.source_format == "database"
    )
    if (
        profile is not None
        and not unverified_legacy
        and profile.currency in _CURRENCY_SYMBOLS
    ):
        return cast(CurrencyCode, profile.currency)
    return requested
