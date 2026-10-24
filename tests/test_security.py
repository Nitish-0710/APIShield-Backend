from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import generate_session_token, hash_session_token
from app.models.session import UserSession
from app.models.user import User


def test_csrf_missing_on_logout_fails(client: TestClient, test_user: User):
    """Calling logout with session cookie but without CSRF header is rejected with 403."""
    client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "ValidPassword123!"},
    )

    # Attempt logout without sending X-CSRF-Token header
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "CSRF_ERROR"
    assert "CSRF" in data["error"]["message"]


def test_csrf_mismatched_token_fails(client: TestClient, test_user: User):
    """Calling logout with a mismatched CSRF header is rejected with 403."""
    client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "ValidPassword123!"},
    )

    response = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": "completely-fake-csrf-token-12345"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_ERROR"


def test_tampered_session_cookie_rejected(client: TestClient):
    """Tampered or invalid session cookie is rejected with 401."""
    client.cookies.set("apishield_session", "forged-nonexistent-session-id")
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_expired_session_rejected(client: TestClient, test_user: User, db_session: Session):
    """Sessions with past expiration dates are rejected."""
    raw_token = generate_session_token()
    token_hash = hash_session_token(raw_token)

    # Insert an already expired session directly
    expired_session = UserSession(
        user_id=test_user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db_session.add(expired_session)
    db_session.commit()

    client.cookies.set("apishield_session", raw_token)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_request_id_present_on_all_responses(client: TestClient):
    """All responses (success and error) include an X-Request-ID header."""
    # Success response
    res1 = client.get("/health/live")
    assert "x-request-id" in res1.headers

    # Error response
    res2 = client.get("/api/v1/auth/me")
    assert "x-request-id" in res2.headers
    assert res2.json()["error"]["requestId"] == res2.headers["x-request-id"]


def test_rate_limiting_enforced(client: TestClient):
    """Rapid repeated requests trigger 429 Too Many Requests."""
    from app.core.middleware import rate_limiter
    rate_limiter.history.clear()
    rate_limiter.limit = 3  # Temporarily lower limit for test

    try:
        # Request 1, 2, 3 succeed
        for _ in range(3):
            res = client.post(
                "/api/v1/auth/login",
                json={"email": "nobody@apishield.dev", "password": "wrong"},
            )
            assert res.status_code == 401

        # Request 4 exceeds rate limit
        blocked = client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@apishield.dev", "password": "wrong"},
        )
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    finally:
        rate_limiter.history.clear()
        rate_limiter.limit = 100  # Restore limit
