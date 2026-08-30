from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from backend.app.api.dependencies import DbSession, SalesFilterParams
from backend.app.dataset_version import active_dataset_version
from backend.app.services import analytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/filter-options")
def get_filter_options(session: DbSession) -> dict:
    dataset_version = active_dataset_version(session)
    return {
        **analytics.available_filters(session),
        "dataset_version": dataset_version,
    }


@router.get("/kpis")
def get_kpis(session: DbSession, filters: SalesFilterParams) -> dict:
    return analytics.kpis(session, filters)


@router.get("/trends")
def get_trends(
    session: DbSession,
    filters: SalesFilterParams,
    grain: Annotated[str, Query(pattern="^(day|month)$")] = "month",
) -> list[dict]:
    return analytics.trend(session, grain=grain, filters=filters)


@router.get("/breakdown/{dimension}")
def get_breakdown(
    dimension: str, session: DbSession, filters: SalesFilterParams
) -> list[dict]:
    try:
        return analytics.breakdown(session, dimension, filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
