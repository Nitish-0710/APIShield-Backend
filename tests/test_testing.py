from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.api import ApiEndpoint
from app.models.test_result import TestResultRecord
from app.models.user import User


def test_adhoc_testing_success(
    authenticated_client: TestClient,
    auth_headers: dict,
    db_session: Session,
):
    """Ad-hoc testing executes request, evaluates assertions, and persists history record."""
    payload = {
        "url": "https://api.github.com/zen",
        "method": "GET",
        "expectedStatus": 200,
        "validationRule": "Practicality beats purity",
        "timeoutMs": 5000,
    }

    mock_resp_tuple = (
        200,
        {"content-type": "text/plain", "server": "GitHub.com"},
        "Practicality beats purity.",
        145.2,
    )

    with patch("app.services.test_service.execute_safe_request", return_value=mock_resp_tuple):
        resp = authenticated_client.post(
            "/api/v1/apis/adhoc/test",
            json=payload,
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is True
    assert data["outcome"] == "success"
    assert data["statusCode"] == 200
    assert data["expectedStatus"] == 200
    assert len(data["validations"]) >= 2
    assert data["validations"][0]["passed"] is True
    assert data["validations"][1]["passed"] is True

    # Check persistence in database
    record = db_session.scalar(select(TestResultRecord).where(TestResultRecord.id == data["id"]))
    assert record is not None
    assert record.api_id is None  # ad-hoc has no api_id
    assert record.passed is True


def test_adhoc_testing_assertion_failure(
    authenticated_client: TestClient,
    auth_headers: dict,
):
    """Ad-hoc testing returns passed=False when expected status code does not match."""
    payload = {
        "url": "https://api.example.com/status",
        "method": "GET",
        "expectedStatus": 200,
        "timeoutMs": 5000,
    }

    mock_resp_tuple = (
        503,
        {"content-type": "application/json"},
        '{"error": "Service Unavailable"}',
        210.5,
    )

    with patch("app.services.test_service.execute_safe_request", return_value=mock_resp_tuple):
        resp = authenticated_client.post(
            "/api/v1/apis/adhoc/test",
            json=payload,
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is False
    assert data["outcome"] == "failure"
    assert data["statusCode"] == 503
    assert data["validations"][0]["passed"] is False


def test_saved_api_testing_and_history(
    authenticated_client: TestClient,
    auth_headers: dict,
    db_session: Session,
):
    """Testing a saved API decrypts credentials, updates API telemetry, and logs history."""
    # 1. Create a saved API
    api_payload = {
        "name": "Weather Service",
        "url": "https://api.weather.com/v1/current",
        "method": "GET",
        "authType": "bearer",
        "secret": "weather-api-secret-12345",
        "expectedStatus": 200,
        "timeoutMs": 5000,
        "intervalSec": 60,
        "maxLatencyMs": 1000,
        "errorRateThreshold": 5.0,
        "expectedAvailability": 99.0,
        "riskThreshold": 70.0,
    }
    create_resp = authenticated_client.post(
        "/api/v1/apis",
        json=api_payload,
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    api_id = create_resp.json()["id"]

    mock_resp_tuple = (
        200,
        {"content-type": "application/json", "authorization": "Bearer weather-api-secret-12345"},
        '{"temp": 72}',
        120.0,
    )

    # 2. Run test on saved API
    with patch("app.services.test_service.execute_safe_request", return_value=mock_resp_tuple) as mock_exec:
        test_resp = authenticated_client.post(
            f"/api/v1/apis/{api_id}/test",
            headers=auth_headers,
        )

    assert test_resp.status_code == 200
    test_data = test_resp.json()
    assert test_data["passed"] is True
    assert test_data["apiId"] == api_id

    # Verify that decrypted secret was supplied in Authorization header during request execution
    mock_exec.assert_called_once()
    called_headers = mock_exec.call_args[1]["headers"]
    assert called_headers["Authorization"] == "Bearer weather-api-secret-12345"

    # Verify sensitive Authorization header is MASKED in returned response and DB
    hdr_dict = {h["key"].lower(): h["value"] for h in test_data["headers"]}
    assert hdr_dict["authorization"] == "********"

    # 3. Verify API endpoint telemetry was updated
    api = db_session.scalar(select(ApiEndpoint).where(ApiEndpoint.id == api_id))
    assert api.last_status_code == 200
    assert api.last_latency_ms == 120.0
    assert api.health == "healthy"
    assert api.last_checked_at is not None

    # 4. Retrieve test history
    hist_resp = authenticated_client.get(f"/api/v1/apis/{api_id}/history")
    assert hist_resp.status_code == 200
    history = hist_resp.json()
    assert len(history) == 1
    assert history[0]["id"] == test_data["id"]
    assert history[0]["apiId"] == api_id
    assert history[0]["passed"] is True


def test_cross_user_test_and_history_forbidden(
    authenticated_client: TestClient,
    auth_headers: dict,
    db_session: Session,
    other_user: User,
):
    """Running test or retrieving history for another user's API returns 404."""
    other_api = ApiEndpoint(
        user_id=other_user.id,
        name="Private Financial Feed",
        url="https://api.finance.com/v1",
        method="GET",
        query_params=[],
        headers=[],
        auth_type="none",
        expected_status=200,
    )
    db_session.add(other_api)
    db_session.commit()

    # Test attempt returns 404
    test_resp = authenticated_client.post(
        f"/api/v1/apis/{other_api.id}/test",
        headers=auth_headers,
    )
    assert test_resp.status_code == 404

    # History attempt returns 404
    hist_resp = authenticated_client.get(f"/api/v1/apis/{other_api.id}/history")
    assert hist_resp.status_code == 404
