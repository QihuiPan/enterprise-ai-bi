from fastapi import APIRouter

from backend.app.api import analytics, dashboard, data, insights, machine_learning, reports

api_router = APIRouter()
api_router.include_router(data.router)
api_router.include_router(analytics.router)
api_router.include_router(dashboard.router)
api_router.include_router(machine_learning.router)
api_router.include_router(insights.router)
api_router.include_router(reports.router)
