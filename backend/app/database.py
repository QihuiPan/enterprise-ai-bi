from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.config import settings


class Base(DeclarativeBase):
    pass


def build_engine(database_url: object) -> Engine:
    connect_args = (
        {"check_same_thread": False}
        if str(database_url).startswith("sqlite")
        else {}
    )
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


def build_session_factory(bind: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=bind, autoflush=False, expire_on_commit=False)


engine = build_engine(settings.database_url)
SessionLocal = build_session_factory(engine)


def create_tables(bind: Engine = engine) -> None:
    from backend.app import models  # noqa: F401

    Base.metadata.create_all(bind=bind)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def session_dependency(
    session_factory: sessionmaker[Session],
) -> Generator[Session, None, None]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
