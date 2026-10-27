from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.ml import DiagnosticReport
from app.services.diagnostic_service import DiagnosticService

router = APIRouter(prefix="/diagnostics", tags=["Diagnostics & Root-Cause"])
diagnostic_service = DiagnosticService()


@router.get(
    "/{api_id}",
    response_model=DiagnosticReport,
    status_code=status.HTTP_200_OK,
    summary="Get root-cause diagnostics and recommendations for an API",
)
def get_api_diagnostics(
    api_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> DiagnosticReport:
    """Analyzes telemetry for verified facts, rule inferences, and concrete recommendations."""
    report = diagnostic_service.get_api_diagnostics(
        db=db,
        api_id=api_id,
        user_id=current_user.id,
    )
    return DiagnosticReport.model_validate(report)
