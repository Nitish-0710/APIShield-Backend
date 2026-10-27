from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.api import ApiEndpoint
from app.models.test_result import TestResultRecord
from app.models.user import User


@pytest.fixture
def test_api(db_session: Session, test_user: User) -> ApiEndpoint:
    api = ApiEndpoint(
        user_id=test_user.id,
        name="Payment Gateway Service",
        url="https://api.stripe.com/v1/health",
        method="GET",
        expected_status=200,
        monitoring=True,
    )
    db_session.add(api)
    db_session.commit()
    db_session.refresh(api)
    return api


@pytest.fixture
def other_user_api(db_session: Session, other_user: User) -> ApiEndpoint:
    api = ApiEndpoint(
        user_id=other_user.id,
        name="Private Internal Service",
        url="https://api.github.com/zen",
        method="GET",
        expected_status=200,
        monitoring=True,
    )
    db_session.add(api)
    db_session.commit()
    db_session.refresh(api)
    return api


def test_predict_endpoint_unauthenticated(client: TestClient, test_api: ApiEndpoint):
    """Verify that unauthenticated prediction requests return 401."""
    resp = client.post(f"/api/v1/predictions/{test_api.id}/predict")
    assert resp.status_code == 401


def test_predict_endpoint_success_and_provenance(
    authenticated_client: TestClient,
    auth_headers: dict,
    test_api: ApiEndpoint,
    db_session: Session,
):
    """Verify prediction generation returns valid risk metrics and explicit rules_baseline provenance."""
    # Add dummy test telemetry
    for _ in range(5):
        tr = TestResultRecord(
            api_id=test_api.id,
            user_id=test_api.user_id,
            passed=True,
            outcome="success",
            status_code=200,
            expected_status=200,
            latency_ms=120.0,
            tested_at=datetime.now(timezone.utc),
        )
        db_session.add(tr)
    db_session.commit()

    resp = authenticated_client.post(
        f"/api/v1/predictions/{test_api.id}/predict",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["api_id"] == test_api.id
    assert "risk_score" in data
    assert "risk_level" in data
    assert data["provenance"] in ("rules_baseline", "trained_model")
    assert "features" in data
    assert "explanation" in data
    assert data["inference_duration_ms"] is not None


def test_predict_endpoint_cross_user_forbidden(
    authenticated_client: TestClient,
    auth_headers: dict,
    other_user_api: ApiEndpoint,
):
    """Verify predicting for another user's API returns 404 (ownership check)."""
    resp = authenticated_client.post(
        f"/api/v1/predictions/{other_user_api.id}/predict",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_list_prediction_history_scoped(
    authenticated_client: TestClient,
    auth_headers: dict,
    test_api: ApiEndpoint,
):
    """Verify prediction history endpoint lists records scoped to the user."""
    # Generate prediction first
    authenticated_client.post(
        f"/api/v1/predictions/{test_api.id}/predict",
        headers=auth_headers,
    )

    resp = authenticated_client.get(f"/api/v1/predictions?api_id={test_api.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["api_id"] == test_api.id


def test_diagnostics_endpoint_analysis(
    authenticated_client: TestClient,
    test_api: ApiEndpoint,
    db_session: Session,
):
    """Verify diagnostic endpoint examines telemetry and returns structured findings."""
    # Add failing telemetry
    for _ in range(3):
        tr = TestResultRecord(
            api_id=test_api.id,
            user_id=test_api.user_id,
            passed=False,
            outcome="failure",
            status_code=503,
            expected_status=200,
            latency_ms=2500.0,
            tested_at=datetime.now(timezone.utc),
        )
        db_session.add(tr)
    db_session.commit()

    resp = authenticated_client.get(f"/api/v1/diagnostics/{test_api.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["api_id"] == test_api.id
    assert data["overall_status"] in ("critical", "degraded")
    assert len(data["findings"]) > 0
    categories = [f["category"] for f in data["findings"]]
    assert "5xx_server_errors" in categories or "consecutive_failures" in categories


def test_promoted_model_loading_and_inference(
    authenticated_client: TestClient,
    auth_headers: dict,
    test_api: ApiEndpoint,
):
    """Verify that the promoted model is loaded and used for inference when valid."""
    from app.services.prediction_service import PredictionService

    # Prediction service should load the promoted model
    service = PredictionService()
    assert service.cached_model is not None
    assert service.model_version is not None
    assert service.model_version.startswith("model_v")
    assert len(service.expected_feature_names) == 15

    resp = authenticated_client.post(
        f"/api/v1/predictions/{test_api.id}/predict",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["provenance"] == "trained_model"
    assert data["model_version"] == service.model_version
    assert data["prediction"] in (0, 1)
    assert 0.0 <= data["risk_score"] <= 100.0


def test_prediction_fallback_missing_or_corrupt_artifact(tmp_path, db_session, test_user, test_api):
    """Verify fallback to rules_baseline when artifact is missing or corrupt."""
    import json
    from app.services.prediction_service import PredictionService

    # 1. Missing artifact
    empty_dir = tmp_path / "empty_models"
    empty_dir.mkdir(parents=True, exist_ok=True)
    svc_empty = PredictionService(artifact_dir=str(empty_dir))
    record_empty = svc_empty.predict_api_risk(db_session, test_api.id, test_user.id)
    assert record_empty.provenance == "rules_baseline"
    assert record_empty.model_version is None

    # 2. Corrupt model artifact
    corrupt_dir = tmp_path / "corrupt_models"
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    (corrupt_dir / "latest_model.joblib").write_bytes(b"INVALID_PICKLE_HEADER_123")
    with open(corrupt_dir / "latest_model_meta.json", "w") as f:
        json.dump({"is_promoted": True, "model_version": "corrupt_v1"}, f)

    svc_corrupt = PredictionService(artifact_dir=str(corrupt_dir))
    record_corrupt = svc_corrupt.predict_api_risk(db_session, test_api.id, test_user.id)
    assert record_corrupt.provenance == "rules_baseline"
    assert record_corrupt.model_version is None


def test_prediction_fallback_incompatible_metadata_and_ordering(tmp_path, db_session, test_user, test_api):
    """Verify fallback when metadata marks model unpromoted or feature dimension mismatches."""
    import json
    import joblib
    from app.services.prediction_service import PredictionService
    from sklearn.ensemble import RandomForestClassifier

    model_dir = tmp_path / "incompatible_models"
    model_dir.mkdir(parents=True, exist_ok=True)

    # Train dummy model with 15 features
    clf = RandomForestClassifier(n_estimators=5, random_state=42)
    clf.fit([[0.0] * 15] * 4, [0, 1, 0, 1])
    joblib.dump(clf, model_dir / "latest_model.joblib")

    # 1. is_promoted = False
    with open(model_dir / "latest_model_meta.json", "w") as f:
        json.dump({
            "is_promoted": False,
            "model_version": "unpromoted_v1",
            "feature_names": [f"f_{i}" for i in range(15)]
        }, f)

    svc_unpromoted = PredictionService(artifact_dir=str(model_dir))
    rec1 = svc_unpromoted.predict_api_risk(db_session, test_api.id, test_user.id)
    assert rec1.provenance == "rules_baseline"
    assert rec1.model_version is None

    # 2. Dimension mismatch (model expects 15, metadata specifies 3)
    with open(model_dir / "latest_model_meta.json", "w") as f:
        json.dump({
            "is_promoted": True,
            "model_version": "mismatch_v1",
            "feature_names": ["f1", "f2", "f3"]
        }, f)

    svc_mismatch = PredictionService(artifact_dir=str(model_dir))
    rec2 = svc_mismatch.predict_api_risk(db_session, test_api.id, test_user.id)
    assert rec2.provenance == "rules_baseline"
    assert rec2.model_version is None
