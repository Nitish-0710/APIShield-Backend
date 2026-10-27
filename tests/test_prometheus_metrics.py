import pytest
from fastapi.testclient import TestClient

from app.core.metrics import normalize_endpoint


def test_endpoint_normalization_prevents_cardinality_explosion():
    """Verify UUIDs in paths are replaced with {id} placeholder."""
    path = "/api/v1/apis/12345678-1234-5678-1234-567812345678/test"
    normalized = normalize_endpoint(path)
    assert normalized == "/api/v1/apis/{id}/test"

    plain_path = "/api/v1/monitoring/metrics"
    assert normalize_endpoint(plain_path) == plain_path


def test_metrics_endpoint_exposition_format(client: TestClient):
    """Verify /metrics returns Prometheus text exposition format."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    text = resp.text

    assert "apishield_http_requests_total" in text
    assert "apishield_http_request_duration_seconds" in text
    assert "apishield_app_healthy" in text
    assert "apishield_scheduler_running" in text


def test_metrics_increment_on_api_requests(client: TestClient):
    """Verify making HTTP requests increments Prometheus request counter."""
    # Hit health endpoint
    client.get("/health/live")

    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    metrics_text = metrics_resp.text

    assert 'apishield_http_requests_total{endpoint="/health/live",method="GET",status="200"}' in metrics_text
