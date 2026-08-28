from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.router import api_router
from backend.app.config import Settings, settings
from backend.app.database import create_tables
from backend.app.services.analytics import NoDataError
from data_pipeline.validation import DataValidationError


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    yield


def create_app(app_settings: Settings = settings) -> FastAPI:
    application = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        description=(
            "Validated business analytics, evaluated ML, and grounded "
            "specialist agents."
        ),
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(DataValidationError)
    async def data_validation_error_handler(_, exc: DataValidationError):
        return JSONResponse(status_code=422, content={"detail": exc.issues})

    @application.exception_handler(NoDataError)
    async def no_data_error_handler(_, exc: NoDataError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @application.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "environment": app_settings.app_env}

    application.include_router(api_router)
    return application


app = create_app()
