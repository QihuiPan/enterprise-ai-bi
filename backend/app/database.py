from __future__ import annotations

import hashlib
import json
from collections.abc import Generator

from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.config import settings


class Base(DeclarativeBase):
    pass


def build_engine(database_url: object) -> Engine:
    database_url_text = str(database_url)
    connect_args = (
        {"check_same_thread": False}
        if database_url_text.startswith("sqlite")
        else {}
    )
    engine_options = {}
    if database_url_text.startswith(("postgresql", "postgres")):
        engine_options["isolation_level"] = "REPEATABLE READ"
    built_engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        **engine_options,
    )
    if database_url_text.startswith("sqlite"):

        @event.listens_for(built_engine, "connect")
        def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
            dbapi_connection.isolation_level = None
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        @event.listens_for(built_engine, "begin")
        def begin_sqlite_transaction(connection) -> None:
            begin_mode = connection.info.pop("enterprise_bi_begin_mode", None)
            connection.exec_driver_sql(
                "BEGIN IMMEDIATE" if begin_mode == "immediate" else "BEGIN"
            )

    return built_engine


def build_session_factory(bind: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=bind, autoflush=False, expire_on_commit=False)


engine = build_engine(settings.database_url)
SessionLocal = build_session_factory(engine)


def create_tables(bind: Engine = engine) -> None:
    from backend.app import models

    Base.metadata.create_all(bind=bind)
    _backfill_legacy_dataset_profile(bind, models.DatasetProfile, models.SalesRecord)


def _backfill_legacy_dataset_profile(
    bind: Engine,
    profile_model,
    sales_model,
) -> None:
    """Preserve pre-profile databases with an explicit conservative profile."""

    warning = (
        "This conservative profile was backfilled for sales rows created before "
        "dataset profiles existed. Currency and entity/record meaning are unverified; "
        "choose the correct currency and re-import the source before relying on "
        "monetary or entity-sensitive results."
    )
    legacy_values = {
        "dataset_name": "Legacy sales snapshot",
        "currency": "USD",
        "aggregate_record_proxy": True,
        "record_count_label": "Sales records",
        "entity_count_label": "Entities",
        "average_value_label": "Average sales record value",
        "average_frequency_label": "Average sales records",
        "semantic_warning": warning,
        "entity_warning": warning,
        "warnings": [warning],
    }

    with bind.connect() as connection:
        if connection.dialect.name == "sqlite":
            # Acquire the database write reservation before the check so concurrent
            # application startups cannot both become the migration winner.
            connection.info["enterprise_bi_begin_mode"] = "immediate"
        elif connection.dialect.name == "postgresql":
            # The advisory-lock statement may wait for another startup. READ
            # COMMITTED lets the profile check see that winner's later commit.
            connection = connection.execution_options(
                isolation_level="READ COMMITTED"
            )
        with connection.begin():
            if connection.dialect.name == "postgresql":
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(711834920250827)")
                )
            with Session(bind=connection, expire_on_commit=False) as session:
                existing = session.get(profile_model, 1)
                if existing is not None:
                    if existing.source_format == "database":
                        for field, value in legacy_values.items():
                            setattr(existing, field, value)
                        session.flush()
                    return

                rows_loaded, date_min, date_max, revenue_total = session.execute(
                    select(
                        func.count(sales_model.id),
                        func.min(sales_model.order_date),
                        func.max(sales_model.order_date),
                        func.sum(sales_model.revenue),
                    )
                ).one()
                if not rows_loaded:
                    return

                digest = hashlib.sha256()
                records = session.scalars(
                    select(sales_model).order_by(sales_model.id)
                ).yield_per(5_000)
                fields = (
                    "order_id",
                    "order_date",
                    "customer_id",
                    "region",
                    "category",
                    "product",
                    "quantity",
                    "unit_price",
                    "discount",
                    "revenue",
                )
                for record in records:
                    encoded = json.dumps(
                        [getattr(record, field) for field in fields],
                        default=str,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    digest.update(encoded.encode("utf-8"))
                    digest.update(b"\n")

                session.add(
                    profile_model(
                        id=1,
                        source_format="database",
                        source_sheet=None,
                        original_filename="legacy-database-snapshot",
                        content_sha256=digest.hexdigest(),
                        rows_loaded=int(rows_loaded),
                        date_min=date_min,
                        date_max=date_max,
                        revenue_total=float(revenue_total),
                        metric_mode="components",
                        mapped_fields={
                            field: field
                            for field in (
                                "order_id",
                                "order_date",
                                "customer_id",
                                "region",
                                "category",
                                "product",
                                "quantity",
                                "unit_price",
                                "discount",
                            )
                        },
                        generated_fields=["revenue"],
                        units_available=True,
                        units_label="Units sold",
                        unit_warning=None,
                        anomaly_features=[
                            "revenue",
                            "quantity",
                            "unit_price",
                            "discount",
                        ],
                        **legacy_values,
                    )
                )
                session.flush()


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
