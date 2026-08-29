from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class CustomerSegmenter:
    requested_clusters: int = 4
    random_state: int = 42

    def run(self, frame: pd.DataFrame) -> dict:
        snapshot = frame["order_date"].max() + timedelta(days=1)
        rfm = frame.groupby("customer_id").agg(
            recency=(
                "order_date",
                lambda values: int((snapshot - values.max()).days),
            ),
            frequency=("order_id", "nunique"),
            monetary=("revenue", "sum"),
        )
        if len(rfm) < 2:
            raise ValueError("At least two entities are required for segmentation.")

        features = rfm[["recency", "frequency", "monetary"]]
        distinct_profiles = len(features.drop_duplicates())
        cluster_count = min(max(2, self.requested_clusters), len(rfm), distinct_profiles)
        if cluster_count < 2:
            raise ValueError(
                "At least two distinct entity profiles are required for segmentation."
            )
        model = make_pipeline(
            StandardScaler(),
            KMeans(
                n_clusters=cluster_count,
                random_state=self.random_state,
                n_init=10,
            ),
        )
        rfm["cluster"] = model.fit_predict(features)

        cluster_value = rfm.groupby("cluster")["monetary"].mean().sort_values()
        names = ["Emerging", "Core", "High Value", "Champions"]
        if cluster_count != 4:
            names = [f"Value Tier {index + 1}" for index in range(cluster_count)]
        label_by_cluster = {
            int(cluster): names[index]
            for index, cluster in enumerate(cluster_value.index)
        }
        rfm["segment"] = rfm["cluster"].map(label_by_cluster)

        summary = (
            rfm.groupby("segment", as_index=False)
            .agg(
                customers=("cluster", "size"),
                average_recency_days=("recency", "mean"),
                average_orders=("frequency", "mean"),
                total_revenue=("monetary", "sum"),
            )
            .sort_values("total_revenue", ascending=False)
        )
        return {
            "method": "RFM entity features standardized before K-Means",
            "cluster_count": cluster_count,
            "segments": [
                {
                    "name": row.segment,
                    "customers": int(row.customers),
                    "average_recency_days": round(
                        float(row.average_recency_days), 1
                    ),
                    "average_orders": round(float(row.average_orders), 1),
                    "total_revenue": round(float(row.total_revenue), 2),
                }
                for row in summary.itertuples(index=False)
            ],
            "customers": [
                {
                    "customer_id": str(customer_id),
                    "segment": row.segment,
                    "recency_days": int(row.recency),
                    "frequency": int(row.frequency),
                    "monetary": round(float(row.monetary), 2),
                }
                for customer_id, row in rfm.sort_values(
                    "monetary", ascending=False
                ).iterrows()
            ],
        }


def segment_customers(frame: pd.DataFrame, requested_clusters: int = 4) -> dict:
    return CustomerSegmenter(requested_clusters=requested_clusters).run(frame)
