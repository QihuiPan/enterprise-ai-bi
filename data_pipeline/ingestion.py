from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from io import StringIO

import pandas as pd
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from backend.app.models import SalesRecord
from data_pipeline.validation import (
    DataValidationError,
    SalesFrameValidator,
    default_sales_validator,
)


def _read_sales_csv(
    content: bytes, validator: SalesFrameValidator
) -> pd.DataFrame:
    try:
        decoded = content.decode("utf-8-sig")
        if "\x00" in decoded:
            raise DataValidationError(
                ["The uploaded CSV contains a NUL control character."]
            )
        header = next(csv.reader(StringIO(decoded, newline="")))
        canonical_header = [validator.canonical_name(column) for column in header]
        duplicate_columns = sorted(
            column
            for column, count in Counter(canonical_header).items()
            if count > 1
        )
        if duplicate_columns:
            raise DataValidationError(
                [
                    "Column names collide after normalization: "
                    f"{', '.join(duplicate_columns)}."
                ]
            )
        return pd.read_csv(
            StringIO(decoded), dtype="string", keep_default_na=False
        )
    except StopIteration as exc:
        raise ValueError("Unable to parse CSV: the file is empty.") from exc
    except (UnicodeDecodeError, csv.Error, pd.errors.ParserError) as exc:
        raise ValueError(f"Unable to parse CSV: {exc}") from exc


@dataclass
class SalesIngestionService:
    session: Session
    validator: SalesFrameValidator = default_sales_validator
    batch_size: int = 5_000

    def parse_csv(self, content: bytes) -> pd.DataFrame:
        frame = _read_sales_csv(content, self.validator)
        return self.validator.validate(frame)

    def load(self, frame: pd.DataFrame, *, replace: bool = True) -> dict:
        if self.batch_size <= 0:
            raise ValueError("Ingestion batch size must be a positive integer.")
        if not replace:
            raise ValueError(
                "Append ingestion is disabled. Upload a complete dataset with "
                "replace=true so validation applies to the full analytical snapshot."
            )
        try:
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
            "replaced_existing": True,
        }

def parse_csv(content: bytes) -> pd.DataFrame:
    frame = _read_sales_csv(content, default_sales_validator)
    return default_sales_validator.validate(frame)


def load_sales_frame(
    frame: pd.DataFrame, session: Session, *, replace: bool = True
) -> dict:
    return SalesIngestionService(session).load(frame, replace=replace)
