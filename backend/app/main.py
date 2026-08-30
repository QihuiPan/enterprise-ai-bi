from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.engine import URL

from backend.app import health as health_checks
from backend.app.api.router import api_router
from backend.app.config import Settings, settings
from backend.app.database import (
    SessionLocal,
    build_engine,
    build_session_factory,
    create_tables,
    engine,
    get_db,
    session_dependency,
)
from backend.app.observability import (
    MetricsMiddleware,
    PrometheusMetrics,
    RequestContextMiddleware,
)
from backend.app.security import (
    APIKeyMiddleware,
    NoStoreAPIMiddleware,
    RateLimitMiddleware,
    RequestBodyLimitMiddleware,
)
from backend.app.services.analytics import NoDataError
from backend.app.services.filtering import NoMatchingSalesError
from data_pipeline.validation import DataValidationError


@asynccontextmanager
async def lifespan(application: FastAPI):
    create_tables(application.state.engine)
    yield


def _same_database_url(left: str | URL, right: str | URL) -> bool:
    return type(left) is type(right) and left == right


def create_app(app_settings: Settings = settings) -> FastAPI:
    metrics = PrometheusMetrics()
    if _same_database_url(app_settings.database_url, settings.database_url):
        app_engine = engine
        session_factory = SessionLocal
    else:
        app_engine = build_engine(app_settings.database_url)
        session_factory = build_session_factory(app_engine)
    application = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        description=(
            "Validated business analytics, evaluated ML, and grounded "
            "specialist agents."
        ),
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.engine = app_engine
    application.state.metrics = metrics

    def get_app_db():
        yield from session_dependency(session_factory)

    application.dependency_overrides[get_db] = get_app_db
    application.add_middleware(
        RequestBodyLimitMiddleware,
        max_upload_bytes=app_settings.max_upload_bytes,
    )
    application.add_middleware(
        RateLimitMiddleware,
        requests=app_settings.rate_limit_requests,
        window_seconds=app_settings.rate_limit_window_seconds,
        max_clients=app_settings.rate_limit_max_clients,
    )
    application.add_middleware(
        APIKeyMiddleware,
        api_key=app_settings.api_key,
        header_name=app_settings.api_key_header,
    )
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(MetricsMiddleware, registry=metrics)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Starlette makes the last registered user middleware the outermost layer.
    # Keep this outside auth and rate limiting so their early responses are covered.
    application.add_middleware(NoStoreAPIMiddleware)

    @application.exception_handler(DataValidationError)
    async def data_validation_error_handler(_, exc: DataValidationError):
        return JSONResponse(status_code=422, content={"detail": exc.issues})

    @application.exception_handler(NoDataError)
    async def no_data_error_handler(_, exc: NoDataError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @application.exception_handler(NoMatchingSalesError)
    async def no_matching_sales_error_handler(_, exc: NoMatchingSalesError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.get("/health/live", tags=["system"])
    def liveness() -> dict:
        return {
            "status": "alive",
            "environment": app_settings.app_env,
            "checks": {"application": "ok"},
        }

    def readiness_response(*, success_status: str = "ready") -> JSONResponse:
        database_ready = health_checks.database_is_ready(application.state.engine)
        status_code = 200 if database_ready else 503
        return JSONResponse(
            status_code=status_code,
            content={
                "status": success_status if database_ready else "not_ready",
                "environment": app_settings.app_env,
                "checks": {"database": "ok" if database_ready else "unavailable"},
            },
        )

    @application.get("/health/ready", tags=["system"])
    def readiness() -> JSONResponse:
        return readiness_response()

    @application.get("/health", tags=["system"])
    def health() -> JSONResponse:
        return readiness_response(success_status="ok")

    @application.get("/metrics", tags=["system"], include_in_schema=False)
    def prometheus_metrics() -> PlainTextResponse:
        return PlainTextResponse(
            metrics.render(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    application.include_router(api_router)
    return application


app = create_app()
