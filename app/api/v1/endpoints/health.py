from datetime import datetime, timezone
from fastapi import APIRouter, Response, status
from app.db.session import check_db_ready

router = APIRouter(tags=["Health"])


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/health/live", summary="Process Liveness Check")
def health_live():
    """
    Indicates whether the application process is running and responding.
    Independent of external database availability.
    """
    return {
        "status": "live",
        "timestamp": utcnow_iso(),
    }


@router.get("/health/ready", summary="System Readiness Check")
def health_ready(response: Response):
    """
    Verifies that required runtime dependencies (database) are operational.
    Returns HTTP 200 when ready, HTTP 503 when degraded or disconnected.
    Never exposes credentials or internal connection strings.
    """
    db_ok = check_db_ready()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "database": "disconnected",
            "timestamp": utcnow_iso(),
        }

    return {
        "status": "ready",
        "database": "connected",
        "timestamp": utcnow_iso(),
    }
