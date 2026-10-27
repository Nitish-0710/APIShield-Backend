from typing import Optional
from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.ml import MonitoringReportSummary
from app.services.report_service import ReportService

router = APIRouter(prefix="/reports", tags=["Reports & Exports"])
report_service = ReportService()


@router.get(
    "/summary",
    response_model=MonitoringReportSummary,
    status_code=status.HTTP_200_OK,
    summary="Get monitoring and health summary report for an API",
)
def get_monitoring_summary(
    apiId: str = Query(..., description="API ID to report on"),
    range: str = Query("24h", pattern="^(1h|6h|24h|7d)$", description="Time range"),
    db: DbSession = None,
    current_user: CurrentUser = None,
) -> MonitoringReportSummary:
    summary = report_service.get_monitoring_summary(
        db=db,
        api_id=apiId,
        user_id=current_user.id,
        time_range=range,
    )
    return MonitoringReportSummary.model_validate(summary)


@router.get(
    "/export-csv",
    status_code=status.HTTP_200_OK,
    summary="Export sanitized telemetry records as CSV",
)
def export_telemetry_csv(
    apiId: str = Query(..., description="API ID to export"),
    limit: int = Query(1000, ge=1, le=5000),
    db: DbSession = None,
    current_user: CurrentUser = None,
) -> Response:
    csv_data = report_service.export_telemetry_csv(
        db=db,
        api_id=apiId,
        user_id=current_user.id,
        limit=limit,
    )
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=apishield_telemetry_{apiId}.csv",
        },
    )
