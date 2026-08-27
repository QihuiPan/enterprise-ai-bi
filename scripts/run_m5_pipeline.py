from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from data_pipeline.m5 import prepare_m5_frame, write_prepared_m5
from ml.m5_forecasting import save_m5_model, train_m5_model


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
    args.output_dir.mkdir(parents=True, exist_ok=True)
    prepared_path = args.output_dir / "m5_store_category_daily.csv"

    if args.stage in {"prepare", "all"}:
        frame, summary = prepare_m5_frame(args.data_dir, verify_checksums=True)
        paths = write_prepared_m5(frame, summary, args.output_dir)
        print(json.dumps({key: str(value) for key, value in paths.items()}, indent=2))

    if args.stage in {"train", "all"}:
        if not prepared_path.is_file():
            raise FileNotFoundError(
                f"Prepared data does not exist: {prepared_path}. Run the prepare stage first."
            )
        frame = pd.read_csv(prepared_path, parse_dates=["order_date"])
        artifact, metrics, predictions = train_m5_model(frame, horizon=args.horizon)
        model_path = save_m5_model(artifact, args.output_dir / "m5_forecaster.joblib")
        metrics_path = args.output_dir / "m5_training_metrics.json"
        predictions_path = args.output_dir / "m5_holdout_predictions.csv"
        metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        predictions.to_csv(predictions_path, index=False)
        print(
            json.dumps(
                {
                    "model": str(model_path),
                    "metrics": str(metrics_path),
                    "predictions": str(predictions_path),
                    "result": metrics,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
