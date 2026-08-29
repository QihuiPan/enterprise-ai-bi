from __future__ import annotations

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

os.environ["APP_ENV"] = "test"
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_enterprise_ai_bi.db")
os.environ["LOKY_MAX_CPU_COUNT"] = "2"
os.environ["API_KEY"] = ""
os.environ["RATE_LIMIT_REQUESTS"] = "1000"

from backend.app.database import Base, engine  # noqa: E402
from backend.app.main import app  # noqa: E402


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)
