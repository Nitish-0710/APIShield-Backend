from typing import Optional
from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, CsrfProtect
from app.core.errors import AppException
from app.models.ml import PredictionRecord
from app.schemas.ml import PredictionHistoryResponse, PredictionResponse
from app.services.prediction_service import PredictionService

router = APIRouter(prefix="/predictions", tags=["Predictions & Inference"])
prediction_service = PredictionService()


@router.post(
    "/{api_id}/predict",
    response_model=PredictionResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate API failure risk prediction using ML or baseline provenance",
)
def predict_api_failure(
    api_id: str,
    db: DbSession,
    current_user: CurrentUser,
    csrf: CsrfProtect,
    is_demo: bool = Query(False, description="Explicitly enable demo mode if desired"),
    explain_method: str = Query("shap", pattern="^(shap|lime|heuristic)$", description="Explainability method"),
) -> PredictionResponse:
    """Runs prediction inference for an API endpoint owned by the authenticated user."""
    record = prediction_service.predict_api_risk(
        db=db,
        api_id=api_id,
        user_id=current_user.id,
        is_demo=is_demo,
        explain_method=explain_method,
    )
    return PredictionResponse.model_validate(record)


@router.get(
    "",
    response_model=PredictionHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="List paginated prediction history for authenticated user",
)
def list_predictions(
    db: DbSession,
    current_user: CurrentUser,
    api_id: Optional[str] = Query(None, description="Filter by API ID"),
    provenance: Optional[str] = Query(None, description="Filter by provenance: trained_model, rules_baseline, demo"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PredictionHistoryResponse:
    total, items = prediction_service.list_prediction_history(
        db=db,
        user_id=current_user.id,
        api_id=api_id,
        provenance=provenance,
        limit=limit,
        offset=offset,
    )
    return PredictionHistoryResponse(
        total=total,
        items=[PredictionResponse.model_validate(r) for r in items],
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{id}",
    response_model=PredictionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single prediction record by ID",
)
def get_prediction_by_id(
    id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> PredictionResponse:
    record = (
        db.query(PredictionRecord)
        .filter(PredictionRecord.id == id, PredictionRecord.user_id == current_user.id)
        .first()
    )
    if not record:
        raise AppException(status_code=404, code="NOT_FOUND", message="Prediction record not found")
    return PredictionResponse.model_validate(record)


@router.get(
    "/{id}/explanation",
    status_code=status.HTTP_200_OK,
    summary="Get dynamic SHAP or LIME explanation for an existing prediction",
)
def get_prediction_explanation(
    id: str,
    db: DbSession,
    current_user: CurrentUser,
    method: str = Query("shap", pattern="^(shap|lime|heuristic)$", description="Explainability method"),
):
    record = (
        db.query(PredictionRecord)
        .filter(PredictionRecord.id == id, PredictionRecord.user_id == current_user.id)
        .first()
    )
    if not record:
        raise AppException(status_code=404, code="NOT_FOUND", message="Prediction record not found")

    features = record.features or {}
    provenance = record.provenance
    risk_score = record.risk_score

    # Compute explanation with requested method
    prediction_service._ensure_model_loaded()
    explanation = prediction_service.explainer.explain(
        features=features,
        risk_score=risk_score,
        provenance=provenance,
        feature_names=prediction_service.expected_feature_names,
        method=method,
    )
    return {
        "prediction_id": record.id,
        "api_id": record.api_id,
        "risk_score": risk_score,
        "provenance": provenance,
        "requested_method": method,
        "explanation": explanation,
    }
