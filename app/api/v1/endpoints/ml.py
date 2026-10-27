import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CsrfProtect, CurrentUser, DbSession
from app.core.errors import AppException
from app.ml.fairness import generate_synthetic_fairness_report
from app.ml.features import FEATURE_NAMES
from app.ml.mlflow_tracker import MLflowTracker
from app.ml.pipeline import train_and_log_pipeline
from app.schemas.ml import (
    ExperimentListResponse,
    ExperimentRunSchema,
    FairnessReportResponse,
    ModelListResponse,
    ModelVersionSchema,
    ServingModelResponse,
    TrainingRunRequest,
    TrainingRunResponse,
)
from app.services.prediction_service import PredictionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ml", tags=["MLOps & Model Management"])
tracker = MLflowTracker()
prediction_service = PredictionService()


@router.get(
    "/experiments",
    response_model=ExperimentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List training experiment runs, parameters, and metrics",
)
def list_experiments(
    current_user: CurrentUser,
    limit: int = Query(50, ge=1, le=200),
) -> ExperimentListResponse:
    runs = tracker.list_experiments(limit=limit)
    items = []
    for r in runs:
        items.append(
            ExperimentRunSchema(
                run_id=r.get("run_id", "unknown"),
                experiment_name=r.get("experiment_name", tracker.experiment_name),
                model_version=r.get("model_version"),
                model_type=r.get("model_type"),
                params=r.get("params", {}),
                metrics=r.get("metrics", {}),
                is_promoted=r.get("is_promoted", False),
                promotion_status=r.get("promotion_status"),
                backend=r.get("backend", "mlflow_native"),
                timestamp=r.get("timestamp"),
                status=r.get("status", "FINISHED"),
                artifact_uri=r.get("artifact_uri"),
            )
        )
    return ExperimentListResponse(total=len(items), items=items)


@router.get(
    "/experiments/{run_id}",
    response_model=ExperimentRunSchema,
    status_code=status.HTTP_200_OK,
    summary="Get details of a specific training run by run ID",
)
def get_experiment_run(
    run_id: str,
    current_user: CurrentUser,
) -> ExperimentRunSchema:
    r = tracker.get_run(run_id)
    if not r:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            message=f"Training experiment run '{run_id}' not found.",
        )
    return ExperimentRunSchema(
        run_id=r.get("run_id", run_id),
        experiment_name=r.get("experiment_name", tracker.experiment_name),
        model_version=r.get("model_version"),
        model_type=r.get("model_type"),
        params=r.get("params", {}),
        metrics=r.get("metrics", {}),
        is_promoted=r.get("is_promoted", False),
        promotion_status=r.get("promotion_status"),
        backend=r.get("backend", "mlflow_native"),
        timestamp=r.get("timestamp"),
        status=r.get("status", "FINISHED"),
        artifact_uri=r.get("artifact_uri"),
    )


@router.get(
    "/models",
    response_model=ModelListResponse,
    status_code=status.HTTP_200_OK,
    summary="List registered models and model versions",
)
def list_models(
    current_user: CurrentUser,
    model_name: str | None = Query(None, description="Optional filter by model name"),
) -> ModelListResponse:
    versions = tracker.list_model_versions(model_name=model_name)
    items = []
    for v in versions:
        items.append(
            ModelVersionSchema(
                model_name=v.get("model_name", MLflowTracker.DEFAULT_REGISTERED_MODEL),
                version=v.get("version", "1"),
                status=v.get("status", "READY"),
                stage=v.get("stage"),
                aliases=v.get("aliases", []),
                run_id=v.get("run_id"),
                created_at=v.get("created_at"),
                metrics=v.get("metrics"),
            )
        )
    return ModelListResponse(total=len(items), items=items)


@router.get(
    "/models/{model_name}/versions",
    response_model=ModelListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all versions of a specific registered model",
)
def list_model_versions_by_name(
    model_name: str,
    current_user: CurrentUser,
) -> ModelListResponse:
    versions = tracker.list_model_versions(model_name=model_name)
    items = [
        ModelVersionSchema(
            model_name=v.get("model_name", model_name),
            version=v.get("version", "1"),
            status=v.get("status", "READY"),
            stage=v.get("stage"),
            aliases=v.get("aliases", []),
            run_id=v.get("run_id"),
            created_at=v.get("created_at"),
            metrics=v.get("metrics"),
        )
        for v in versions
    ]
    return ModelListResponse(total=len(items), items=items)


@router.get(
    "/models/serving",
    response_model=ServingModelResponse,
    status_code=status.HTTP_200_OK,
    summary="Report the active model actually serving prediction inferences and its health",
)
def get_serving_model_status(
    current_user: CurrentUser,
) -> ServingModelResponse:
    prediction_service._ensure_model_loaded()

    artifact_file = Path("artifacts/models/latest_model.joblib")
    meta_file = Path("artifacts/models/latest_model_meta.json")

    artifact_exists = artifact_file.exists()
    meta: dict[str, Any] = {}
    if meta_file.exists():
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            pass

    is_loaded = prediction_service.cached_model is not None
    provenance = "trained_model" if is_loaded else "rules_baseline"
    model_type = (
        type(prediction_service.cached_model).__name__
        if is_loaded
        else meta.get("model_type", "RuleBasedBaseline")
    )
    health = "healthy" if is_loaded else ("standby_rules_fallback" if artifact_exists else "no_artifact")

    return ServingModelResponse(
        model_name=MLflowTracker.DEFAULT_REGISTERED_MODEL,
        model_version=prediction_service.model_version or meta.get("model_version"),
        model_type=model_type,
        provenance=provenance,
        is_loaded=is_loaded,
        artifact_exists=artifact_exists,
        expected_features=prediction_service.expected_feature_names or FEATURE_NAMES,
        candidate_metrics=meta.get("candidate_metrics"),
        trained_at=meta.get("trained_at"),
        health_status=health,
    )


@router.post(
    "/training-runs",
    response_model=TrainingRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger model training, evaluation, and promotion pipeline",
)
def trigger_training_run(
    req: TrainingRunRequest,
    current_user: CurrentUser,
    csrf: CsrfProtect,
) -> TrainingRunResponse:
    dataset_path = req.dataset_path or "data/telemetry_dataset.json"
    result = train_and_log_pipeline(dataset_path=dataset_path)

    if not result.get("success"):
        return TrainingRunResponse(
            success=False,
            status=result.get("status", "error"),
            reason=result.get("reason", "Training pipeline execution failed."),
        )

    return TrainingRunResponse(
        success=True,
        status=result.get("status", "promoted"),
        model_version=result.get("model_version"),
        model_type=result.get("model_type"),
        is_promoted=result.get("is_promoted"),
        candidate_metrics=result.get("candidate_metrics"),
        baseline_metrics=result.get("baseline_metrics"),
    )


@router.get(
    "/fairness-reports",
    response_model=FairnessReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve model fairness and demographic parity report across client tiers",
)
def get_fairness_report(
    current_user: CurrentUser,
) -> FairnessReportResponse:
    report = generate_synthetic_fairness_report()
    return FairnessReportResponse.model_validate(report)
