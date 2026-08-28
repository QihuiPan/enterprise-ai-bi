from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from data_pipeline.m5 import prepare_m5_frame, write_prepared_m5
from ml.m5_forecasting import save_m5_model, train_m5_model


@dataclass(frozen=True)
class M5Pipeline:
    data_dir: Path
    output_dir: Path
    horizon: int = 28

    @property
    def prepared_path(self) -> Path:
        return self.output_dir / "m5_store_category_daily.csv"

    def prepare(self) -> dict:
        frame, summary = prepare_m5_frame(self.data_dir, verify_checksums=True)
        paths = write_prepared_m5(frame, summary, self.output_dir)
        return {key: str(value) for key, value in paths.items()}

    def train(self) -> dict:
        if not self.prepared_path.is_file():
            raise FileNotFoundError(
                f"Prepared data does not exist: {self.prepared_path}. "
                "Run the prepare stage first."
            )
        frame = pd.read_csv(self.prepared_path, parse_dates=["order_date"])
        artifact, metrics, predictions = train_m5_model(
            frame, horizon=self.horizon
        )
        model_path = save_m5_model(
            artifact, self.output_dir / "m5_forecaster.joblib"
        )
        metrics_path = self.output_dir / "m5_training_metrics.json"
        predictions_path = self.output_dir / "m5_holdout_predictions.csv"
        metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        predictions.to_csv(predictions_path, index=False)
        return {
            "model": str(model_path),
            "metrics": str(metrics_path),
            "predictions": str(predictions_path),
            "result": metrics,
        }

    def run(self, stage: str) -> list[dict]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        results = []
        if stage in {"prepare", "all"}:
            results.append(self.prepare())
        if stage in {"train", "all"}:
            results.append(self.train())
        return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare and train on the Walmart M5 dataset.")
    parser.add_argument("--data-dir", type=Path, required=True, help="Directory with M5 CSV files.")
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Directory for generated artifacts."
    )
    parser.add_argument(
        "--stage",
        choices=("prepare", "train", "all"),
        default="all",
        help="Pipeline stage to run.",
    )
    parser.add_argument("--horizon", type=int, default=28, help="Temporal holdout in days.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pipeline = M5Pipeline(args.data_dir, args.output_dir, args.horizon)
    for result in pipeline.run(args.stage):
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
