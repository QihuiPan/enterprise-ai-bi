from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from data_pipeline.validation import validate_and_transform


def build_demo_frame(rows: int = 720, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    end = pd.Timestamp("2026-06-30")
    start = end - timedelta(days=729)
    dates = start + pd.to_timedelta(rng.integers(0, 730, rows), unit="D")

    product_catalog = {
        "Analytics": [("Insight Pro", 249.0), ("Metric Studio", 169.0)],
        "Automation": [("Flow Engine", 329.0), ("Task Pilot", 119.0)],
        "Security": [("Shield Cloud", 289.0), ("Access Guard", 199.0)],
    }
    categories = rng.choice(list(product_catalog), rows, p=[0.42, 0.34, 0.24])
    chosen = [product_catalog[category][rng.integers(0, 2)] for category in categories]
    products = [item[0] for item in chosen]
    base_prices = np.array([item[1] for item in chosen])

    quantities = rng.integers(1, 7, rows)
    recent_drop = dates >= end - timedelta(days=30)
    quantities[recent_drop] = np.maximum(1, np.floor(quantities[recent_drop] * 0.55)).astype(int)

    frame = pd.DataFrame(
        {
            "order_id": [f"ORD-{index + 1:05d}" for index in range(rows)],
            "order_date": dates,
            "customer_id": [f"CUST-{value:03d}" for value in rng.integers(1, 121, rows)],
            "region": rng.choice(["North", "South", "East", "West"], rows),
            "category": categories,
            "product": products,
            "quantity": quantities,
            "unit_price": (base_prices * rng.normal(1.0, 0.04, rows)).round(2),
            "discount": rng.choice([0.0, 0.05, 0.1, 0.15], rows, p=[0.5, 0.25, 0.2, 0.05]),
        }
    )
    return validate_and_transform(frame)
