# APIShield Backend — Foundation & Authentication

APIShield is an AI-based API failure prediction and root-cause monitoring platform. This backend service provides the core REST API built with FastAPI, PostgreSQL / SQLAlchemy 2.x, Alembic, and Argon2 password security.

---

## 1. Architecture & Directory Structure

```text
backend/
├── app/
│   ├── api/
│   │   ├── deps.py               # Dependency injection (DB, auth, CSRF, rate limit)
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── auth.py       # Authentication endpoints (/register, /login, /me, /logout, /csrf)
│   │       │   └── health.py     # Liveness (/health/live) and Readiness (/health/ready)
│   │       └── router.py         # API v1 router registration
│   ├── core/
│   │   ├── config.py             # Pydantic Settings & environment variables
│   │   ├── logging.py            # Structured sanitized logging (masks secrets/tokens)
│   │   ├── middleware.py         # X-Request-ID, in-memory Rate Limiting, CSRF verification
│   │   └── security.py           # Argon2id password hashing, SHA-256 session token hashing
│   ├── db/
│   │   ├── base.py               # SQLAlchemy DeclarativeBase
│   │   └── session.py            # Engine, sessionmaker, get_db, DB readiness check
│   ├── models/
│   │   ├── user.py               # User entity (Argon2 password hash, UUID, active flag)
│   │   └── session.py            # UserSession entity (SHA-256 hashed token lookup)
│   ├── schemas/
│   │   ├── auth.py               # Auth request/response schemas (matches frontend types)
│   │   └── error.py              # Standard error envelope schema
│   ├── services/
│   │   └── auth_service.py       # Authentication and session domain logic
│   └── main.py                   # FastAPI entrypoint, CORS, error handlers, route mounting
├── migrations/
│   ├── env.py                    # Alembic migration environment
│   ├── script.py.mako            # Migration template
│   └── versions/
│       └── 0001_initial_user_and_session.py
├── tests/
│   ├── conftest.py               # Test fixtures (SQLite in-memory, TestClient, test user)
│   ├── test_auth.py              # Register, login, me, logout, cookies tests
│   ├── test_health.py            # Liveness and readiness tests
│   └── test_security.py          # CSRF, tampering, expiration, rate limiting tests
├── .env.example                  # Environment template (placeholders only)
├── alembic.ini                   # Alembic database migration configuration
├── pyproject.toml                # Project metadata and pytest/ruff configuration
├── requirements.txt              # Production dependencies
├── requirements-dev.txt          # Development & test dependencies
└── README.md                     # Documentation
```

---

## 2. Setup & Installation

### Prerequisites
* Python 3.11, 3.12, or 3.13
* PostgreSQL 14+ (or SQLite for lightweight local testing)

### Step 1: Create and activate virtual environment
```bash
cd backend
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate
```

### Step 2: Install dependencies
```bash
pip install -r requirements-dev.txt
```

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Ensure `SECRET_KEY` is set to a secure string (minimum 32 characters), and `DATABASE_URL` points to your PostgreSQL database:
```ini
ENVIRONMENT=development
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/apishield
SECRET_KEY=your-secure-random-secret-key-min-32-chars
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

---

## 3. Database Migrations

Apply database migrations:
```bash
alembic upgrade head
```

Roll back migration (if needed):
```bash
alembic downgrade -1
```

---

## 4. Running the Development Server

Start the ASGI server with hot-reload:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive API documentation:
* Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
* ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 5. Authentication & Security Contract

### Endpoints
* `POST /api/v1/auth/register` — Creates user account with Argon2id password hash.
* `POST /api/v1/auth/login` — Verifies credentials, issues fresh session and sets HTTP-only `apishield_session` cookie + `apishield_csrf` cookie.
* `GET /api/v1/auth/me` — Returns current authenticated user profile (`id`, `name`, `email`, `role`).
* `POST /api/v1/auth/logout` — Requires CSRF verification. Invalidates session in database and deletes cookies.
* `GET /api/v1/auth/csrf` — Provides a fresh CSRF token and sets `apishield_csrf` cookie.

### Cookie Specifications
* **Session Cookie:** `apishield_session`
  * `HttpOnly`: `True` (inaccessible to JavaScript)
  * `SameSite`: `Lax`
  * `Secure`: `False` in local dev, `True` in HTTPS/production
  * `Path`: `/`
  * `Max-Age`: `86400` (24 hours)
* **CSRF Cookie:** `apishield_csrf`
  * `HttpOnly`: `False` (accessible for client Double Submit verification)
  * `SameSite`: `Lax`
  * `Path`: `/`

### CSRF Protection
For state-changing requests (`POST`, `PUT`, `PATCH`, `DELETE`) authenticated by session cookies:
1. Client obtains CSRF token from the `apishield_csrf` cookie, `X-CSRF-Token` response header on login, or `GET /api/v1/auth/csrf`.
2. Client sends the token in the `X-CSRF-Token` (or `X-XSRF-Token`) request header.
3. Server validates matching tokens using constant-time comparison (`hmac.compare_digest`).

---

## 6. Running Tests

Run the full automated test suite:
```bash
pytest -v
```
