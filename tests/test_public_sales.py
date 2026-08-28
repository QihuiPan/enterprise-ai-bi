from __future__ import annotations

import json
import zipfile

import pandas as pd

from data_pipeline.public_sales import (
    IowaLiquorSalesPreparer,
    PublicSalesArtifactWriter,
    UCIOnlineRetailPreparer,
)


def _write_uci_archive(directory) -> None:
    workbook = directory / "online_retail_ii.xlsx"
    first = pd.DataFrame(
        {
            "Invoice": ["100", "101", "C102", "103"],
            "Quantity": [2, 1, 3, -1],
            "InvoiceDate": [
                "2009-12-01",
                "2009-12-01",
                "2009-12-02",
                "2009-12-03",
            ],
            "Price": [4.0, 2.0, 1.0, 5.0],
            "Customer ID": [12345, 12345, 12345, 12345],
            "Country": ["United Kingdom"] * 4,
        }
    )
    second = pd.DataFrame(
        {
            "InvoiceNo": ["200", "201"],
            "Quantity": [2, 1],
            "InvoiceDate": ["2010-12-01", "2010-12-02"],
            "UnitPrice": [3.0, 8.0],
            "CustomerID": [99999, None],
            "Country": ["France", "France"],
        }
    )
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        first.to_excel(writer, sheet_name="Year 2009-2010", index=False)
        second.to_excel(writer, sheet_name="Year 2010-2011", index=False)
    with zipfile.ZipFile(directory / "online_retail_ii.zip", "w") as archive:
        archive.write(workbook, workbook.name)
    workbook.unlink()


def _write_iowa_archive(directory) -> None:
    rows = pd.DataFrame(
        {
            "invoice_id": ["INV-1", "INV-2", "INV-3", "INV-4"],
            "ordered_on": ["2024-01-02", "2024-01-20", "2024-02-01", "2023-12-31"],
            "store_no": ["100", "100", "200", "300"],
            "county_name": ["Polk", "Polk", None, "Linn"],
            "category_name": ["Vodka", "Vodka", "Gin", "Rum"],
            "sales_bottles": [2, 3, -1, 5],
            "sales_dollars": [20.0, 30.0, 12.0, 50.0],
        }
    )
    with zipfile.ZipFile(directory / "iowa_liquor_sales_2024.zip", "w") as archive:
        for part_number, part in enumerate((rows.iloc[:2], rows.iloc[2:]), start=1):
            csv_path = directory / f"iowa_liquor_sales_2024_part_{part_number:04d}.csv"
            part.to_csv(csv_path, index=False)
            archive.write(csv_path, csv_path.name)
            csv_path.unlink()


def test_uci_online_retail_preparation_cleans_and_aggregates(tmp_path) -> None:
    _write_uci_archive(tmp_path)
    frame, summary = UCIOnlineRetailPreparer.from_path(tmp_path).prepare()

    assert summary["source_rows"] == 6
    assert summary["cancelled_rows"] == 1
    assert summary["invalid_rows"] == 2
    assert summary["valid_rows"] == 3
    assert summary["prepared_rows"] == 2
    assert summary["currency"] == "GBP"
    assert summary["source_revenue"] == 16.0
    assert frame["order_id"].is_unique
    assert set(frame["customer_id"]) == {"UCI-12345", "UCI-99999"}


def test_iowa_preparation_filters_year_and_aggregates_monthly(tmp_path) -> None:
    _write_iowa_archive(tmp_path)
    frame, summary = IowaLiquorSalesPreparer.from_path(
        tmp_path, chunksize=2
    ).prepare()

    assert summary["source_rows"] == 4
    assert summary["valid_rows"] == 2
    assert summary["invalid_rows"] == 2
    assert summary["prepared_rows"] == 1
    assert summary["source_invoices"] == 2
    assert summary["source_revenue"] == 50.0
    assert summary["date_max"] == "2024-01-20"
    assert frame.iloc[0]["quantity"] == 5
    assert frame.iloc[0]["unit_price"] == 10.0
    assert frame.iloc[0]["customer_id"] == "IA-STORE-100"


def test_public_sales_writer_creates_application_and_summary_files(tmp_path) -> None:
    _write_iowa_archive(tmp_path)
    frame, summary = IowaLiquorSalesPreparer.from_path(tmp_path).prepare()
    paths = PublicSalesArtifactWriter(tmp_path / "artifacts").write(
        "iowa", frame, summary
    )

    assert paths["application"].is_file()
    written_summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert written_summary["dataset"] == "Iowa Liquor Sales, 2024"
