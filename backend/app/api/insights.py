from fastapi import APIRouter

from backend.app.agents.orchestrator import answer_question
from backend.app.api.dependencies import DbSession
from backend.app.schemas import InsightQuery, InsightResponse

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.post("/query", response_model=InsightResponse)
def query_insights(payload: InsightQuery, session: DbSession) -> dict:
    return answer_question(payload.question, session)
