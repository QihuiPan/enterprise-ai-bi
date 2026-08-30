from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter

from backend.app.api.dependencies import DbSession, SalesFilterParams
from backend.app.dataset_version import active_dataset_version
from backend.app.services.business import BusinessIntelligence

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _optional_model(operation: Callable[[], dict]) -> tuple[dict | None, str | None]:
    try:
        return operation(), None
    except ValueError as exc:
        return None, str(exc)


@router.get("")
def get_dashboard(session: DbSession, filters: SalesFilterParams) -> dict:
    """Build the dashboard from one filtered database snapshot."""

    dataset_version = active_dataset_version(session)
    business = BusinessIntelligence(session, filters)
    forecast, forecast_error = _optional_model(
        lambda: business.machine_learning.revenue_forecast(horizon=3)
    )
    segments, segments_error = _optional_model(
        business.machine_learning.customer_segments
    )
    anomalies, anomalies_error = _optional_model(
        lambda: business.machine_learning.sales_anomalies(limit=6)
    )
    model_errors = {
        name: error
        for name, error in (
            ("forecast", forecast_error),
            ("segments", segments_error),
            ("anomalies", anomalies_error),
        )
        if error is not None
    }
    return {
        "kpis": business.analytics.kpis(),
        "trends": business.analytics.trend(),
        "regions": business.analytics.breakdown("region"),
        "products": business.analytics.breakdown("product")[:10],
        "forecast": forecast,
        "segments": segments,
        "anomalies": anomalies,
        "model_errors": model_errors,
        "dataset_version": dataset_version,
    }
