from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from backend.app.api.dependencies import DbSession
from backend.app.config import settings
from backend.app.schemas import IngestionSummary
from data_pipeline.ingestion import load_sales_frame, parse_csv
from data_pipeline.sample import build_demo_frame

router = APIRouter(prefix="/api/data", tags=["data"])


@router.post("/demo", response_model=IngestionSummary)
def load_demo_data(session: DbSession) -> dict:
    return load_sales_frame(build_demo_frame(), session, replace=True)


@router.post("/upload", response_model=IngestionSummary)
async def upload_csv(
    file: Annotated[UploadFile, File()],
    session: DbSession,
    replace: Annotated[bool, Query()] = True,
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload must be a .csv file.")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413, detail="CSV exceeds the configured upload limit."
        )
    try:
        return load_sales_frame(parse_csv(content), session, replace=replace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
