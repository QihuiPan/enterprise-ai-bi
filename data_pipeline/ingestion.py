from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from io import StringIO
from typing import Any

import pandas as pd
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from backend.app.models import DatasetProfile, SalesRecord
from data_pipeline.delimited import validate_delimited_shape
from data_pipeline.validation import (
    REQUIRED_COLUMNS,
    DataValidationError,
    SalesFrameValidator,
    default_sales_validator,
)

MAX_LEGACY_ROWS = 500_000
MAX_LEGACY_COLUMNS = 100
MAX_LEGACY_CELLS = 5_000_000
MAX_LEGACY_CELL_CHARACTERS = 10_000
MAX_LEGACY_HEADER_CHARACTERS = 255


def _read_sales_csv(
    content: bytes, validator: SalesFrameValidator
) -> pd.DataFrame:
    try:
        decoded = content.decode("utf-8-sig")
        if "\x00" in decoded:
            raise DataValidationError(
                ["The uploaded CSV contains a NUL control character."]
            )
        validate_delimited_shape(
            decoded,
            ",",
            max_columns=MAX_LEGACY_COLUMNS,
            max_header_characters=MAX_LEGACY_HEADER_CHARACTERS,
            max_cell_characters=MAX_LEGACY_CELL_CHARACTERS,
        )
        reader = csv.reader(StringIO(decoded, newline=""), strict=True)
        header = next(reader)
        if len(header) > MAX_LEGACY_COLUMNS:
            raise DataValidationError(
                [f"The table exceeds the {MAX_LEGACY_COLUMNS:,}-column limit."]
            )
        oversized_headers = [
            column for column in header if len(column) > MAX_LEGACY_HEADER_CHARACTERS
        ]
        if oversized_headers:
            raise DataValidationError(
                [
                    "The table header has "
                    f"{len(oversized_headers)} column names longer than "
                    f"{MAX_LEGACY_HEADER_CHARACTERS} characters."
                ]
            )
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
        missing_columns = [
            column for column in REQUIRED_COLUMNS if column not in canonical_header
        ]
        unexpected_columns = sorted(set(canonical_header).difference(REQUIRED_COLUMNS))
        if missing_columns or unexpected_columns:
            issues = []
            if missing_columns:
                issues.append(
                    f"Missing required columns: {', '.join(missing_columns)}."
                )
            if unexpected_columns:
                issues.append(
                    "The compatibility CSV accepts exactly the nine canonical "
                    "columns; unexpected columns: "
                    f"{', '.join(unexpected_columns)}. Use the guided import for "
                    "other schemas."
                )
            raise DataValidationError(issues)
        rows: list[list[str]] = []
        for data_row_number, row in enumerate(reader, start=1):
            if not row or not any(value.strip() for value in row):
                continue
            if len(row) != len(header):
                raise DataValidationError(
                    [
                        f"Data row {data_row_number} has {len(row)} fields; "
                        f"the header defines {len(header)}."
                    ]
                )
            oversized_cells = sum(
                len(value) > MAX_LEGACY_CELL_CHARACTERS for value in row
            )
            if oversized_cells:
                raise DataValidationError(
                    [
                        f"Data row {data_row_number} has {oversized_cells} values "
                        f"longer than {MAX_LEGACY_CELL_CHARACTERS:,} characters."
                    ]
                )
            rows.append(row)
            if len(rows) > MAX_LEGACY_ROWS:
                raise DataValidationError(
                    [f"The table exceeds the {MAX_LEGACY_ROWS:,}-row limit."]
                )
            if len(rows) * len(header) > MAX_LEGACY_CELLS:
                raise DataValidationError(
                    [
                        "The table exceeds the "
                        f"{MAX_LEGACY_CELLS:,}-cell processing limit."
                    ]
                )
        return pd.DataFrame(rows, columns=header, dtype="string")
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

    def load(
        self,
        frame: pd.DataFrame,
        *,
        replace: bool = True,
        profile: dict | None = None,
        profile_serializer: Callable[[DatasetProfile], dict[str, Any]] | None = None,
    ) -> dict:
        if self.batch_size <= 0:
            raise ValueError("Ingestion batch size must be a positive integer.")
        if not replace:
            raise ValueError(
                "Append ingestion is disabled. Upload a complete dataset with "
                "replace=true so validation applies to the full analytical snapshot."
            )
        serialized_profile = None
        try:
            self.session.execute(delete(SalesRecord))
            self.session.execute(delete(DatasetProfile))
            for start in range(0, len(frame), self.batch_size):
                batch = frame.iloc[start : start + self.batch_size].to_dict(
                    orient="records"
                )
                for row in batch:
                    row["order_date"] = pd.Timestamp(row["order_date"]).date()
                self.session.execute(insert(SalesRecord), batch)
            if profile is not None:
                date_min = pd.Timestamp(frame["order_date"].min()).date()
                date_max = pd.Timestamp(frame["order_date"].max()).date()
                revenue_total = float(frame["revenue"].sum())
                profile_record = DatasetProfile(
                    id=1,
                    **profile,
                    rows_loaded=len(frame),
                    date_min=date_min,
                    date_max=date_max,
                    revenue_total=revenue_total,
                )
                self.session.add(profile_record)
                self.session.flush()
                if profile_serializer is not None:
                    # Freeze the response while this transaction still owns the
                    # profile it wrote. A later importer may replace row id=1.
                    serialized_profile = profile_serializer(profile_record)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        summary = {
            "rows_loaded": len(frame),
            "date_min": frame["order_date"].min().date().isoformat(),
            "date_max": frame["order_date"].max().date().isoformat(),
            "revenue_total": round(float(frame["revenue"].sum()), 2),
            "replaced_existing": True,
        }
        if serialized_profile is not None:
            summary["_dataset_profile"] = serialized_profile
        return summary

def parse_csv(content: bytes) -> pd.DataFrame:
    frame = _read_sales_csv(content, default_sales_validator)
    return default_sales_validator.validate(frame)


def load_sales_frame(
    frame: pd.DataFrame,
    session: Session,
    *,
    replace: bool = True,
    profile: dict | None = None,
    profile_serializer: Callable[[DatasetProfile], dict[str, Any]] | None = None,
) -> dict:
    return SalesIngestionService(session).load(
        frame,
        replace=replace,
        profile=profile,
        profile_serializer=profile_serializer,
    )
