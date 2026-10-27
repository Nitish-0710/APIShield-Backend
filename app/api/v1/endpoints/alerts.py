from typing import Optional
from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, CsrfProtect
from app.schemas.ml import AlertListResponse, AlertResponse, AlertStatusUpdate
from app.services.alert_service import AlertService

router = APIRouter(prefix="/alerts", tags=["Alerts"])
alert_service = AlertService()


@router.get(
    "",
    response_model=AlertListResponse,
    status_code=status.HTTP_200_OK,
    summary="List persistent alerts for authenticated user",
)
def list_alerts(
    db: DbSession,
    current_user: CurrentUser,
    status: Optional[str] = Query(None, description="Filter by status: open, acknowledged, resolved"),
    api_id: Optional[str] = Query(None, description="Filter by API ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AlertListResponse:
    total, items = alert_service.list_alerts(
        db=db,
        user_id=current_user.id,
        status=status,
        api_id=api_id,
        limit=limit,
        offset=offset,
    )
    return AlertListResponse(
        total=total,
        items=[AlertResponse.model_validate(a) for a in items],
    )


@router.patch(
    "/{id}/status",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Update alert lifecycle status",
)
def update_alert_status(
    id: str,
    payload: AlertStatusUpdate,
    db: DbSession,
    current_user: CurrentUser,
    csrf: CsrfProtect,
) -> AlertResponse:
    updated = alert_service.update_alert_status(
        db=db,
        alert_id=id,
        user_id=current_user.id,
        new_status=payload.status,
    )
    return AlertResponse.model_validate(updated)
