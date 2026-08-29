from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile

from backend.app.api.dependencies import DbSession
from backend.app.schemas import IngestionSummary
from data_pipeline.ingestion import load_sales_frame, parse_csv
from data_pipeline.sample import build_demo_frame
from data_pipeline.validation import DataValidationError

router = APIRouter(prefix="/api/data", tags=["data"])


@router.post("/demo", response_model=IngestionSummary)
def load_demo_data(session: DbSession) -> dict:
    return load_sales_frame(build_demo_frame(), session, replace=True)


@router.post("/upload", response_model=IngestionSummary)
def upload_csv(
    file: Annotated[UploadFile, File()],
    session: DbSession,
    request: Request,
    replace: Annotated[bool, Query()] = True,
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload must be a .csv file.")
    max_upload_bytes = request.app.state.settings.max_upload_bytes
    content = file.file.read(max_upload_bytes + 1)
    if len(content) > max_upload_bytes:
        raise HTTPException(
            status_code=413, detail="CSV exceeds the configured upload limit."
        )
    try:
        return load_sales_frame(parse_csv(content), session, replace=replace)
    except DataValidationError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
