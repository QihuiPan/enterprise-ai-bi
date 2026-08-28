from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from backend.app.api.dependencies import DbSession
from backend.app.services import analytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/kpis")
def get_kpis(session: DbSession) -> dict:
    return analytics.kpis(session)


@router.get("/trends")
def get_trends(
    session: DbSession,
    grain: Annotated[str, Query(pattern="^(day|month)$")] = "month",
) -> list[dict]:
    return analytics.trend(session, grain=grain)


@router.get("/breakdown/{dimension}")
def get_breakdown(dimension: str, session: DbSession) -> list[dict]:
    try:
        return analytics.breakdown(session, dimension)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
