from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from backend.app.models import DatasetProfile


def dataset_version_from_profile(profile: DatasetProfile) -> dict[str, str]:
    """Hash all material import choices, not only the uploaded file bytes."""

    payload = {
        "dataset_name": profile.dataset_name,
        "source_format": profile.source_format,
        "source_sheet": profile.source_sheet,
        "original_filename": profile.original_filename,
        "content_sha256": profile.content_sha256,
        "rows_loaded": profile.rows_loaded,
        "date_min": profile.date_min.isoformat(),
        "date_max": profile.date_max.isoformat(),
        "revenue_total": profile.revenue_total,
        "currency": profile.currency,
        "metric_mode": profile.metric_mode,
        "mapped_fields": profile.mapped_fields,
        "generated_fields": profile.generated_fields,
        "warnings": profile.warnings,
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
        "anomaly_features": profile.anomaly_features,
    }
    profile_sha256 = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "content_sha256": profile.content_sha256,
        "currency": profile.currency,
        "profile_sha256": profile_sha256,
    }


def active_dataset_version(session: Session) -> dict[str, str] | None:
    """Return the immutable identity used to bind parallel read responses."""

    profile = session.get(DatasetProfile, 1)
    return None if profile is None else dataset_version_from_profile(profile)
