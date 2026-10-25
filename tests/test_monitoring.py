import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.api import ApiEndpoint
from app.models.test_result import TestResultRecord
from app.models.user import User
from app.services.monitoring_service import monitoring_service
from tests.conftest import TestingSessionLocal


@pytest.fixture(autouse=True)
def configure_monitoring_test_session():
    monitoring_service.set_session_factory(TestingSessionLocal)
    yield
    monitoring_service.set_session_factory(None)


@pytest.fixture
def auth_user_and_session(db_session: Session, client: TestClient):
    """Register and log in a test user, returning User object and authenticated client."""
    from app.core.security import hash_password
    import uuid

    user = User(
        email=f"monitor_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("StrongPassword123!"),
        name="Monitoring User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "StrongPassword123!"},
    )
    assert login_resp.status_code == 200

    return user, client


@pytest.fixture
def secondary_user(db_session: Session):
    """Create a secondary user for cross-user isolation tests."""
    from app.core.security import hash_password
    import uuid

    user = User(
        email=f"other_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("StrongPassword123!"),
        name="Other User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# 1. Scheduled Monitoring Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_monitoring_tick_executes_probe_for_enabled_api(
    db_session: Session,
    auth_user_and_session,
):
    user, _ = auth_user_and_session

    api = ApiEndpoint(
        user_id=user.id,
        name="Monitored Target",
        url="https://example.com/health",
        method="GET",
        monitoring=True,
        interval_sec=60,
        expected_status=200,
        timeout_ms=5000,
    )
    db_session.add(api)
    db_session.commit()
    db_session.refresh(api)

    with patch(
        "app.services.test_service.execute_safe_request",
        return_value=(200, {"content-type": "application/json"}, '{"status":"ok"}', 42.5),
    ):
        claimed = await monitoring_service.tick()
        assert claimed >= 1
        await monitoring_service.wait_for_active_probes()

    # Verify probe completed and updated API health
    db_session.expire_all()
    updated_api = db_session.get(ApiEndpoint, api.id)
    assert updated_api is not None
    assert updated_api.is_probing is False
    assert updated_api.health == "healthy"
    assert updated_api.last_status_code == 200
    assert updated_api.last_latency_ms == 42.5
    assert updated_api.next_run_at is not None
    next_run = (
        updated_api.next_run_at
        if updated_api.next_run_at.tzinfo
        else updated_api.next_run_at.replace(tzinfo=timezone.utc)
    )
    assert next_run > datetime.now(timezone.utc) - timedelta(seconds=5)

    # Verify automated probe persisted test result without body or headers
    record = db_session.scalar(
        select(TestResultRecord).where(TestResultRecord.api_id == api.id)
    )
    assert record is not None
    assert record.passed is True
    assert record.outcome == "success"
    assert record.status_code == 200
    assert record.body == ""  # Body omitted for automated probes
    assert record.headers == []  # Headers omitted for automated probes


@pytest.mark.asyncio
async def test_monitoring_tick_skips_disabled_api(
    db_session: Session,
    auth_user_and_session,
):
    user, _ = auth_user_and_session

    api = ApiEndpoint(
        user_id=user.id,
        name="Disabled Target",
        url="https://example.com/health",
        method="GET",
        monitoring=False,
        interval_sec=60,
    )
    db_session.add(api)
    db_session.commit()

    with patch("app.services.test_service.execute_safe_request") as mock_exec:
        claimed = await monitoring_service.tick()
        await monitoring_service.wait_for_active_probes()
        assert mock_exec.call_count == 0

    record = db_session.scalar(
        select(TestResultRecord).where(TestResultRecord.api_id == api.id)
    )
    assert record is None


@pytest.mark.asyncio
async def test_monitoring_tick_skips_api_not_due(
    db_session: Session,
    auth_user_and_session,
):
    user, _ = auth_user_and_session

    future_time = datetime.now(timezone.utc) + timedelta(minutes=10)
    api = ApiEndpoint(
        user_id=user.id,
        name="Not Due Target",
        url="https://example.com/health",
        method="GET",
        monitoring=True,
        interval_sec=60,
        next_run_at=future_time,
    )
    db_session.add(api)
    db_session.commit()

    with patch("app.services.test_service.execute_safe_request") as mock_exec:
        claimed = await monitoring_service.tick()
        await monitoring_service.wait_for_active_probes()
        assert mock_exec.call_count == 0


@pytest.mark.asyncio
async def test_monitoring_duplicate_claim_prevention(
    db_session: Session,
    auth_user_and_session,
):
    """Verify that if an API is already marked is_probing=True, another worker cannot claim it."""
    user, _ = auth_user_and_session

    api = ApiEndpoint(
        user_id=user.id,
        name="Already Probing Target",
        url="https://example.com/health",
        method="GET",
        monitoring=True,
        interval_sec=60,
        is_probing=True,  # Simulate another worker holding the claim
    )
    db_session.add(api)
    db_session.commit()

    with patch("app.services.test_service.execute_safe_request") as mock_exec:
        claimed = await monitoring_service.tick()
        await monitoring_service.wait_for_active_probes()
        assert mock_exec.call_count == 0


@pytest.mark.asyncio
async def test_monitoring_handles_timeout_gracefully(
    db_session: Session,
    auth_user_and_session,
):
    user, _ = auth_user_and_session

    api = ApiEndpoint(
        user_id=user.id,
        name="Timing Out Target",
        url="https://example.com/timeout",
        method="GET",
        monitoring=True,
        interval_sec=60,
        expected_status=200,
    )
    db_session.add(api)
    db_session.commit()

    with patch(
        "app.services.test_service.execute_safe_request",
        side_effect=TimeoutError("Request timed out after 5000ms"),
    ):
        claimed = await monitoring_service.tick()
        assert claimed >= 1
        await monitoring_service.wait_for_active_probes()

    db_session.expire_all()
    updated_api = db_session.get(ApiEndpoint, api.id)
    assert updated_api is not None
    assert updated_api.is_probing is False
    assert updated_api.health == "failing"

    record = db_session.scalar(
        select(TestResultRecord).where(TestResultRecord.api_id == api.id)
    )
    assert record is not None
    assert record.outcome == "timeout"
    assert record.passed is False


# ---------------------------------------------------------------------------
# 2. Metrics Collection and API Tests
# ---------------------------------------------------------------------------


def test_metrics_unauthenticated_returns_401(client: TestClient):
    resp = client.get("/api/v1/monitoring/metrics")
    assert resp.status_code == 401


def test_metrics_cross_user_api_returns_404(
    db_session: Session,
    auth_user_and_session,
    secondary_user: User,
):
    _, client = auth_user_and_session

    other_api = ApiEndpoint(
        user_id=secondary_user.id,
        name="Other User API",
        url="https://example.com/private",
        method="GET",
        monitoring=True,
    )
    db_session.add(other_api)
    db_session.commit()

    resp = client.get(f"/api/v1/monitoring/metrics?apiId={other_api.id}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_metrics_empty_dataset_returns_consistent_points(
    auth_user_and_session,
):
    _, client = auth_user_and_session

    resp = client.get("/api/v1/monitoring/metrics?range=1h")
    assert resp.status_code == 200
    points = resp.json()
    assert len(points) == 30  # 1h produces 30 points

    # Verify field names match frontend MetricPoint contract
    sample = points[0]
    expected_keys = {
        "t",
        "avgLatency",
        "p95Latency",
        "requests",
        "errorRate4xx",
        "errorRate5xx",
        "errorRate",
        "timeouts",
        "availability",
    }
    assert expected_keys.issubset(sample.keys())

    # Empty points must represent zero activity with availability as null (None)
    for p in points:
        assert p["requests"] == 0
        assert p["avgLatency"] == 0.0
        assert p["p95Latency"] == 0.0
        assert p["errorRate"] == 0.0
        assert p["errorRate4xx"] == 0.0
        assert p["errorRate5xx"] == 0.0
        assert p["timeouts"] == 0
        assert p["availability"] is None


def test_metrics_calculations_accuracy(
    db_session: Session,
    auth_user_and_session,
):
    user, client = auth_user_and_session

    api = ApiEndpoint(
        user_id=user.id,
        name="Calculation Test API",
        url="https://example.com/calc",
        method="GET",
        monitoring=True,
    )
    db_session.add(api)
    db_session.commit()

    now = datetime.now(timezone.utc)
    # Insert 5 test results 1 minute ago (within the current 1h window and same bucket)
    tested_time = now - timedelta(minutes=1)

    records = [
        # 1: 200 OK, 100ms, success
        TestResultRecord(
            api_id=api.id,
            user_id=user.id,
            passed=True,
            outcome="success",
            status_code=200,
            expected_status=200,
            latency_ms=100.0,
            tested_at=tested_time,
        ),
        # 2: 200 OK, 200ms, success
        TestResultRecord(
            api_id=api.id,
            user_id=user.id,
            passed=True,
            outcome="success",
            status_code=200,
            expected_status=200,
            latency_ms=200.0,
            tested_at=tested_time,
        ),
        # 3: 404 Client Error, 50ms, failure
        TestResultRecord(
            api_id=api.id,
            user_id=user.id,
            passed=False,
            outcome="failure",
            status_code=404,
            expected_status=200,
            latency_ms=50.0,
            tested_at=tested_time,
        ),
        # 4: 500 Server Error, 300ms, failure
        TestResultRecord(
            api_id=api.id,
            user_id=user.id,
            passed=False,
            outcome="failure",
            status_code=500,
            expected_status=200,
            latency_ms=300.0,
            tested_at=tested_time,
        ),
        # 5: Timeout, 1000ms, timeout
        TestResultRecord(
            api_id=api.id,
            user_id=user.id,
            passed=False,
            outcome="timeout",
            status_code=None,
            expected_status=200,
            latency_ms=1000.0,
            tested_at=tested_time,
        ),
    ]
    db_session.add_all(records)
    db_session.commit()

    resp = client.get(f"/api/v1/monitoring/metrics?apiId={api.id}&range=1h")
    assert resp.status_code == 200
    points = resp.json()

    # Find the bucket that recorded the 5 requests
    active_points = [p for p in points if p["requests"] > 0]
    assert len(active_points) == 1
    pt = active_points[0]

    assert pt["requests"] == 5
    # Latencies: [50, 100, 200, 300, 1000] -> sum = 1650 -> avg = 330.0
    assert pt["avgLatency"] == 330.0
    # p95 on 5 points (index 4 * 0.95 = 3.8): interpolated between 300 and 1000 = 300 + 0.8 * 700 = 860.0
    assert pt["p95Latency"] == 860.0
    # 1 4xx out of 5 = 20.0%
    assert pt["errorRate4xx"] == 20.0
    # 1 5xx out of 5 = 20.0%
    assert pt["errorRate5xx"] == 20.0
    # 3 failures out of 5 = 60.0%
    assert pt["errorRate"] == 60.0
    # 1 timeout
    assert pt["timeouts"] == 1
    # 2 passed out of 5 = 40.0%
    assert pt["availability"] == 40.0

    # Remaining 29 empty buckets must have availability as null
    inactive_points = [p for p in points if p["requests"] == 0]
    assert len(inactive_points) == 29
    for ip in inactive_points:
        assert ip["availability"] is None


def test_metrics_supports_all_time_ranges(
    auth_user_and_session,
):
    _, client = auth_user_and_session

    range_expected_lengths = {
        "1h": 30,
        "6h": 36,
        "24h": 48,
        "7d": 42,
    }

    for rng, expected_len in range_expected_lengths.items():
        resp = client.get(f"/api/v1/monitoring/metrics?range={rng}")
        assert resp.status_code == 200
        assert len(resp.json()) == expected_len


def test_metrics_invalid_range_rejected(
    auth_user_and_session,
):
    _, client = auth_user_and_session

    resp = client.get("/api/v1/monitoring/metrics?range=30d")
    assert resp.status_code == 422
