from __future__ import annotations

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


def detect_anomalies(frame: pd.DataFrame, limit: int = 10) -> dict:
    if len(frame) < 20:
        raise ValueError("At least 20 transactions are required for anomaly detection.")
    if not 1 <= limit <= 50:
        raise ValueError("Anomaly limit must be between 1 and 50.")

    features = frame[["revenue", "quantity", "unit_price", "discount"]]
    scaled = StandardScaler().fit_transform(features)
    model = IsolationForest(contamination=0.05, random_state=42)
    predictions = model.fit_predict(scaled)
    scores = -model.decision_function(scaled)

    ranked = frame.assign(anomaly=predictions == -1, anomaly_score=scores)
    anomalous = ranked[ranked["anomaly"]].nlargest(limit, "anomaly_score")
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
