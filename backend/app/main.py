from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.agents.orchestrator import answer_question
from backend.app.config import settings
from backend.app.database import create_tables, get_db
from backend.app.schemas import IngestionSummary, InsightQuery, InsightResponse
from backend.app.services import analytics, machine_learning, reports
from data_pipeline.ingestion import load_sales_frame, parse_csv
from data_pipeline.sample import build_demo_frame
from data_pipeline.validation import DataValidationError


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Validated business analytics, evaluated ML, and grounded specialist agents.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DbSession = Annotated[Session, Depends(get_db)]


@app.exception_handler(DataValidationError)
async def data_validation_error_handler(_, exc: DataValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.issues})


@app.exception_handler(analytics.NoDataError)
async def no_data_error_handler(_, exc: analytics.NoDataError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.app_env}


@app.post("/api/data/demo", response_model=IngestionSummary)
def load_demo_data(session: DbSession) -> dict:
    return load_sales_frame(build_demo_frame(), session, replace=True)


@app.post("/api/data/upload", response_model=IngestionSummary)
async def upload_csv(
    file: Annotated[UploadFile, File()],
    session: DbSession,
    replace: Annotated[bool, Query()] = True,
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload must be a .csv file.")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="CSV exceeds the configured upload limit.")
    try:
        frame = parse_csv(content)
        return load_sales_frame(frame, session, replace=replace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/analytics/kpis")
def get_kpis(session: DbSession) -> dict:
    return analytics.kpis(session)


@app.get("/api/analytics/trends")
def get_trends(
    session: DbSession,
    grain: Annotated[str, Query(pattern="^(day|month)$")] = "month",
) -> list[dict]:
    return analytics.trend(session, grain=grain)


@app.get("/api/analytics/breakdown/{dimension}")
def get_breakdown(dimension: str, session: DbSession) -> list[dict]:
    try:
        return analytics.breakdown(session, dimension)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ml/forecast")
def get_forecast(
    session: DbSession,
    horizon: Annotated[int, Query(ge=1, le=12)] = 3,
) -> dict:
    try:
        return machine_learning.revenue_forecast(session, horizon=horizon)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ml/segments")
def get_segments(
    session: DbSession,
    clusters: Annotated[int, Query(ge=2, le=8)] = 4,
) -> dict:
    try:
        return machine_learning.customer_segments(session, clusters=clusters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ml/anomalies")
def get_anomalies(
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict:
    try:
        return machine_learning.sales_anomalies(session, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/insights/query", response_model=InsightResponse)
def query_insights(payload: InsightQuery, session: DbSession) -> dict:
    return answer_question(payload.question, session)


@app.get("/api/reports/executive")
def get_executive_report(session: DbSession) -> dict:
    return reports.executive_report(session)
