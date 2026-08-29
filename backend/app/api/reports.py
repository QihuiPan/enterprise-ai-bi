from typing import Annotated

from fastapi import APIRouter, Query

from backend.app.api.dependencies import DbSession, SalesFilterParams
from backend.app.currency import CurrencyCode
from backend.app.services.reports import executive_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/executive")
def get_executive_report(
    session: DbSession,
    filters: SalesFilterParams,
    currency: Annotated[CurrencyCode, Query()] = "USD",
) -> dict:
    return executive_report(session, filters, currency)
