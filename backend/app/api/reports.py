from fastapi import APIRouter

from backend.app.api.dependencies import DbSession
from backend.app.services.reports import executive_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/executive")
def get_executive_report(session: DbSession) -> dict:
    return executive_report(session)
