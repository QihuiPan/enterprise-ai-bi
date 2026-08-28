from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy.orm import Session

from backend.app.services.analytics import sales_frame
from ml.anomaly_detection import SalesAnomalyDetector
from ml.forecasting import RevenueForecaster
from ml.segmentation import CustomerSegmenter


@dataclass(frozen=True)
class MachineLearningService:
    """ML facade over one validated, request-scoped sales snapshot."""

    frame: pd.DataFrame

    @classmethod
    def from_session(cls, session: Session) -> MachineLearningService:
        return cls(sales_frame(session))

    def revenue_forecast(self, horizon: int = 3) -> dict:
        return RevenueForecaster(horizon=horizon).run(self.frame)

    def customer_segments(self, clusters: int = 4) -> dict:
        return CustomerSegmenter(requested_clusters=clusters).run(self.frame)

    def sales_anomalies(self, limit: int = 10) -> dict:
        return SalesAnomalyDetector(limit=limit).run(self.frame)


def revenue_forecast(session: Session, horizon: int = 3) -> dict:
    return MachineLearningService.from_session(session).revenue_forecast(horizon)


def customer_segments(session: Session, clusters: int = 4) -> dict:
    return MachineLearningService.from_session(session).customer_segments(clusters)


def sales_anomalies(session: Session, limit: int = 10) -> dict:
    return MachineLearningService.from_session(session).sales_anomalies(limit)
