from __future__ import annotations

import hashlib
import hmac
import re
from datetime import UTC, date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from backend.app.api.dependencies import DbSession
from backend.app.currency import CurrencyCode
from backend.app.dataset_version import dataset_version_from_profile
from backend.app.models import DatasetProfile
from backend.app.schemas import (
    DatasetProfileResponse,
    FlexibleImportResponse,
    IngestionSummary,
    TabularPreviewResponse,
)
from data_pipeline.ingestion import load_sales_frame, parse_csv
from data_pipeline.sample import build_demo_frame
from data_pipeline.tabular import (
    build_preview,
    map_tabular_sales,
    parse_mapping,
    read_tabular_file,
)
from data_pipeline.validation import REQUIRED_COLUMNS, DataValidationError

router = APIRouter(prefix="/api/data", tags=["data"])
MAX_MAPPING_CHARACTERS = 10_000
SourceProfile = Literal["order_level", "uci", "iowa", "m5"]
KNOWN_SOURCE_PROFILES = {
    "uci": (
        "UCI Online Retail II",
        "Customer-country-day records",
        "Customers",
        "Average aggregate record value",
        "Average aggregate records",
        True,
        "The generated IDs represent customer-country-day aggregates, not source "
        "orders; this value is not source average order value.",
        "Customer IDs retain source customer identifiers.",
        "GBP",
    ),
    "iowa": (
        "Iowa Liquor Sales 2024",
        "Store-county-category-month records",
        "Stores",
        "Average aggregate record value",
        "Average aggregate records",
        True,
        "The generated IDs represent store-county-category-month aggregates, not "
        "source transactions; this value is not source average order value.",
        "Entity IDs represent source stores.",
        "USD",
    ),
    "m5": (
        "Walmart M5",
        "Store-category-day records",
        "Stores",
        "Average aggregate record value",
        "Average aggregate records",
        True,
        "The generated IDs represent store-category-day aggregates and M5 contains "
        "no order or shopper facts; this value is not average order value.",
        "Entity IDs represent stores because M5 contains no shoppers.",
        "USD",
    ),
}
KNOWN_SOURCE_PREFIXES = {"uci": "UCI-", "iowa": "IA2024-", "m5": "M5-"}
KNOWN_SOURCE_REQUIRED_MAPPINGS = set(REQUIRED_COLUMNS)
KNOWN_SOURCE_EXPECTED_SUMMARIES = {
    "uci": (33_112, date(2009, 12, 1), date(2011, 12, 9)),
    "iowa": (438_528, date(2024, 1, 1), date(2024, 12, 1)),
    "m5": (58_105, date(2011, 1, 29), date(2016, 5, 22)),
}


def _known_record_contract_matches(source_profile: str, record) -> bool:
    order_id = str(record.order_id)
    order_date = record.order_date
    if hasattr(order_date, "date"):
        order_date = order_date.date()
    customer_id = str(record.customer_id)
    category = str(record.category)
    product = str(record.product)
    region = str(record.region)
    if float(record.discount) != 0:
        return False

    if source_profile == "iowa":
        return bool(
            re.fullmatch(r"IA2024-\d{8}", order_id)
            and order_date.year == 2024
            and order_date.day == 1
            and re.fullmatch(r"IA-STORE-.+", customer_id)
            and region != "All regions"
            and category != "Uncategorized"
            and product == "Monthly spirits basket"
        )
    if source_profile == "uci":
        return bool(
            re.fullmatch(r"UCI-\d{8}", order_id)
            and date(2009, 12, 1) <= order_date <= date(2011, 12, 9)
            and re.fullmatch(r"UCI-.+", customer_id)
            and region != "All regions"
            and category == "Online Retail"
            and product == "Daily online retail basket"
        )
    if source_profile != "m5":
        return False

    match = re.fullmatch(
        r"M5-d_(?P<day>\d{1,4})-(?P<store>(?:CA|TX|WI)_\d+)-"
        r"(?P<category>FOODS|HOBBIES|HOUSEHOLD)",
        order_id,
    )
    if match is None:
        return False
    expected_date = date(2011, 1, 29) + timedelta(
        days=int(match.group("day")) - 1
    )
    return bool(
        order_date == expected_date
        and order_date <= date(2016, 5, 22)
        and customer_id == match.group("store")
        and region == customer_id.split("_", 1)[0]
        and category == match.group("category")
        and product == f"{customer_id} {category}"
    )


def _resolve_profile_currency(
    source_profile: SourceProfile,
    requested_currency: CurrencyCode | None,
) -> CurrencyCode:
    known_source = KNOWN_SOURCE_PROFILES.get(source_profile)
    if known_source is None:
        return requested_currency or "USD"
    expected_currency: CurrencyCode = known_source[-1]
    if requested_currency is not None and requested_currency != expected_currency:
        raise DataValidationError(
            [
                f"The prepared {source_profile} profile uses {expected_currency}; "
                f"the selected source currency is {requested_currency}."
            ]
        )
    return expected_currency


def _validate_known_source_selection(
    frame,
    source_profile: SourceProfile,
    *,
    mapping: dict[str, str],
) -> None:
    if source_profile not in KNOWN_SOURCE_PREFIXES:
        return
    missing = sorted(KNOWN_SOURCE_REQUIRED_MAPPINGS.difference(mapping))
    extra = sorted(set(mapping).difference(KNOWN_SOURCE_REQUIRED_MAPPINGS))
    renamed = sorted(
        field
        for field in KNOWN_SOURCE_REQUIRED_MAPPINGS.intersection(mapping)
        if mapping[field] != field
    )
    if missing or extra or renamed:
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if extra:
            details.append(f"unexpected {', '.join(extra)}")
        if renamed:
            details.append(f"non-canonical sources for {', '.join(renamed)}")
        raise DataValidationError(
            [
                f"The prepared {source_profile} profile requires the exact canonical "
                f"nine-column artifact mapping ({'; '.join(details)})."
            ]
        )
    order_ids = frame["order_id"].astype("string")
    entities = frame["customer_id"].astype("string")
    missing_entities = entities.eq("UNSPECIFIED-ENTITY") | entities.str.strip().eq("")
    if missing_entities.any():
        raise DataValidationError(
            [
                f"The prepared {source_profile} profile requires a source entity ID "
                f"for every row; {int(missing_entities.sum()):,} rows are missing one."
            ]
        )

    invalid_contract = sum(
        not _known_record_contract_matches(source_profile, record)
        for record in frame.itertuples(index=False)
    )
    if invalid_contract:
        raise DataValidationError(
            [
                f"The prepared {source_profile} profile has {invalid_contract:,} rows "
                "outside its documented ID, date grain, entity, category, product, "
                "region, or discount contract. Choose the automatic profile for "
                "modified or unrelated files."
            ]
        )
    expected_rows, expected_min, expected_max = KNOWN_SOURCE_EXPECTED_SUMMARIES[
        source_profile
    ]
    observed_min = frame["order_date"].min().date()
    observed_max = frame["order_date"].max().date()
    if (len(frame), observed_min, observed_max) != (
        expected_rows,
        expected_min,
        expected_max,
    ):
        raise DataValidationError(
            [
                f"The prepared {source_profile} profile requires the complete "
                f"prepared-output contract ({expected_rows:,} rows, {expected_min} through "
                f"{expected_max}); this file has {len(frame):,} rows, {observed_min} "
                f"through {observed_max}. Choose the automatic profile for a subset."
            ]
        )
    if source_profile in {"uci", "iowa"}:
        number = order_ids.str.rsplit("-", n=1).str[-1].astype(int)
        if (
            int(number.min()) != 1
            or int(number.max()) != expected_rows
            or int(number.nunique()) != expected_rows
        ):
            raise DataValidationError(
                [
                    f"The prepared {source_profile} profile requires contiguous "
                    f"generated record IDs from 00000001 through "
                    f"{expected_rows:08d}."
                ]
            )


def _read_bounded_upload(file: UploadFile, request: Request) -> bytes:
    max_upload_bytes = request.app.state.settings.max_upload_bytes
    content = file.file.read(max_upload_bytes + 1)
    if len(content) > max_upload_bytes:
        raise HTTPException(
            status_code=413, detail="File exceeds the configured upload limit."
        )
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    return content


def _safe_filename(value: str) -> str:
    filename = re.split(r"[/\\\\]", value)[-1].strip()
    if not filename or len(filename) > 255 or "\x00" in filename:
        raise HTTPException(
            status_code=400,
            detail="Uploaded filename is invalid or exceeds 255 characters.",
        )
    return filename


def _profile_dict(profile: DatasetProfile) -> dict:
    imported_at = profile.imported_at
    if imported_at.tzinfo is None:
        imported_at = imported_at.replace(tzinfo=UTC)
    return {
        "dataset_name": profile.dataset_name,
        "source_format": profile.source_format,
        "source_sheet": profile.source_sheet,
        "original_filename": profile.original_filename,
        "content_sha256": profile.content_sha256,
        "rows_loaded": profile.rows_loaded,
        "date_min": profile.date_min.isoformat(),
        "date_max": profile.date_max.isoformat(),
        "revenue_total": round(float(profile.revenue_total), 2),
        "currency": profile.currency,
        "metric_mode": profile.metric_mode,
        "mapped_fields": dict(profile.mapped_fields),
        "generated_fields": list(profile.generated_fields),
        "warnings": list(profile.warnings),
        "aggregate_record_proxy": profile.aggregate_record_proxy,
        "record_count_label": profile.record_count_label,
        "entity_count_label": profile.entity_count_label,
        "average_value_label": profile.average_value_label,
        "average_frequency_label": profile.average_frequency_label,
        "semantic_warning": profile.semantic_warning,
        "entity_warning": profile.entity_warning,
        "units_available": profile.units_available,
        "units_label": profile.units_label,
        "unit_warning": profile.unit_warning,
        "anomaly_features": list(profile.anomaly_features),
        "imported_at": imported_at,
        "dataset_version": dataset_version_from_profile(profile),
        "currency_verified": profile.source_format != "database",
    }


def _canonical_profile(
    *,
    dataset_name: str,
    filename: str,
    content_sha256: str,
    source_format: str,
    source_currency: CurrencyCode | None = None,
    source_profile: SourceProfile = "order_level",
) -> dict:
    known_source = KNOWN_SOURCE_PROFILES.get(source_profile)
    if known_source is None:
        resolved_name = dataset_name
        semantics = (
            "Orders",
            "Customers",
            "Average order value",
            "Average orders",
            False,
            None,
            None,
        )
    else:
        resolved_name = known_source[0]
        semantics = known_source[1:-1]
    (
        record_label,
        entity_label,
        average_label,
        frequency_label,
        aggregate_proxy,
        warning,
        entity_warning,
    ) = semantics
    return {
        "dataset_name": resolved_name,
        "source_format": source_format,
        "source_sheet": None,
        "original_filename": filename,
        "content_sha256": content_sha256,
        "currency": _resolve_profile_currency(source_profile, source_currency),
        "metric_mode": "components",
        "mapped_fields": {
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
        "generated_fields": ["revenue"],
        "warnings": [],
        "aggregate_record_proxy": aggregate_proxy,
        "record_count_label": record_label,
        "entity_count_label": entity_label,
        "average_value_label": average_label,
        "average_frequency_label": frequency_label,
        "semantic_warning": warning,
        "entity_warning": entity_warning,
        "units_available": True,
        "units_label": "Units sold",
        "unit_warning": None,
        "anomaly_features": ["revenue", "quantity", "unit_price", "discount"],
    }


@router.post("/demo", response_model=IngestionSummary)
def load_demo_data(session: DbSession) -> dict:
    frame = build_demo_frame()
    profile = _canonical_profile(
        dataset_name="Deterministic demo sales",
        filename="generated-demo.csv",
        content_sha256=hashlib.sha256(b"enterprise-ai-bi-demo-v1").hexdigest(),
        source_format="generated",
    )
    return load_sales_frame(frame, session, replace=True, profile=profile)


@router.post("/upload", response_model=IngestionSummary)
def upload_csv(
    file: Annotated[UploadFile, File()],
    session: DbSession,
    request: Request,
    replace: Annotated[bool, Query()] = True,
    source_currency: Annotated[CurrencyCode | None, Form()] = None,
    source_profile: Annotated[SourceProfile, Form()] = "order_level",
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Upload must be a .csv file.")
    filename = _safe_filename(file.filename)
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload must be a .csv file.")
    content = _read_bounded_upload(file, request)
    try:
        frame = parse_csv(content)
        _validate_known_source_selection(
            frame,
            source_profile,
            mapping={field: field for field in REQUIRED_COLUMNS},
        )
        profile = _canonical_profile(
            dataset_name="Uploaded order-level sales",
            filename=filename,
            content_sha256=hashlib.sha256(content).hexdigest(),
            source_format="csv",
            source_currency=source_currency,
            source_profile=source_profile,
        )
        return load_sales_frame(
            frame, session, replace=replace, profile=profile
        )
    except DataValidationError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/preview", response_model=TabularPreviewResponse)
def preview_tabular_data(
    file: Annotated[UploadFile, File()],
    request: Request,
    sheet_name: Annotated[str | None, Form()] = None,
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file needs a filename.")
    content = _read_bounded_upload(file, request)
    try:
        dataset = read_tabular_file(
            content, file.filename, sheet_name=sheet_name or None
        )
        return build_preview(dataset)
    except DataValidationError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/import", response_model=FlexibleImportResponse)
def import_tabular_data(
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str, Form()],
    dataset_name: Annotated[str, Form()],
    expected_sha256: Annotated[str, Form()],
    session: DbSession,
    request: Request,
    sheet_name: Annotated[str | None, Form()] = None,
    source_currency: Annotated[CurrencyCode | None, Form()] = None,
    source_profile: Annotated[SourceProfile, Form()] = "order_level",
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file needs a filename.")
    _safe_filename(file.filename)
    normalized_name = dataset_name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="dataset_name must not be blank.")
    if len(normalized_name) > 120:
        raise HTTPException(
            status_code=400, detail="dataset_name cannot exceed 120 characters."
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized_name):
        raise HTTPException(
            status_code=400,
            detail="dataset_name cannot contain control characters.",
        )
    if len(mapping) > MAX_MAPPING_CHARACTERS:
        raise HTTPException(
            status_code=400,
            detail=f"mapping cannot exceed {MAX_MAPPING_CHARACTERS:,} characters.",
        )
    normalized_sha256 = expected_sha256.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized_sha256):
        raise HTTPException(
            status_code=400,
            detail="expected_sha256 must be a 64-character hexadecimal digest.",
        )
    content = _read_bounded_upload(file, request)
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(normalized_sha256, actual_sha256):
        raise HTTPException(
            status_code=409,
            detail="The file changed after preview. Preview it again before import.",
        )
    try:
        parsed_mapping = parse_mapping(mapping)
        dataset = read_tabular_file(
            content, file.filename, sheet_name=sheet_name or None
        )
        known_source = KNOWN_SOURCE_PROFILES.get(source_profile)
        resolved_currency = _resolve_profile_currency(source_profile, source_currency)
        mapped = map_tabular_sales(
            dataset, parsed_mapping, source_currency=resolved_currency
        )
        _validate_known_source_selection(
            mapped.frame,
            source_profile,
            mapping=parsed_mapping,
        )
        semantics = dict(mapped.record_semantics)
        resolved_name = normalized_name
        if known_source is not None:
            resolved_name = known_source[0]
            semantics.update(
                {
                    "record_count_label": known_source[1],
                    "entity_count_label": known_source[2],
                    "average_value_label": known_source[3],
                    "average_frequency_label": known_source[4],
                    "aggregate_record_proxy": known_source[5],
                    "warning": known_source[6],
                    "entity_warning": known_source[7],
                }
            )
        profile_payload = {
            "dataset_name": resolved_name,
            "source_format": dataset.file_format,
            "source_sheet": dataset.selected_sheet,
            "original_filename": dataset.filename,
            "content_sha256": dataset.file_sha256,
            "currency": resolved_currency,
            "metric_mode": mapped.metric_mode,
            "mapped_fields": mapped.mapping,
            "generated_fields": mapped.generated_fields,
            "warnings": mapped.warnings,
            "aggregate_record_proxy": semantics["aggregate_record_proxy"],
            "record_count_label": semantics["record_count_label"],
            "entity_count_label": semantics["entity_count_label"],
            "average_value_label": semantics["average_value_label"],
            "average_frequency_label": semantics["average_frequency_label"],
            "semantic_warning": semantics["warning"],
            "entity_warning": semantics["entity_warning"],
            "units_available": semantics["units_available"],
            "units_label": semantics["units_label"],
            "unit_warning": semantics["unit_warning"],
            "anomaly_features": semantics["anomaly_features"],
        }
        summary = load_sales_frame(
            mapped.frame,
            session,
            replace=True,
            profile=profile_payload,
            profile_serializer=_profile_dict,
        )
        serialized_profile = summary.pop("_dataset_profile", None)
        if serialized_profile is None:  # pragma: no cover - transaction invariant
            raise RuntimeError("Imported dataset profile was not persisted.")
        return {
            **summary,
            "dataset_profile": serialized_profile,
            "mapping": mapped.mapping,
            "generated_fields": mapped.generated_fields,
            "warnings": mapped.warnings,
        }
    except DataValidationError:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/profile", response_model=DatasetProfileResponse)
def get_dataset_profile(session: DbSession) -> dict:
    profile = session.get(DatasetProfile, 1)
    if profile is None:
        raise HTTPException(status_code=404, detail="No active dataset profile exists.")
    return _profile_dict(profile)
