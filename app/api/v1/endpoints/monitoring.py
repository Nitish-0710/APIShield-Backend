from typing import List, Optional
from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.monitoring import MetricPoint, TimeRange
from app.services.metrics_service import MetricsService

router = APIRouter(prefix="/monitoring", tags=["Monitoring & Metrics"])


@router.get(
    "/metrics",
    response_model=List[MetricPoint],
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated time-series metrics for API monitoring",
)
def get_metrics(
    db: DbSession,
    current_user: CurrentUser,
    apiId: Optional[str] = Query(default=None, description="Target API ID, or omit/'all' for user-wide aggregate"),
    api_id: Optional[str] = Query(default=None, description="Snake_case alias for apiId"),
    range: TimeRange = Query(default="24h", description="Time range: 1h, 6h, 24h, 7d"),
) -> List[MetricPoint]:
    """Retrieve time-series monitoring metrics for the authenticated user.

    Supports filtering by specific API or aggregating all APIs owned by the user.
    Enforces user ownership, authentications, and handles empty datasets cleanly.
    """
    target_api_id = apiId if apiId is not None else api_id
    return MetricsService.get_metrics(
        db=db,
        user=current_user,
        api_id=target_api_id,
        time_range=range,
    )
