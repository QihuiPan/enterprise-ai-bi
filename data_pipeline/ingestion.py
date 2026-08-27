from __future__ import annotations

from io import BytesIO

import pandas as pd
from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.app.models import SalesRecord
from data_pipeline.validation import validate_and_transform


def parse_csv(content: bytes) -> pd.DataFrame:
    try:
        frame = pd.read_csv(BytesIO(content))
    except (UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise ValueError(f"Unable to parse CSV: {exc}") from exc
    return validate_and_transform(frame)


def load_sales_frame(frame: pd.DataFrame, session: Session, *, replace: bool = True) -> dict:
    if replace:
        session.execute(delete(SalesRecord))

    records = []
    for row in frame.to_dict(orient="records"):
        row["order_date"] = pd.Timestamp(row["order_date"]).date()
        records.append(SalesRecord(**row))
    session.add_all(records)
    session.commit()

    return {
        "rows_loaded": len(records),
        "date_min": frame["order_date"].min().date().isoformat(),
        "date_max": frame["order_date"].max().date().isoformat(),
        "revenue_total": round(float(frame["revenue"].sum()), 2),
        "replaced_existing": replace,
    }
