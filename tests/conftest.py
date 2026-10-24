import os
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Ensure test environment variables before importing app
os.environ["ENVIRONMENT"] = "testing"
os.environ["DEBUG"] = "false"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "apishield-testing-secret-key-at-least-32-chars-long"
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["CORS_ORIGINS"] = "http://localhost:3000,http://localhost:5173"
os.environ["AUTH_RATE_LIMIT_PER_MINUTE"] = "100"

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.services.auth_service import register_user
from app.schemas.auth import UserRegisterRequest

# In-memory SQLite engine for tests
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
    expire_on_commit=False,
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session: Session) -> User:
    req = UserRegisterRequest(
        name="Test Engineer",
        email="engineer@apishield.dev",
        password="ValidPassword123!",
    )
    return register_user(db_session, req)


@pytest.fixture
def authenticated_client(client: TestClient, test_user: User) -> TestClient:
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": "ValidPassword123!"},
    )
    assert login_resp.status_code == 200
    return client


@pytest.fixture
def auth_headers(authenticated_client: TestClient) -> dict:
    csrf = authenticated_client.cookies.get("apishield_csrf")
    return {"X-CSRF-Token": csrf} if csrf else {}


@pytest.fixture
def other_user(db_session: Session) -> User:
    req = UserRegisterRequest(
        name="Other Engineer",
        email="other@apishield.dev",
        password="ValidPassword456!",
    )
    return register_user(db_session, req)

