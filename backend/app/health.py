from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app.database import engine


def database_is_ready(bind: Engine = engine) -> bool:
    try:
        with bind.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:  # A health probe must report unavailable, never crash the app.
        return False
