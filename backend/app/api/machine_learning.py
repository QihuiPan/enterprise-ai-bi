from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from backend.app.api.dependencies import DbSession
from backend.app.services import machine_learning

router = APIRouter(prefix="/api/ml", tags=["machine-learning"])


def _run_model(operation: Callable[[], dict]) -> dict:
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/forecast")
def get_forecast(
    session: DbSession,
    horizon: Annotated[int, Query(ge=1, le=12)] = 3,
) -> dict:
    return _run_model(lambda: machine_learning.revenue_forecast(session, horizon))


@router.get("/segments")
def get_segments(
    session: DbSession,
    clusters: Annotated[int, Query(ge=2, le=8)] = 4,
) -> dict:
    return _run_model(lambda: machine_learning.customer_segments(session, clusters))


@router.get("/anomalies")
def get_anomalies(
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict:
    return _run_model(lambda: machine_learning.sales_anomalies(session, limit))
