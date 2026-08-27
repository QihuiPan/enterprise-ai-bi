from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.services.analytics import sales_frame
from ml.anomaly_detection import detect_anomalies
from ml.forecasting import forecast_revenue
from ml.segmentation import segment_customers


def revenue_forecast(session: Session, horizon: int = 3) -> dict:
    return forecast_revenue(sales_frame(session), horizon=horizon)


def customer_segments(session: Session, clusters: int = 4) -> dict:
    return segment_customers(sales_frame(session), requested_clusters=clusters)


def sales_anomalies(session: Session, limit: int = 10) -> dict:
    return detect_anomalies(sales_frame(session), limit=limit)
