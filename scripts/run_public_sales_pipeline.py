from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from data_pipeline.public_sales import (
    IowaLiquorSalesPreparer,
    PublicSalesArtifactWriter,
    UCIOnlineRetailPreparer,
)
from data_pipeline.validation import SalesFrameValidator
from ml.forecasting import RevenueForecaster


@dataclass(frozen=True)
class PublicSalesPipeline:
    source: str
    data_dir: Path
    output_dir: Path
    horizon: int = 3

    @property
    def application_path(self) -> Path:
        return self.output_dir / f"{self.source}_application_sales.csv"

    def prepare(self) -> dict:
        if self.source == "uci":
            frame, summary = UCIOnlineRetailPreparer.from_path(self.data_dir).prepare()
        else:
            frame, summary = IowaLiquorSalesPreparer.from_path(self.data_dir).prepare()
        paths = PublicSalesArtifactWriter(self.output_dir).write(
            self.source, frame, summary
        )
        return {
            "stage": "prepare",
            "source": self.source,
            "artifacts": {key: str(value) for key, value in paths.items()},
            "summary": summary,
        }

    def analyze(self) -> dict:
        if not self.application_path.is_file():
            raise FileNotFoundError(
                f"Prepared data does not exist: {self.application_path}. "
                "Run the prepare stage first."
            )
        frame = pd.read_csv(self.application_path)
        validated = SalesFrameValidator().validate(frame)
        forecast_frame = validated
        excluded_partial_months: list[str] = []
        if self.source == "uci":
            latest_date = validated["order_date"].max()
            if latest_date < latest_date + pd.offsets.MonthEnd(0):
                latest_period = latest_date.to_period("M")
                excluded_partial_months.append(str(latest_period))
                forecast_frame = validated[
                    validated["order_date"].dt.to_period("M") != latest_period
                ]
        result = {
            "dataset_rows": int(len(validated)),
            "customers": int(validated["customer_id"].nunique()),
            "revenue": round(float(validated["revenue"].sum()), 2),
            "forecast_input_rows": int(len(forecast_frame)),
            "excluded_partial_months": excluded_partial_months,
            "forecast": RevenueForecaster(horizon=self.horizon).run(forecast_frame),
        }
        analysis_path = self.output_dir / f"{self.source}_analysis.json"
        analysis_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return {
            "stage": "analyze",
            "source": self.source,
            "artifact": str(analysis_path),
            "result": result,
        }

    def run(self, stage: str) -> list[dict]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        results: list[dict] = []
        if stage in {"prepare", "all"}:
            results.append(self.prepare())
        if stage in {"analyze", "all"}:
            results.append(self.analyze())
        return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare and analyze the UCI or Iowa public sales dataset."
    )
    parser.add_argument("--source", choices=("uci", "iowa"), required=True)
    parser.add_argument(
        "--data-dir", type=Path, required=True, help="Directory for the raw download."
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Directory for generated artifacts."
    )
    parser.add_argument(
        "--stage",
        choices=("prepare", "analyze", "all"),
        default="all",
        help="Pipeline stage to run.",
    )
    parser.add_argument("--horizon", type=int, default=3, help="Forecast months.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pipeline = PublicSalesPipeline(
        source=args.source,
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        horizon=args.horizon,
    )
    for result in pipeline.run(args.stage):
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
