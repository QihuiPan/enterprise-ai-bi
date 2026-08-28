from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import pandas as pd
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from backend.app.models import SalesRecord
from data_pipeline.validation import SalesFrameValidator, default_sales_validator


@dataclass
class SalesIngestionService:
    session: Session
    validator: SalesFrameValidator = default_sales_validator
    batch_size: int = 5_000

    def parse_csv(self, content: bytes) -> pd.DataFrame:
        try:
            frame = pd.read_csv(BytesIO(content))
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            raise ValueError(f"Unable to parse CSV: {exc}") from exc
        return self.validator.validate(frame)

    def load(self, frame: pd.DataFrame, *, replace: bool = True) -> dict:
        if self.batch_size <= 0:
            raise ValueError("Ingestion batch size must be a positive integer.")
        try:
            if replace:
                self.session.execute(delete(SalesRecord))
            for start in range(0, len(frame), self.batch_size):
                batch = frame.iloc[start : start + self.batch_size].to_dict(
                    orient="records"
                )
                for row in batch:
                    row["order_date"] = pd.Timestamp(row["order_date"]).date()
                self.session.execute(insert(SalesRecord), batch)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return {
            "rows_loaded": len(frame),
            "date_min": frame["order_date"].min().date().isoformat(),
            "date_max": frame["order_date"].max().date().isoformat(),
            "revenue_total": round(float(frame["revenue"].sum()), 2),
            "replaced_existing": replace,
        }

def parse_csv(content: bytes) -> pd.DataFrame:
    try:
        frame = pd.read_csv(BytesIO(content))
    except (UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise ValueError(f"Unable to parse CSV: {exc}") from exc
    return default_sales_validator.validate(frame)


def load_sales_frame(
    frame: pd.DataFrame, session: Session, *, replace: bool = True
) -> dict:
    return SalesIngestionService(session).load(frame, replace=replace)
