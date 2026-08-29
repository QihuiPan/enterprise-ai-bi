from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy.engine import URL


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    database_url: str | URL
    cors_origins_raw: str
    max_upload_bytes: int
    api_key: str | None = None
    api_key_header: str = "X-API-Key"
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    rate_limit_max_clients: int = 10_000

    @classmethod
    def from_env(cls) -> Settings:
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
        if max_upload_bytes <= 0:
            raise ValueError("MAX_UPLOAD_BYTES must be a positive integer.")
        rate_limit_requests = int(os.getenv("RATE_LIMIT_REQUESTS", "120"))
        rate_limit_window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
        rate_limit_max_clients = int(os.getenv("RATE_LIMIT_MAX_CLIENTS", "10000"))
        if rate_limit_requests < 0:
            raise ValueError("RATE_LIMIT_REQUESTS must be zero or a positive integer.")
        if rate_limit_window_seconds <= 0:
            raise ValueError("RATE_LIMIT_WINDOW_SECONDS must be a positive integer.")
        if rate_limit_max_clients <= 0:
            raise ValueError("RATE_LIMIT_MAX_CLIENTS must be a positive integer.")
        api_key = os.getenv("API_KEY", "").strip() or None
        api_key_header = os.getenv("API_KEY_HEADER", "X-API-Key").strip()
        if not api_key_header:
            raise ValueError("API_KEY_HEADER must not be empty.")
        cors_origins_raw = os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
        cors_origins = [
            origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()
        ]
        if app_env == "production":
            if api_key is None or len(api_key) < 32:
                raise ValueError("Production API_KEY must contain at least 32 characters.")
            if not cors_origins or "*" in cors_origins:
                raise ValueError(
                    "Production CORS_ORIGINS must be an explicit origin allowlist."
                )
            for origin in cors_origins:
                parsed = urlsplit(origin)
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.netloc
                    or parsed.path not in {"", "/"}
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError(
                        "Production CORS_ORIGINS entries must be exact HTTP(S) origins."
                    )
        database_url: str | URL
        configured_database_url = os.getenv("DATABASE_URL", "").strip()
        database_host = os.getenv("DATABASE_HOST", "").strip()
        if configured_database_url:
            database_url = configured_database_url
        elif database_host:
            database_port = int(os.getenv("DATABASE_PORT", "5432"))
            database_name = os.getenv("DATABASE_NAME", "").strip()
            database_user = os.getenv("DATABASE_USER", "").strip()
            database_password = os.getenv("DATABASE_PASSWORD", "")
            if not database_name or not database_user or not database_password:
                raise ValueError(
                    "DATABASE_NAME, DATABASE_USER, and DATABASE_PASSWORD are required "
                    "when DATABASE_HOST is set."
                )
            if not 1 <= database_port <= 65535:
                raise ValueError("DATABASE_PORT must be between 1 and 65535.")
            database_url = URL.create(
                "postgresql+psycopg",
                username=database_user,
                password=database_password,
                host=database_host,
                port=database_port,
                database=database_name,
            )
        else:
            database_url = "sqlite:///./enterprise_ai_bi.db"
        return cls(
            app_name=os.getenv(
                "APP_NAME", "Enterprise AI Business Intelligence Agent"
            ),
            app_env=app_env,
            database_url=database_url,
            cors_origins_raw=cors_origins_raw,
            max_upload_bytes=max_upload_bytes,
            api_key=api_key,
            api_key_header=api_key_header,
            rate_limit_requests=rate_limit_requests,
            rate_limit_window_seconds=rate_limit_window_seconds,
            rate_limit_max_clients=rate_limit_max_clients,
        )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]


settings = Settings.from_env()
