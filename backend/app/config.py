from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    database_url: str
    cors_origins_raw: str
    max_upload_bytes: int

    @classmethod
    def from_env(cls) -> Settings:
        max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
        if max_upload_bytes <= 0:
            raise ValueError("MAX_UPLOAD_BYTES must be a positive integer.")
        return cls(
            app_name=os.getenv(
                "APP_NAME", "Enterprise AI Business Intelligence Agent"
            ),
            app_env=os.getenv("APP_ENV", "development"),
            database_url=os.getenv(
                "DATABASE_URL", "sqlite:///./enterprise_ai_bi.db"
            ),
            cors_origins_raw=os.getenv(
                "CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ),
            max_upload_bytes=max_upload_bytes,
        )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]


settings = Settings.from_env()
