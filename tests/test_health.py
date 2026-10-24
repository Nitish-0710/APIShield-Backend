from unittest.mock import patch
from fastapi.testclient import TestClient


def test_liveness_succeeds(client: TestClient):
    """Liveness check returns 200 and indicates process is live."""
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "live"
    assert "timestamp" in data


def test_readiness_succeeds_when_db_healthy(client: TestClient):
    """Readiness returns 200 when database connectivity is verified."""
    with patch("app.api.v1.endpoints.health.check_db_ready", return_value=True):
        response = client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"
        assert "timestamp" in data


def test_readiness_fails_when_db_down(client: TestClient):
    """Readiness returns 503 without leaking stack traces when DB is unavailable."""
    with patch("app.api.v1.endpoints.health.check_db_ready", return_value=False):
        response = client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["database"] == "disconnected"
        assert "password" not in response.text.lower()
        assert "traceback" not in response.text.lower()


def test_liveness_unaffected_by_db_failure(client: TestClient):
    """Liveness must stay operational even if the database is completely down."""
    with patch("app.api.v1.endpoints.health.check_db_ready", return_value=False):
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "live"
