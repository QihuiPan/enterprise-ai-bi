from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from data_pipeline.validation import REQUIRED_COLUMNS, SalesFrameValidator

UCI_SOURCE = "https://archive.ics.uci.edu/dataset/502/online+retail+ii"
UCI_DOI = "https://doi.org/10.24432/C5CG6D"
UCI_DOWNLOAD_URL = (
    "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
)
IOWA_SOURCE = "https://data.iowa.gov/catalog/dataset/1261"
IOWA_DOWNLOAD_URL = "https://idh-be.iowa.gov/api/v1/datasets/1261/rows.csv"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_file(url: str, destination: str | Path) -> dict[str, int | str]:
    """Download a public source atomically and return reproducibility metadata."""

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "enterprise-ai-bi/0.1 public-data-pipeline"},
        )
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=f".{path.name}.", delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                with urllib.request.urlopen(request, timeout=120) as response:
                    shutil.copyfileobj(response, temporary, length=1024 * 1024)
            temporary_path.replace(path)
        except BaseException:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
    return {
        "url": url,
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _largest_member(archive: zipfile.ZipFile, suffix: str) -> zipfile.ZipInfo:
    candidates = _members(archive, suffix)
    return max(candidates, key=lambda member: member.file_size)


def _members(archive: zipfile.ZipFile, suffix: str) -> list[zipfile.ZipInfo]:
    candidates = [
        member
        for member in archive.infolist()
        if not member.is_dir() and member.filename.lower().endswith(suffix)
    ]
    if not candidates:
        raise ValueError(f"Downloaded archive does not contain a {suffix} file.")
    return sorted(candidates, key=lambda member: member.filename)


def _clean_identifier(series: pd.Series, prefix: str) -> pd.Series:
    values = series.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    return prefix + values


def _column_aliases(frame: pd.DataFrame) -> dict[str, str]:
    canonical = {
        str(column).strip().lower().replace(" ", "").replace("_", ""): str(column)
        for column in frame.columns
    }
    aliases = {
        "invoice": ("invoice", "invoiceno"),
        "quantity": ("quantity",),
        "invoice_date": ("invoicedate",),
        "unit_price": ("price", "unitprice"),
        "customer_id": ("customerid",),
        "country": ("country",),
    }
    resolved: dict[str, str] = {}
    for target, choices in aliases.items():
        source = next((canonical[choice] for choice in choices if choice in canonical), None)
        if source is None:
            raise ValueError(f"UCI workbook is missing the '{target}' field.")
        resolved[target] = source
    return resolved


def _finalize_aggregates(
    aggregates: list[pd.DataFrame],
    *,
    source_prefix: str,
    product: str,
) -> tuple[pd.DataFrame, float]:
    if not aggregates:
        raise ValueError("No valid sales records remained after source cleaning.")
    combined = pd.concat(aggregates, ignore_index=True)
    dimensions = ["order_date", "customer_id", "region", "category"]
    combined = (
        combined.groupby(dimensions, as_index=False, dropna=False)[
            ["quantity", "source_revenue"]
        ]
        .sum()
        .sort_values(dimensions)
        .reset_index(drop=True)
    )
    combined["unit_price"] = (
        combined["source_revenue"] / combined["quantity"]
    ).round(2)
    combined["discount"] = 0.0
    combined["product"] = product
    combined["order_id"] = [
        f"{source_prefix}-{index:08d}" for index in range(1, len(combined) + 1)
    ]
    validated = SalesFrameValidator().validate(combined.loc[:, REQUIRED_COLUMNS])
    application_revenue = float(validated["revenue"].sum())
    return validated.loc[:, REQUIRED_COLUMNS].copy(), application_revenue


def _collapse_aggregates(aggregates: list[pd.DataFrame]) -> pd.DataFrame:
    combined = pd.concat(aggregates, ignore_index=True)
    dimensions = ["order_date", "customer_id", "region", "category"]
    return combined.groupby(dimensions, as_index=False, dropna=False)[
        ["quantity", "source_revenue"]
    ].sum()


@dataclass(frozen=True)
class UCIOnlineRetailPreparer:
    data_dir: Path
    download_url: str = UCI_DOWNLOAD_URL

    @classmethod
    def from_path(cls, data_dir: str | Path) -> UCIOnlineRetailPreparer:
        return cls(Path(data_dir))

    @property
    def archive_path(self) -> Path:
        return self.data_dir / "online_retail_ii.zip"

    def prepare(self) -> tuple[pd.DataFrame, dict]:
        download = download_file(self.download_url, self.archive_path)
        counters = {
            "source_rows": 0,
            "cancelled_rows": 0,
            "invalid_rows": 0,
            "valid_rows": 0,
            "source_invoices": 0,
        }
        aggregates: list[pd.DataFrame] = []
        dates: list[pd.Timestamp] = []
        countries: set[str] = set()
        source_revenue = 0.0

        with zipfile.ZipFile(self.archive_path) as archive:
            member = _largest_member(archive, ".xlsx")
            with tempfile.TemporaryDirectory(prefix="uci-online-retail-") as temporary:
                workbook_path = Path(temporary) / Path(member.filename).name
                with archive.open(member) as source, workbook_path.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                with pd.ExcelFile(workbook_path, engine="openpyxl") as workbook:
                    for sheet_name in workbook.sheet_names:
                        raw = pd.read_excel(workbook, sheet_name=sheet_name)
                        mapped, sheet_counters = self._transform_sheet(raw)
                        for key, value in sheet_counters.items():
                            counters[key] += value
                        if mapped.empty:
                            continue
                        source_revenue += float(mapped["source_revenue"].sum())
                        countries.update(mapped["region"].dropna().astype(str))
                        dates.extend(
                            [mapped["order_date"].min(), mapped["order_date"].max()]
                        )
                        aggregates.append(mapped)

        application, application_revenue = _finalize_aggregates(
            aggregates,
            source_prefix="UCI",
            product="Daily online retail basket",
        )
        summary = {
            "dataset": "UCI Online Retail II",
            "source": UCI_SOURCE,
            "doi": UCI_DOI,
            "license": "CC BY 4.0",
            "currency": "GBP",
            "download": download,
            **counters,
            "prepared_rows": int(len(application)),
            "customers": int(application["customer_id"].nunique()),
            "regions": len(countries),
            "date_min": min(dates).date().isoformat(),
            "date_max": max(dates).date().isoformat(),
            "units": int(application["quantity"].sum()),
            "source_revenue": round(source_revenue, 2),
            "application_revenue": round(application_revenue, 2),
            "revenue_rounding_delta": round(application_revenue - source_revenue, 2),
            "grain": "customer-country-day",
        }
        return application, summary

    @staticmethod
    def _transform_sheet(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
        aliases = _column_aliases(raw)
        data = raw.rename(columns={source: target for target, source in aliases.items()})
        data = data.loc[:, aliases.keys()].copy()
        source_rows = len(data)
        invoice = data["invoice"].astype("string").str.strip()
        cancelled = invoice.str.upper().str.startswith("C", na=False)
        quantity = pd.to_numeric(data["quantity"], errors="coerce")
        unit_price = pd.to_numeric(data["unit_price"], errors="coerce")
        order_date = pd.to_datetime(data["invoice_date"], errors="coerce")
        customer = data["customer_id"].astype("string").str.strip()
        country = data["country"].astype("string").str.strip()
        valid = (
            ~cancelled
            & quantity.notna()
            & quantity.gt(0)
            & quantity.mod(1).eq(0)
            & unit_price.notna()
            & unit_price.ge(0)
            & order_date.notna()
            & customer.notna()
            & customer.ne("")
            & country.notna()
            & country.ne("")
        )
        mapped = pd.DataFrame(
            {
                "order_date": order_date[valid].dt.normalize(),
                "customer_id": _clean_identifier(customer[valid], "UCI-"),
                "region": country[valid],
                "category": "Online Retail",
                "quantity": quantity[valid].astype("int64"),
                "source_revenue": quantity[valid] * unit_price[valid],
            }
        )
        if not mapped.empty:
            mapped = _collapse_aggregates([mapped])
        return mapped, {
            "source_rows": int(source_rows),
            "cancelled_rows": int(cancelled.sum()),
            "invalid_rows": int((~valid & ~cancelled).sum()),
            "valid_rows": int(valid.sum()),
            "source_invoices": int(invoice[valid].nunique()),
        }


@dataclass(frozen=True)
class IowaLiquorSalesPreparer:
    data_dir: Path
    download_url: str = IOWA_DOWNLOAD_URL
    chunksize: int = 100_000

    @classmethod
    def from_path(
        cls, data_dir: str | Path, *, chunksize: int = 100_000
    ) -> IowaLiquorSalesPreparer:
        return cls(Path(data_dir), chunksize=chunksize)

    @property
    def archive_path(self) -> Path:
        return self.data_dir / "iowa_liquor_sales_2024.zip"

    def _chunks(self) -> Iterator[pd.DataFrame]:
        with zipfile.ZipFile(self.archive_path) as archive:
            for member in _members(archive, ".csv"):
                with archive.open(member) as csv_file:
                    yield from pd.read_csv(
                        csv_file, chunksize=self.chunksize, low_memory=False
                    )

    def prepare(self) -> tuple[pd.DataFrame, dict]:
        download = download_file(self.download_url, self.archive_path)
        aggregates: list[pd.DataFrame] = []
        source_rows = 0
        valid_rows = 0
        source_revenue = 0.0
        source_invoices = 0
        stores: set[str] = set()
        categories: set[str] = set()
        counties: set[str] = set()
        dates: list[pd.Timestamp] = []

        for raw in self._chunks():
            source_rows += len(raw)
            mapped, metadata = self._transform_chunk(raw)
            valid_rows += metadata["valid_rows"]
            source_revenue += metadata["source_revenue"]
            source_invoices += metadata["source_invoices"]
            stores.update(metadata["stores"])
            categories.update(metadata["categories"])
            counties.update(metadata["counties"])
            if mapped.empty:
                continue
            dates.extend([metadata["date_min"], metadata["date_max"]])
            aggregates.append(mapped)
            if len(aggregates) >= 8:
                aggregates = [_collapse_aggregates(aggregates)]

        application, application_revenue = _finalize_aggregates(
            aggregates,
            source_prefix="IA2024",
            product="Monthly spirits basket",
        )
        summary = {
            "dataset": "Iowa Liquor Sales, 2024",
            "source": IOWA_SOURCE,
            "license": "CC BY 4.0",
            "currency": "USD",
            "download": download,
            "source_rows": int(source_rows),
            "invalid_rows": int(source_rows - valid_rows),
            "valid_rows": int(valid_rows),
            "source_invoices": int(source_invoices),
            "prepared_rows": int(len(application)),
            "stores": len(stores),
            "categories": len(categories),
            "counties": len(counties),
            "date_min": min(dates).date().isoformat(),
            "date_max": max(dates).date().isoformat(),
            "units": int(application["quantity"].sum()),
            "source_revenue": round(source_revenue, 2),
            "application_revenue": round(application_revenue, 2),
            "revenue_rounding_delta": round(application_revenue - source_revenue, 2),
            "grain": "store-county-category-month",
        }
        return application, summary

    @staticmethod
    def _transform_chunk(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        required = {
            "invoice_id",
            "ordered_on",
            "store_no",
            "county_name",
            "category_name",
            "sales_bottles",
            "sales_dollars",
        }
        missing = sorted(required.difference(raw.columns))
        if missing:
            raise ValueError(f"Iowa source is missing columns: {', '.join(missing)}.")

        dates = pd.to_datetime(raw["ordered_on"], errors="coerce")
        quantity = pd.to_numeric(raw["sales_bottles"], errors="coerce")
        revenue = pd.to_numeric(raw["sales_dollars"], errors="coerce")
        store = raw["store_no"].astype("string").str.strip()
        county = raw["county_name"].astype("string").str.strip().fillna("Unknown County")
        county = county.mask(county.eq(""), "Unknown County")
        category = raw["category_name"].astype("string").str.strip()
        category = category.fillna("Uncategorized Spirits").mask(
            category.eq(""), "Uncategorized Spirits"
        )
        valid = (
            dates.notna()
            & dates.dt.year.eq(2024)
            & quantity.notna()
            & quantity.gt(0)
            & quantity.mod(1).eq(0)
            & revenue.notna()
            & revenue.ge(0)
            & store.notna()
            & store.ne("")
        )
        month = dates[valid].dt.to_period("M").dt.to_timestamp()
        mapped = pd.DataFrame(
            {
                "order_date": month,
                "customer_id": _clean_identifier(store[valid], "IA-STORE-"),
                "region": county[valid],
                "category": category[valid],
                "quantity": quantity[valid].astype("int64"),
                "source_revenue": revenue[valid].astype(float),
            }
        )
        if not mapped.empty:
            mapped = _collapse_aggregates([mapped])
        return mapped, {
            "valid_rows": int(valid.sum()),
            "source_revenue": float(revenue[valid].sum()),
            "source_invoices": int(raw.loc[valid, "invoice_id"].nunique()),
            "stores": set(store[valid].dropna().astype(str)),
            "categories": set(category[valid].dropna().astype(str)),
            "counties": set(county[valid].dropna().astype(str)),
            "date_min": dates[valid].min(),
            "date_max": dates[valid].max(),
        }


@dataclass(frozen=True)
class PublicSalesArtifactWriter:
    output_dir: Path

    def write(self, dataset: str, frame: pd.DataFrame, summary: dict) -> dict[str, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        application_path = self.output_dir / f"{dataset}_application_sales.csv"
        summary_path = self.output_dir / f"{dataset}_preparation_summary.json"
        frame.to_csv(application_path, index=False)
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return {"application": application_path, "summary": summary_path}
