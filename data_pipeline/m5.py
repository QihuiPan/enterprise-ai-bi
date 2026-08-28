from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

M5_SOURCE = "https://doi.org/10.5281/zenodo.10203108"
M5_FILES = {
    "calendar.csv": {
        "bytes": 103_469,
        "md5": "3ffeab2991b0c8e861d008b39ea4c95c",
    },
    "sales_train_evaluation.csv": {
        "bytes": 121_736_518,
        "md5": "b806dfc9f30a745102b708c09951f6aa",
    },
    "sell_prices.csv": {
        "bytes": 203_395_785,
        "md5": "08c591caa99e55daf3e0ccac913f7c85",
    },
}


def _file_md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_m5_files(data_dir: str | Path) -> dict[str, dict[str, int | str]]:
    directory = Path(data_dir)
    verified: dict[str, dict[str, int | str]] = {}
    for name, expected in M5_FILES.items():
        path = directory / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing required M5 file: {path}")
        size = path.stat().st_size
        if size != expected["bytes"]:
            raise ValueError(
                f"Unexpected size for {name}: {size} bytes; expected {expected['bytes']}."
            )
        checksum = _file_md5(path)
        if checksum != expected["md5"]:
            raise ValueError(
                f"Checksum mismatch for {name}: {checksum}; expected {expected['md5']}."
            )
        verified[name] = {"bytes": size, "md5": checksum}
    return verified


def _read_sales(path: Path) -> tuple[pd.DataFrame, list[str]]:
    columns = pd.read_csv(path, nrows=0).columns.tolist()
    day_columns = [column for column in columns if column.startswith("d_")]
    if not day_columns:
        raise ValueError("M5 sales file does not contain d_* daily sales columns.")
    required = ["id", "item_id", "dept_id", "cat_id", "store_id", "state_id"]
    missing = [column for column in required if column not in columns]
    if missing:
        raise ValueError(f"M5 sales file is missing columns: {', '.join(missing)}.")
    dtype: dict[str, str | type] = {column: "int16" for column in day_columns}
    dtype.update({column: "string" for column in required})
    return pd.read_csv(path, dtype=dtype), day_columns


def _read_calendar(path: Path, day_columns: list[str]) -> pd.DataFrame:
    calendar = pd.read_csv(path)
    required = {"d", "date", "wm_yr_wk", "event_name_1", "event_name_2"}
    required.update({"snap_CA", "snap_TX", "snap_WI"})
    missing = sorted(required.difference(calendar.columns))
    if missing:
        raise ValueError(f"M5 calendar file is missing columns: {', '.join(missing)}.")
    calendar = calendar[calendar["d"].isin(day_columns)].copy()
    calendar["order_date"] = pd.to_datetime(calendar["date"], errors="raise")
    calendar["day_number"] = calendar["d"].str.removeprefix("d_").astype(int)
    calendar["event_flag"] = (
        calendar[["event_name_1", "event_name_2"]].notna().any(axis=1).astype("int8")
    )
    return calendar.sort_values("day_number")


def _prepare_m5_frame(
    directory: Path,
    *,
    verify_checksums: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Aggregate all M5 item-day observations to store/category/day rows."""

    verified = verify_m5_files(directory) if verify_checksums else {}
    sales, day_columns = _read_sales(directory / "sales_train_evaluation.csv")
    calendar = _read_calendar(directory / "calendar.csv", day_columns)
    prices = pd.read_csv(
        directory / "sell_prices.csv",
        dtype={
            "store_id": "string",
            "item_id": "string",
            "wm_yr_wk": "int32",
            "sell_price": "float32",
        },
    )
    price_index = prices.set_index(["store_id", "item_id", "wm_yr_wk"])["sell_price"]

    metadata_columns = ["item_id", "cat_id", "store_id", "state_id"]
    metadata = sales.loc[:, metadata_columns]
    group_columns = ["state_id", "store_id", "cat_id"]
    groups = metadata[group_columns].drop_duplicates().sort_values(group_columns)
    groups = groups.reset_index(drop=True)
    group_index = pd.MultiIndex.from_frame(groups)
    group_codes = group_index.get_indexer(pd.MultiIndex.from_frame(metadata[group_columns]))
    if (group_codes < 0).any():
        raise ValueError("Unable to map every M5 series to a store/category group.")

    item_keys = metadata[["store_id", "item_id"]].reset_index(drop=True)
    rows: list[dict] = []
    missing_price_units = 0
    for week, week_days in calendar.groupby("wm_yr_wk", sort=True):
        price_keys = pd.MultiIndex.from_arrays(
            [
                item_keys["store_id"],
                item_keys["item_id"],
                np.full(len(item_keys), int(week), dtype="int32"),
            ],
            names=["store_id", "item_id", "wm_yr_wk"],
        )
        price_vector = price_index.reindex(price_keys).to_numpy(dtype="float64")

        for day in week_days.itertuples(index=False):
            units = sales[day.d].to_numpy(dtype="int64")
            missing_price_units += int(units[np.isnan(price_vector)].sum())
            revenue_values = units * np.nan_to_num(price_vector, nan=0.0)
            group_units = np.bincount(group_codes, weights=units, minlength=len(groups))
            group_revenue = np.bincount(
                group_codes, weights=revenue_values, minlength=len(groups)
            )

            for group_id, group in groups.iterrows():
                quantity = int(group_units[group_id])
                revenue = float(group_revenue[group_id])
                state = str(group["state_id"])
                rows.append(
                    {
                        "series_id": f"{group['store_id']}:{group['cat_id']}",
                        "d": day.d,
                        "day_number": int(day.day_number),
                        "order_date": day.order_date,
                        "wm_yr_wk": int(day.wm_yr_wk),
                        "state_id": state,
                        "store_id": str(group["store_id"]),
                        "category": str(group["cat_id"]),
                        "quantity": quantity,
                        "unit_price": round(revenue / quantity, 4) if quantity else 0.0,
                        "revenue": round(revenue, 2),
                        "event_flag": int(day.event_flag),
                        "snap": int(getattr(day, f"snap_{state}")),
                    }
                )

    if missing_price_units:
        raise ValueError(
            f"M5 prices are missing for {missing_price_units} sold units; refusing to "
            "understate revenue."
        )

    frame = pd.DataFrame(rows).sort_values(["order_date", "store_id", "category"])
    frame = frame.reset_index(drop=True)
    summary = {
        "source": M5_SOURCE,
        "source_series": int(len(sales)),
        "source_days": int(len(day_columns)),
        "source_item_day_values": int(len(sales) * len(day_columns)),
        "prepared_rows": int(len(frame)),
        "prepared_series": int(frame["series_id"].nunique()),
        "date_min": frame["order_date"].min().date().isoformat(),
        "date_max": frame["order_date"].max().date().isoformat(),
        "units": int(frame["quantity"].sum()),
        "revenue": round(float(frame["revenue"].sum()), 2),
        "verified_files": verified,
    }
    return frame, summary


@dataclass(frozen=True)
class M5DataPreparer:
    data_dir: Path
    verify_checksums: bool = True

    @classmethod
    def from_path(
        cls, data_dir: str | Path, *, verify_checksums: bool = True
    ) -> M5DataPreparer:
        return cls(Path(data_dir), verify_checksums)

    def prepare(self) -> tuple[pd.DataFrame, dict]:
        return _prepare_m5_frame(
            self.data_dir, verify_checksums=self.verify_checksums
        )


def prepare_m5_frame(
    data_dir: str | Path,
    *,
    verify_checksums: bool = True,
) -> tuple[pd.DataFrame, dict]:
    return M5DataPreparer.from_path(
        data_dir, verify_checksums=verify_checksums
    ).prepare()


def to_application_frame(frame: pd.DataFrame) -> pd.DataFrame:
    positive = frame[frame["quantity"] > 0].copy()
    positive["order_id"] = (
        "M5-"
        + positive["d"].astype(str)
        + "-"
        + positive["store_id"].astype(str)
        + "-"
        + positive["category"].astype(str)
    )
    positive["customer_id"] = positive["store_id"]
    positive["region"] = positive["state_id"]
    positive["product"] = positive["store_id"] + " " + positive["category"]
    positive["discount"] = 0.0
    return positive[
        [
            "order_id",
            "order_date",
            "customer_id",
            "region",
            "category",
            "product",
            "quantity",
            "unit_price",
            "discount",
        ]
    ]


@dataclass(frozen=True)
class M5ArtifactWriter:
    output_dir: Path

    def write(self, frame: pd.DataFrame, summary: dict) -> dict[str, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        prepared_path = self.output_dir / "m5_store_category_daily.csv"
        application_path = self.output_dir / "m5_application_sales.csv"
        summary_path = self.output_dir / "m5_preparation_summary.json"
        frame.to_csv(prepared_path, index=False)
        to_application_frame(frame).to_csv(application_path, index=False)
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return {
            "prepared": prepared_path,
            "application": application_path,
            "summary": summary_path,
        }


def write_prepared_m5(
    frame: pd.DataFrame,
    summary: dict,
    output_dir: str | Path,
) -> dict[str, Path]:
    return M5ArtifactWriter(Path(output_dir)).write(frame, summary)
