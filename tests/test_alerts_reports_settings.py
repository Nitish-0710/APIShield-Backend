from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.api import ApiEndpoint
from app.models.ml import AlertRecord, SettingRecord
from app.models.test_result import TestResultRecord
from app.models.user import User
from app.services.alert_service import AlertService
from app.services.test_service import TestService


@pytest.fixture
def test_api(db_session: Session, test_user: User) -> ApiEndpoint:
    api = ApiEndpoint(
        user_id=test_user.id,
        name="Auth Identity Service",
        url="https://api.github.com/status",
        method="GET",
        expected_status=200,
        monitoring=True,
    )
    db_session.add(api)
    db_session.commit()
    db_session.refresh(api)
    return api


def test_alert_creation_and_cooldown_deduplication(db_session: Session, test_user: User, test_api: ApiEndpoint):
    """Verify alert cooldown suppresses rapid duplicate alerts for the same condition."""
    alert_service = AlertService()

    # 1. First alert created
    a1 = alert_service.create_alert_if_due(
        db=db_session,
        user_id=test_user.id,
        api_id=test_api.id,
        title="High Latency Alert",
        description="Observed latency exceeded 1500ms",
        severity="warning",
        source="monitoring",
        condition_key="latency_breached",
        cooldown_minutes=15,
    )
    assert a1 is not None
    assert a1.status == "open"

    # 2. Duplicate alert immediately attempted
    a2 = alert_service.create_alert_if_due(
        db=db_session,
        user_id=test_user.id,
        api_id=test_api.id,
        title="High Latency Alert",
        description="Observed latency exceeded 1500ms",
        severity="warning",
        source="monitoring",
        condition_key="latency_breached",
        cooldown_minutes=15,
    )
    assert a2 is None  # Suppressed by cooldown


def test_alert_lifecycle_status_update(
    authenticated_client: TestClient,
    auth_headers: dict,
    db_session: Session,
    test_user: User,
    test_api: ApiEndpoint,
):
    """Verify alert can be acknowledged and resolved via API."""
    alert_service = AlertService()
    alert = alert_service.create_alert_if_due(
        db=db_session,
        user_id=test_user.id,
        api_id=test_api.id,
        title="Elevated Error Rate",
        description="Error rate reached 20%",
        severity="critical",
        source="prediction",
        condition_key="error_rate_critical",
    )
    assert alert is not None

    # Update to acknowledged
    resp = authenticated_client.patch(
        f"/api/v1/alerts/{alert.id}/status",
        headers=auth_headers,
        json={"status": "acknowledged"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "acknowledged"

    # Update to resolved
    resp2 = authenticated_client.patch(
        f"/api/v1/alerts/{alert.id}/status",
        headers=auth_headers,
        json={"status": "resolved"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "resolved"
    assert resp2.json()["resolved_at"] is not None


def test_user_settings_get_and_update(authenticated_client: TestClient, auth_headers: dict):
    """Verify user settings retrieval with safe defaults and schema-validated updates."""
    # 1. Get settings
    get_resp = authenticated_client.get("/api/v1/settings")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "alert_cooldown_minutes" in data
    assert data["alert_cooldown_minutes"] == 15

    # 2. Update settings
    put_resp = authenticated_client.put(
        "/api/v1/settings",
        headers=auth_headers,
        json={
            "alert_cooldown_minutes": 30,
            "latency_warning_threshold_ms": 1500.0,
            "risk_alert_threshold": 80.0,
        },
    )
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["alert_cooldown_minutes"] == 30
    assert updated["latency_warning_threshold_ms"] == 1500.0


def test_monitoring_report_summary(
    authenticated_client: TestClient,
    test_api: ApiEndpoint,
    db_session: Session,
):
    """Verify monitoring report summary calculates aggregations correctly."""
    for i in range(4):
        tr = TestResultRecord(
            api_id=test_api.id,
            user_id=test_api.user_id,
            passed=(i % 2 == 0),
            outcome="success" if (i % 2 == 0) else "failure",
            status_code=200 if (i % 2 == 0) else 500,
            expected_status=200,
            latency_ms=100.0 * (i + 1),
            tested_at=datetime.now(timezone.utc),
        )
        db_session.add(tr)
    db_session.commit()

    resp = authenticated_client.get(f"/api/v1/reports/summary?apiId={test_api.id}&range=24h")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_observations"] == 4
    assert data["availability"] == 50.0
    assert data["avg_latency_ms"] == 250.0


def test_csv_export_sanitization_and_ownership(
    authenticated_client: TestClient,
    test_api: ApiEndpoint,
    db_session: Session,
):
    """Verify CSV export sanitizes formulas and does not expose sensitive authorization tokens."""
    tr = TestResultRecord(
        api_id=test_api.id,
        user_id=test_api.user_id,
        passed=True,
        outcome="success",
        status_code=200,
        expected_status=200,
        latency_ms=150.0,
        error="=cmd|' /C calc'!A0",  # Potential formula injection string
        tested_at=datetime.now(timezone.utc),
    )
    db_session.add(tr)
    db_session.commit()

    resp = authenticated_client.get(f"/api/v1/reports/export-csv?apiId={test_api.id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    csv_text = resp.text

    assert "record_id,api_id,api_name,tested_at" in csv_text
    # Formula injection sanitized with leading quote
    assert "'=cmd|" in csv_text
    # No sensitive auth headers or cookies exposed in export
    assert "cookie" not in csv_text.lower()
    assert "bearer" not in csv_text.lower()


def test_automated_probe_failure_generates_alert(db_session: Session, test_api: ApiEndpoint, test_user: User):
    """Verify automated monitoring probe failures automatically generate persistent alerts."""
    with patch(
        "app.services.test_service.execute_safe_request",
        return_value=(500, {}, "Internal Server Error", 120.0),
    ):
        result = TestService.run_saved_api_test(
            db=db_session,
            user=None,
            api_id=test_api.id,
            is_automated=True,
        )
        assert result is not None
        assert result.passed is False
        assert result.outcome == "failure"

    alert = (
        db_session.query(AlertRecord)
        .filter(AlertRecord.api_id == test_api.id, AlertRecord.user_id == test_user.id)
        .first()
    )
    assert alert is not None
    assert alert.status == "open"
    assert alert.severity == "critical"
    assert alert.source == "monitoring"
    assert "500" in alert.title or "500" in alert.description
    assert alert.fingerprint is not None


def test_successful_probe_produces_no_alert(db_session: Session, test_api: ApiEndpoint):
    """Verify normal successful automated monitoring probes do not create alerts."""
    with patch(
        "app.services.test_service.execute_safe_request",
        return_value=(200, {"content-type": "application/json"}, '{"status":"ok"}', 45.0),
    ):
        result = TestService.run_saved_api_test(
            db=db_session,
            user=None,
            api_id=test_api.id,
            is_automated=True,
        )
        assert result is not None
        assert result.passed is True
        assert result.outcome == "success"

    # Confirm no alert was created for this successful probe
    count = db_session.query(AlertRecord).filter(AlertRecord.api_id == test_api.id).count()
    assert count == 0


def test_automated_probe_timeout_generates_critical_alert(db_session: Session, test_api: ApiEndpoint, test_user: User):
    """Verify timeout outcomes generate critical alerts."""
    with patch(
        "app.services.test_service.execute_safe_request",
        side_effect=TimeoutError("Request timed out after 5000ms"),
    ):
        result = TestService.run_saved_api_test(
            db=db_session,
            user=None,
            api_id=test_api.id,
            is_automated=True,
        )
        assert result is not None
        assert result.outcome == "timeout"
        assert result.passed is False

    alert = (
        db_session.query(AlertRecord)
        .filter(AlertRecord.api_id == test_api.id, AlertRecord.user_id == test_user.id)
        .first()
    )
    assert alert is not None
    assert alert.severity == "critical"
    assert "Timeout" in alert.title


def test_automated_probe_cooldown_deduplication(db_session: Session, test_api: ApiEndpoint, test_user: User):
    """Verify duplicate alerts within the cooldown window are suppressed."""
    with patch(
        "app.services.test_service.execute_safe_request",
        return_value=(503, {}, "Service Unavailable", 100.0),
    ):
        # 1. First probe failure creates alert
        res1 = TestService.run_saved_api_test(db=db_session, user=None, api_id=test_api.id, is_automated=True)
        assert res1 is not None and res1.passed is False

        alerts_after_first = (
            db_session.query(AlertRecord)
            .filter(AlertRecord.api_id == test_api.id)
            .all()
        )
        assert len(alerts_after_first) == 1

        # 2. Second immediate probe failure with identical condition is suppressed by cooldown
        res2 = TestService.run_saved_api_test(db=db_session, user=None, api_id=test_api.id, is_automated=True)
        assert res2 is not None and res2.passed is False

        alerts_after_second = (
            db_session.query(AlertRecord)
            .filter(AlertRecord.api_id == test_api.id)
            .all()
        )
        assert len(alerts_after_second) == 1  # Cooldown prevented duplicate


def test_latency_threshold_breach_generates_warning_alert(db_session: Session, test_api: ApiEndpoint):
    """Verify exceeding configured max_latency_ms triggers a latency warning alert."""
    test_api.max_latency_ms = 500
    db_session.commit()

    with patch(
        "app.services.test_service.execute_safe_request",
        return_value=(200, {}, '{"ok": true}', 1200.0),
    ):
        result = TestService.run_saved_api_test(
            db=db_session,
            user=None,
            api_id=test_api.id,
            is_automated=True,
        )
        assert result is not None
        assert result.passed is True

    alert = (
        db_session.query(AlertRecord)
        .filter(AlertRecord.api_id == test_api.id)
        .first()
    )
    assert alert is not None
    assert alert.severity == "warning"
    assert "High Latency" in alert.title


def test_diagnostics_endpoint_remains_strictly_read_only(
    authenticated_client: TestClient,
    test_api: ApiEndpoint,
    db_session: Session,
):
    """Verify GET /diagnostics is read-only and does not persist alerts."""
    # Seed a failed test observation so diagnostics detects an availability breach
    tr = TestResultRecord(
        api_id=test_api.id,
        user_id=test_api.user_id,
        passed=False,
        outcome="failure",
        status_code=500,
        expected_status=200,
        latency_ms=100.0,
        tested_at=datetime.now(timezone.utc),
    )
    db_session.add(tr)
    db_session.commit()

    alerts_before = db_session.query(AlertRecord).filter(AlertRecord.api_id == test_api.id).count()

    # Call diagnostics GET endpoint
    resp = authenticated_client.get(f"/api/v1/diagnostics/{test_api.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["findings"]) > 0

    alerts_after = db_session.query(AlertRecord).filter(AlertRecord.api_id == test_api.id).count()
    assert alerts_after == alerts_before  # Read-only, no alerts created
