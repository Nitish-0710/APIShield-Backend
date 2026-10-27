import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.api import ApiEndpoint
from app.models.ml import PredictionRecord
from app.models.user import User


@pytest.fixture
def sample_prediction(db_session: Session, test_user: User, test_api: ApiEndpoint) -> PredictionRecord:
    rec = PredictionRecord(
        api_id=test_api.id,
        user_id=test_user.id,
        risk_score=78.5,
        risk_level="high",
        prediction=1,
        provenance="trained_model",
        model_version="test_v1",
        features={
            "avg_latency_ms": 600.0,
            "p95_latency_ms": 1100.0,
            "error_rate": 20.0,
            "recent_consecutive_failures": 2.0,
        },
        explanation={
            "method": "shap_tree_attribution",
            "is_fallback": False,
            "top_contributing_features": [],
        },
    )
    db_session.add(rec)
    db_session.commit()
    db_session.refresh(rec)
    return rec


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


def test_ml_experiments_unauthenticated(client: TestClient):
    resp = client.get("/api/v1/ml/experiments")
    assert resp.status_code == 401


def test_ml_experiments_authenticated(authenticated_client: TestClient):
    resp = authenticated_client.get("/api/v1/ml/experiments")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data
    assert isinstance(data["items"], list)


def test_ml_experiment_run_not_found(authenticated_client: TestClient):
    resp = authenticated_client.get("/api/v1/ml/experiments/non_existent_run_999")
    assert resp.status_code == 404


def test_ml_models_authenticated(authenticated_client: TestClient):
    resp = authenticated_client.get("/api/v1/ml/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data


def test_ml_models_serving(authenticated_client: TestClient):
    resp = authenticated_client.get("/api/v1/ml/models/serving")
    assert resp.status_code == 200
    data = resp.json()
    assert "model_name" in data
    assert "provenance" in data
    assert "is_loaded" in data
    assert "health_status" in data
    assert "expected_features" in data
    assert len(data["expected_features"]) == 15


def test_ml_fairness_reports(authenticated_client: TestClient):
    resp = authenticated_client.get("/api/v1/ml/fairness-reports")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "evaluated"
    assert data["is_synthetic_demonstration"] is True
    assert "demographic_parity_ratio" in data["summary"]
    assert "disclaimer" in data


def test_prediction_explanation_endpoint_shap_and_lime(
    authenticated_client: TestClient,
    sample_prediction: PredictionRecord,
):
    # Test default/shap explanation
    resp_shap = authenticated_client.get(f"/api/v1/predictions/{sample_prediction.id}/explanation?method=shap")
    assert resp_shap.status_code == 200
    data_shap = resp_shap.json()
    assert data_shap["prediction_id"] == sample_prediction.id
    assert "explanation" in data_shap
    assert "method" in data_shap["explanation"]

    # Test LIME explanation
    resp_lime = authenticated_client.get(f"/api/v1/predictions/{sample_prediction.id}/explanation?method=lime")
    assert resp_lime.status_code == 200
    data_lime = resp_lime.json()
    assert data_lime["requested_method"] == "lime"
    assert "explanation" in data_lime

    # Test 404 for unknown prediction ID
    resp_404 = authenticated_client.get("/api/v1/predictions/invalid_pred_id/explanation")
    assert resp_404.status_code == 404


def test_prediction_explanation_unauthorized_access(
    client: TestClient,
    sample_prediction: PredictionRecord,
):
    resp = client.get(f"/api/v1/predictions/{sample_prediction.id}/explanation")
    assert resp.status_code == 401
