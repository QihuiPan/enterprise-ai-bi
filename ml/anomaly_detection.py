from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ANOMALY_FEATURES = ["revenue", "quantity", "unit_price", "discount"]


@dataclass(frozen=True)
class SalesAnomalyDetector:
    limit: int = 10
    contamination: float = 0.05
    random_state: int = 42

    def run(self, frame: pd.DataFrame) -> dict:
        if len(frame) < 20:
            raise ValueError("At least 20 transactions are required for anomaly detection.")
        if not 1 <= self.limit <= 50:
            raise ValueError("Anomaly limit must be between 1 and 50.")
        if not 0 < self.contamination <= 0.5:
            raise ValueError("Contamination must be greater than 0 and at most 0.5.")

        model = make_pipeline(
            StandardScaler(),
            IsolationForest(
                contamination=self.contamination,
                random_state=self.random_state,
            ),
        )
        features = frame[ANOMALY_FEATURES]
        predictions = model.fit_predict(features)
        scores = -model.decision_function(features)

        ranked = frame.assign(anomaly=predictions == -1, anomaly_score=scores)
        anomalous = ranked[ranked["anomaly"]].nlargest(
            self.limit, "anomaly_score"
        )
        return {
            "method": "Isolation Forest on standardized transaction features",
            "records_evaluated": len(frame),
            "anomaly_count": int((predictions == -1).sum()),
            "anomalies": [
                {
                    "order_id": row.order_id,
                    "order_date": row.order_date.date().isoformat(),
                    "customer_id": row.customer_id,
                    "region": row.region,
                    "category": row.category,
                    "revenue": round(float(row.revenue), 2),
                    "score": round(float(row.anomaly_score), 4),
                }
                for row in anomalous.itertuples(index=False)
            ],
        }


def detect_anomalies(frame: pd.DataFrame, limit: int = 10) -> dict:
    return SalesAnomalyDetector(limit=limit).run(frame)
