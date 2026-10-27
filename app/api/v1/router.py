from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    health,
    apis,
    monitoring,
    predictions,
    diagnostics,
    alerts,
    reports,
    settings,
    ml,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(health.router)
api_router.include_router(apis.router)
api_router.include_router(monitoring.router)
api_router.include_router(predictions.router)
api_router.include_router(diagnostics.router)
api_router.include_router(alerts.router)
api_router.include_router(reports.router)
api_router.include_router(settings.router)
api_router.include_router(ml.router)

