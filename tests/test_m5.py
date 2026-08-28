from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from data_pipeline import m5
from data_pipeline.m5 import prepare_m5_frame, to_application_frame, write_prepared_m5
from ml.m5_forecasting import save_m5_model, train_m5_model


def build_m5_fixture(directory, days: int = 120) -> None:
    dates = pd.date_range("2020-01-01", periods=days, freq="D")
    calendar = pd.DataFrame(
        {
            "date": dates,
            "wm_yr_wk": 1000 + np.arange(days) // 7,
            "d": [f"d_{day}" for day in range(1, days + 1)],
            "event_name_1": ["Event" if day % 14 == 0 else None for day in range(days)],
            "event_name_2": None,
            "snap_CA": [day % 2 for day in range(days)],
            "snap_TX": 0,
            "snap_WI": 0,
        }
    )
    calendar.to_csv(directory / "calendar.csv", index=False)

    sales_rows = []
    for index, item in enumerate(("ITEM_1", "ITEM_2")):
        row = {
            "id": f"{item}_CA_1_evaluation",
            "item_id": item,
            "dept_id": "FOODS_1",
            "cat_id": "FOODS",
            "store_id": "CA_1",
            "state_id": "CA",
        }
        row.update(
            {f"d_{day}": 1 + ((day + index) % 5) for day in range(1, days + 1)}
        )
        sales_rows.append(row)
    pd.DataFrame(sales_rows).to_csv(directory / "sales_train_evaluation.csv", index=False)

    price_rows = []
    for week in sorted(calendar["wm_yr_wk"].unique()):
        price_rows.extend(
            [
                {
                    "store_id": "CA_1",
                    "item_id": "ITEM_1",
                    "wm_yr_wk": week,
                    "sell_price": 2.0,
                },
                {
                    "store_id": "CA_1",
                    "item_id": "ITEM_2",
                    "wm_yr_wk": week,
                    "sell_price": 3.0,
                },
            ]
        )
    pd.DataFrame(price_rows).to_csv(directory / "sell_prices.csv", index=False)


def test_m5_preparation_aggregates_every_item_day(tmp_path) -> None:
    build_m5_fixture(tmp_path)
    frame, summary = prepare_m5_frame(tmp_path, verify_checksums=False)
    assert summary["source_series"] == 2
    assert summary["source_item_day_values"] == 240
    assert len(frame) == 120
    first = frame.iloc[0]
    assert first["quantity"] == 5
    assert first["revenue"] == 13.0
    application = to_application_frame(frame)
    assert application["order_id"].is_unique
    assert set(application["region"]) == {"CA"}


def test_m5_model_trains_with_temporal_holdout(tmp_path) -> None:
    build_m5_fixture(tmp_path)
    frame, _ = prepare_m5_frame(tmp_path, verify_checksums=False)
    artifact, metrics, predictions = train_m5_model(frame, horizon=7)
    assert artifact["target_transform"] == "log1p"
    assert metrics["model"] in metrics["candidate_tuning_results"]
    assert sum(metrics["selected_blend_weights"].values()) == 1
    assert metrics["tuning_rows"] == 7
    assert metrics["holdout_rows"] == 7
    assert metrics["model_metrics"]["rmse"] >= 0
    assert len(predictions) == 7
    assert save_m5_model(artifact, tmp_path / "artifacts" / "model.joblib").is_file()


def test_m5_checksums_and_prepared_artifacts(tmp_path, monkeypatch) -> None:
    build_m5_fixture(tmp_path)
    expected = {}
    for name in ("calendar.csv", "sales_train_evaluation.csv", "sell_prices.csv"):
        content = (tmp_path / name).read_bytes()
        expected[name] = {
            "bytes": len(content),
            "md5": hashlib.md5(content, usedforsecurity=False).hexdigest(),
        }
    monkeypatch.setattr(m5, "M5_FILES", expected)

    verified = m5.verify_m5_files(tmp_path)
    assert set(verified) == set(expected)
    frame, summary = prepare_m5_frame(tmp_path, verify_checksums=True)
    paths = write_prepared_m5(frame, summary, tmp_path / "artifacts")
    assert all(path.is_file() for path in paths.values())
