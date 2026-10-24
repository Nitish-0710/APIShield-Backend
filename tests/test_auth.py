from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.user import User


def test_register_user_success(client: TestClient, db_session: Session):
    """Registering creates a user with Argon2-hashed password, not plaintext."""
    payload = {
        "name": "Ada Lovelace",
        "email": "ada@apishield.dev",
        "password": "SecurePassword123!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Ada Lovelace"
    assert data["email"] == "ada@apishield.dev"
    assert data["role"] == "developer"
    assert "id" in data
    assert "password" not in data
    assert "password_hash" not in data

    # Verify directly in DB that password is not plaintext
    user_in_db = db_session.execute(
        select(User).where(User.email == "ada@apishield.dev")
    ).scalar_one()
    assert user_in_db.password_hash != "SecurePassword123!"
    assert user_in_db.password_hash.startswith("$argon2id$")


def test_register_duplicate_email_fails(client: TestClient, test_user: User):
    """Duplicate email registration returns 409 Conflict with standard error envelope."""
    payload = {
        "name": "Imposter",
        "email": test_user.email,
        "password": "AnotherPassword456!",
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "CONFLICT"
    assert "email" in data["error"]["fieldErrors"]
    assert "requestId" in data["error"]


def test_register_validation_failure(client: TestClient):
    """Validation errors return 422 with fieldErrors map."""
    payload = {
        "name": "A",  # too short (< 2)
        "email": "not-an-email",
        "password": "short",  # < 8
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "name" in data["error"]["fieldErrors"]
    assert "email" in data["error"]["fieldErrors"]
    assert "password" in data["error"]["fieldErrors"]


def test_login_success_sets_http_only_cookie_and_csrf(client: TestClient, test_user: User):
    """Successful login sets secure HTTP-only session cookie and returns profile."""
    payload = {
        "email": test_user.email,
        "password": "ValidPassword123!",
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["email"] == test_user.email
    assert data["name"] == test_user.name

    # Check session cookie properties
    session_cookie = response.cookies.get("apishield_session")
    assert session_cookie is not None

    # Check CSRF cookie and header
    csrf_cookie = response.cookies.get("apishield_csrf")
    assert csrf_cookie is not None
    assert "X-CSRF-Token" in response.headers
    assert response.headers["X-CSRF-Token"] == csrf_cookie


def test_login_invalid_credentials_returns_safe_error(client: TestClient):
    """Invalid credentials return 401 without revealing whether the user exists."""
    payload = {
        "email": "nonexistent@apishield.dev",
        "password": "SomePassword123!",
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "INVALID_CREDENTIALS"
    assert data["error"]["message"] == "Invalid email or password."


def test_get_me_authenticated(authenticated_client: TestClient, test_user: User):
    """Accessing /auth/me with session cookie returns the authenticated user profile."""
    response = authenticated_client.get("/api/v1/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email
    assert data["name"] == test_user.name
    assert data["id"] == test_user.id


def test_get_me_unauthenticated(client: TestClient):
    """Unauthenticated call to /auth/me returns 401 Unauthorized."""
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"


def test_logout_invalidates_session_and_clears_cookies(
    client: TestClient,
    test_user: User,
    db_session: Session,
):
    """Logout invalidates session and prevents further authenticated requests."""
    # Step 1: Login
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "ValidPassword123!"},
    )
    assert login_resp.status_code == 200
    csrf_token = login_resp.headers["X-CSRF-Token"]

    # Step 2: Verify /auth/me works
    me_resp1 = client.get("/api/v1/auth/me")
    assert me_resp1.status_code == 200

    # Step 3: Logout with CSRF token
    logout_resp = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout_resp.status_code == 200
    assert logout_resp.json()["message"] == "Logged out successfully."

    # Step 4: Verify subsequent /auth/me fails
    me_resp2 = client.get("/api/v1/auth/me")
    assert me_resp2.status_code == 401


def test_csrf_endpoint_generates_token(client: TestClient):
    """GET /api/v1/auth/csrf returns token and sets cookie."""
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    data = response.json()
    assert "csrfToken" in data
    assert response.cookies.get("apishield_csrf") == data["csrfToken"]
