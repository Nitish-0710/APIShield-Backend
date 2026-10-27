# APIShield — Backend Integration & Developer Handoff Guide

> **Document Version:** 1.0.0  
> **Status:** Final Backend Release  
> **Target Audience:** Frontend Engineers, Full-Stack Developers, MLOps Engineers, and API Consumers  
> **Backend Repository:** `D:\College\3rd_Year\MLOPS\CP\backend`  
> **Active Serving Model:** `model_v20261026_182719` (`RandomForestClassifier`, 15 tabular telemetry features)  
> **Active Verification:** 141 passed unit, integration, and security tests across 21 test suites  

---

## Table of Contents

1. [A. Project Overview](#a-project-overview)
   - [Core Capabilities](#core-capabilities)
   - [Backend Responsibilities vs Out-of-Scope](#backend-responsibilities-vs-out-of-scope)
   - [High-Level Architecture & Mermaid Diagram](#high-level-architecture--mermaid-diagram)
2. [B. Repository Structure & Module Map](#b-repository-structure--module-map)
3. [C. Local Setup & Execution Guide](#c-local-setup--execution-guide)
   - [Prerequisites & Supported Runtimes](#prerequisites--supported-runtimes)
   - [Virtual Environment Setup (Windows & POSIX)](#virtual-environment-setup-windows--posix)
   - [Environment Configuration (.env)](#environment-configuration-env)
   - [Database Migrations (Alembic)](#database-migrations-alembic)
   - [Running the Backend Locally](#running-the-backend-locally)
   - [Running the Docker Compose Stack](#running-the-docker-compose-stack)
   - [Accessing Observability (Swagger, ReDoc, Prometheus, Grafana)](#accessing-observability)
   - [Troubleshooting Startup Failures](#troubleshooting-startup-failures)
4. [D. API Reference & Contract Specification](#d-api-reference--contract-specification)
   - [Complete Endpoint Inventory Table](#complete-endpoint-inventory-table)
   - [Standard Error Envelope](#standard-error-envelope)
   - [Route Group 1: Authentication & Session Management](#route-group-1-authentication--session-management)
   - [Route Group 2: System Health & Readiness](#route-group-2-system-health--readiness)
   - [Route Group 3: Saved API Configuration & Management](#route-group-3-saved-api-configuration--management)
   - [Route Group 4: Ad-Hoc & Saved API Testing](#route-group-4-ad-hoc--saved-api-testing)
   - [Route Group 5: Time-Series Monitoring & Metrics](#route-group-5-time-series-monitoring--metrics)
   - [Route Group 6: Failure Risk Predictions & Explainability](#route-group-6-failure-risk-predictions--explainability)
   - [Route Group 7: Root-Cause Diagnostics](#route-group-7-root-cause-diagnostics)
   - [Route Group 8: Alerts & Incident Lifecycle](#route-group-8-alerts--incident-lifecycle)
   - [Route Group 9: Reports & Telemetry Data Exports](#route-group-9-reports--telemetry-data-exports)
   - [Route Group 10: Application Settings](#route-group-10-application-settings)
   - [Route Group 11: MLOps, Training & Model Registry](#route-group-11-mlops-training--model-registry)
5. [E. Authentication, Session & Security Architecture](#e-authentication-session--security-architecture)
   - [Session Management Mechanism](#session-management-mechanism)
   - [CSRF Protection Workflow](#csrf-protection-workflow)
   - [CORS Configuration & Credentialed Headers](#cors-configuration--credentialed-headers)
   - [SSRF Protection Engine](#ssrf-protection-engine)
6. [F. Canonical Frontend Integration Code Examples](#f-canonical-frontend-integration-code-examples)
   - [Shared Reusable HTTP Client (`apiClient.js`)](#shared-reusable-http-client-apiclientjs)
   - [Authentication & Session Workflows](#authentication--session-workflows)
   - [API Configuration & Testing Workflows](#api-configuration--testing-workflows)
   - [Prediction, Explainability & Diagnostics Workflows](#prediction-explainability--diagnostics-workflows)
   - [Monitoring, Reports & CSV Export](#monitoring-reports--csv-export)
7. [G. Data Models & Entity Relationships](#g-data-models--entity-relationships)
   - [Database Schema & ORM Relationships](#database-schema--orm-relationships)
   - [ORM vs Pydantic Serialization Contract](#orm-vs-pydantic-serialization-contract)
8. [H. Machine Learning Lifecycle & Prediction Behavior](#h-machine-learning-lifecycle--prediction-behavior)
   - [15 Extracted Telemetry Features](#15-extracted-telemetry-features)
   - [Prediction Pipeline & Provenance Resolution](#prediction-pipeline--provenance-resolution)
   - [Model Explanations (SHAP & LIME)](#model-explanations-shap--lime)
   - [Group Fairness (Fairlearn & IBM AIF360)](#group-fairness-fairlearn--ibm-aif360)
   - [Candidate Evaluation vs Production Active Model](#candidate-evaluation-vs-production-active-model)
9. [I. Monitoring, Background Workflows & Observability](#i-monitoring-background-workflows--observability)
   - [Automated Background Probing Scheduler](#automated-background-probing-scheduler)
   - [Prometheus Metrics Instruments](#prometheus-metrics-instruments)
   - [Grafana Dashboard](#grafana-dashboard)
   - [Apache Airflow Workflows](#apache-airflow-workflows)
   - [DVC Reproducibility](#dvc-reproducibility)
10. [J. Error Handling & Troubleshooting Reference](#j-error-handling--troubleshooting-reference)
11. [K. Environment Configuration Reference](#k-environment-configuration-reference)
12. [L. Testing & Verification Runbook](#l-testing--verification-runbook)
13. [M. Frontend Integration Checklist](#m-frontend-integration-checklist)
14. [N. Verified cURL Smoke Test Scripts](#n-verified-curl-smoke-test-scripts)
15. [O. OpenAPI Specification Export Guide](#o-openapi-specification-export-guide)
16. [P. Documentation Verification & Audit Trail](#p-documentation-verification--audit-trail)

---

## A. Project Overview

### Core Capabilities

**APIShield** is an AI-powered API monitoring, telemetry analytics, failure risk prediction, root-cause diagnostics, and MLOps platform. It bridges proactive API health probing with machine learning to anticipate outages before downstream consumers are impacted.

The backend service is implemented in **Python 3.11–3.13** using **FastAPI**, **PostgreSQL** (via **SQLAlchemy 2.x** and **Alembic**), **scikit-learn**, native **SHAP** and **LIME** explainers, **MLflow Tracking & Model Registry**, **DVC**, **Fairlearn**, **IBM AIF360**, **Apache Airflow**, **Prometheus**, and **Grafana**.

### Backend Responsibilities vs Out-of-Scope

| Backend Responsibilities (Implemented & Verified) | Out-of-Scope for Backend (Frontend / Ops Domain) |
|---|---|
| Argon2id password hashing and secure session provisioning | User interface layouts, styling, themes, and client routing |
| HTTP-only cookie session handling with double-submit CSRF protection | Storing sensitive tokens in browser `localStorage` or `sessionStorage` |
| Encrypted storage of API credentials at rest using Fernet symmetric encryption | Direct browser-to-third-party API calls (bypassing SSRF controls) |
| Anti-SSRF validation engine pinning DNS, blocking private IPs, loopbacks, and cloud metadata | External reverse proxy TLS termination (e.g., NGINX, Cloudflare SSL) |
| Automated background probe scheduler executing scheduled HTTP health checks | End-user browser notifications / push notification service workers |
| 15-feature sliding-window feature extraction with strict time-leakage prevention | Client-side time-zone conversions (all backend timestamps are UTC ISO-8601) |
| Active model inference (`RandomForestClassifier`) with transparent Rule-Based fallback | Heavy client-side math or prediction recalculation |
| Model explainability using genuine `shap.TreeExplainer` and `lime.LimeTabularExplainer` | Rendering visual SHAP force plots or D3 graphs (backend delivers raw vectors) |
| Group fairness evaluation and demographic parity metric calculation | Business decisions regarding unprivileged customer SLA policies |
| Prometheus `/metrics` exposition and provisioned Grafana dashboards | Configuring external Alertmanager receivers (PagerDuty, OpsGenie) |

### Implemented vs Configured / External Features

To ensure seamless frontend integration without assumptions, the following distinctions between active backend behavior and configured/external dependencies are explicitly defined:

| Capability | Status | Implementation Details & Frontend Integration Guidance |
|---|---|---|
| **Session Authentication** | **Fully Implemented** | Database-backed sessions via `user_sessions`, Argon2id password hashing, HTTP-only cookie `apishield_session`. |
| **CSRF Defense** | **Fully Implemented** | Double-submit CSRF cookie `apishield_csrf` + `X-CSRF-Token` header validated on all state-changing routes (`POST`, `PATCH`, `PUT`, `DELETE`). |
| **Credential Encryption** | **Fully Implemented** | Fernet symmetric 256-bit encryption for saved API auth tokens at rest. Raw credentials are never returned in GET responses. |
| **Anti-SSRF Safe Client** | **Fully Implemented** | DNS resolution validation, socket IP pinning, and private/loopback/cloud metadata filtering for all probe executions. |
| **Background Probe Scheduler** | **Fully Implemented** | Async 5-second polling loop with duplicate claim prevention and lease timeout recovery. |
| **Model Inference & Fallback** | **Fully Implemented** | Active serving model (`model_v20261026_182719`, Random Forest) with transparent fallback to `RuleBasedBaseline`. |
| **SHAP & LIME Explainers** | **Fully Implemented** | Native `shap.TreeExplainer` and `lime.LimeTabularExplainer` with statistical association disclaimers. |
| **Group Fairness Reports** | **Fully Implemented** | Fairlearn `MetricFrame` and IBM AIF360 `BinaryLabelDatasetMetric` across client tiers. |
| **Prometheus & Grafana** | **Fully Implemented** | Prometheus ASGI middleware exporting `/metrics`, provisioned 9-panel Grafana dashboard. |
| **Webhook Delivery** | *Configured Only* | `webhook_url` is stored in the database in `user_settings.settings` schema. Automated outbound HTTP dispatch on alert trigger is an optional external extension point. Alerts are persisted to the database and queried via `/api/v1/alerts`. |
| **AWS SageMaker Adapter** | *Configured Stub* | `app/ml/sagemaker_adapter.py` exists as a structural adapter stub for external cloud pipelines. Production training and serving run natively. |
| **Apache Airflow DAGs** | *Requires WSL / Linux* | `airflow/dags/` contains DAG A (data prep) and DAG B (training). The DAG tasks and callables are unit-tested via pytest in Windows, but running scheduled Airflow cron executions requires WSL2 Ubuntu or a Linux Airflow instance. |
| **Central MLflow Server** | *Configured / Optional* | MLflow tracking uses a self-contained local SQLite Model Registry (`sqlite:///mlruns/mlflow.db`) and fallback JSONL logging. A centralized remote MLflow tracking server is optional via `MLFLOW_TRACKING_URI`. |

### High-Level Architecture & Mermaid Diagram

```mermaid
flowchart TD
    subgraph Client["Frontend Client (Browser / React / Vite)"]
        UI["APIShield Web Application"]
        CookieJar["Browser Cookie Jar\n- apishield_session (HttpOnly)\n- apishield_csrf (Readable)"]
    end

    subgraph Gateway["FastAPI HTTP Application (:8000)"]
        CORSMW["CORS Middleware\n(allow_credentials=True)"]
        ReqIdMW["RequestIdMiddleware\n(X-Request-ID)"]
        PromMW["PrometheusMiddleware\n(/metrics)"]
        CSRFDep["CSRF Verification Dependency\n(X-CSRF-Token header == cookie)"]
        RateLimiter["Sliding-Window Rate Limiter\n(20 req/min per IP)"]
        Router["FastAPI API Router\n(/api/v1)"]
    end

    subgraph CoreServices["Backend Service Layer"]
        AuthSvc["AuthService\n(Argon2id, Session Lifecycle)"]
        ApiSvc["ApiService\n(Fernet Credential Encryption)"]
        TestSvc["TestService & SSRF Guard\n(DNS Validation, IP Pinning)"]
        MonSvc["MonitoringService Scheduler\n(Periodic HTTP Probing)"]
        PredSvc["PredictionService\n(Feature Window, Fallback Gate)"]
        DiagSvc["DiagnosticService\n(Fact Verification & Inference)"]
        AlertSvc["AlertService\n(Fingerprint Cooldown Deduplication)"]
        ReportSvc["ReportService\n(CSV Telemetry Export)"]
    end

    subgraph DataStorage["Persistence & Caching"]
        Postgres[("PostgreSQL 16 DB\n- users\n- user_sessions\n- api_endpoints\n- test_results\n- prediction_records\n- alert_records\n- user_settings")]
        LocalModel["Model Artifacts\n- latest_model.joblib\n- latest_model_meta.json"]
        MLflowDB[("SQLite MLflow Registry\nmlruns/mlflow.db")]
    end

    subgraph MLOpsWorkflows["MLOps & Observability"]
        Airflow["Apache Airflow DAGs\n- Data Prep (@hourly)\n- Model Training (@daily)"]
        DVC["DVC Pipeline\n(dvc.yaml)"]
        Prometheus["Prometheus Server (:9090)"]
        Grafana["Grafana Dashboards (:3000)"]
    end

    UI <-->|HTTP Requests + Cookies| CORSMW
    CORSMW --> ReqIdMW --> PromMW --> CSRFDep --> RateLimiter --> Router

    Router --> AuthSvc
    Router --> ApiSvc
    Router --> TestSvc
    Router --> MonSvc
    Router --> PredSvc
    Router --> DiagSvc
    Router --> AlertSvc
    Router --> ReportSvc

    AuthSvc <--> Postgres
    ApiSvc <--> Postgres
    TestSvc <--> Postgres
    MonSvc <--> Postgres
    PredSvc <--> Postgres
    DiagSvc <--> Postgres
    AlertSvc <--> Postgres
    ReportSvc <--> Postgres

    PredSvc --> LocalModel
    PredSvc --> MLflowDB
    TestSvc -->|Target HTTP Probe| TargetAPI["External Target APIs"]

    Prometheus -->|Scrape /metrics| PromMW
    Grafana -->|Query Metrics| Prometheus
    Airflow -->|Cross-Env CLI Execution| CoreServices
    DVC -->|Data Versioning| Postgres
```

---

## B. Repository Structure & Module Map

```text
backend/
├── .env.example                      # Canonical environment variables template
├── Dockerfile                        # Multi-stage production container build
├── alembic.ini                       # Alembic database migration configuration
├── requirements.txt                  # Production runtime dependencies
├── requirements-dev.txt              # Development & test dependencies
├── dvc.yaml                          # DVC pipeline stages (prepare_dataset, train_model)
│
├── airflow/                          # Apache Airflow integration
│   ├── dags/
│   │   ├── dag_telemetry_prep.py     # DAG: Hourly telemetry extraction and data quality validation
│   │   └── dag_model_training.py     # DAG: Daily training, baseline comparison, and model promotion
│   └── discover_wsl_airflow.sh       # WSL2 discovery & DAG synchronization helper
│
├── app/
│   ├── main.py                       # FastAPI application entrypoint, CORS, exception handlers
│   │
│   ├── api/
│   │   ├── deps.py                   # Dependencies: CurrentUser, DbSession, CsrfProtect, RateLimit
│   │   └── v1/
│   │       ├── router.py             # Route aggregator mounting all sub-routers
│   │       └── endpoints/
│   │           ├── auth.py           # /auth: register, login, me, logout, csrf
│   │           ├── health.py         # /health/live, /health/ready
│   │           ├── apis.py           # /apis: CRUD, test execution, test history
│   │           ├── monitoring.py     # /monitoring/metrics: aggregated time-series telemetry
│   │           ├── predictions.py    # /predictions: inference, history, SHAP/LIME explanation
│   │           ├── diagnostics.py    # /diagnostics/{api_id}: rule-based root cause analysis
│   │           ├── alerts.py         # /alerts: persistent alerts and status patch
│   │           ├── reports.py        # /reports/summary, /reports/export-csv
│   │           ├── settings.py       # /settings: user threshold & cooldown preferences
│   │           └── ml.py             # /ml: experiments, models, serving status, training, fairness
│   │
│   ├── core/
│   │   ├── config.py                 # Pydantic BaseSettings, strict production secret validators
│   │   ├── errors.py                 # Standardized AppException hierarchy
│   │   ├── logging.py                # Redacting structured logger (masks tokens, credentials, cookies)
│   │   ├── metrics.py                # Prometheus metric counters, gauges, histograms & ASGI middleware
│   │   ├── middleware.py             # RequestIdMiddleware, RateLimiter, validate_csrf_for_request
│   │   └── security.py               # Argon2id password hashing, Fernet symmetric encryption, CSRF tokens
│   │
│   ├── db/
│   │   ├── base.py                   # SQLAlchemy 2.x DeclarativeBase
│   │   └── session.py                # Engine initialization, get_db session generator, check_db_ready
│   │
│   ├── ml/
│   │   ├── features.py               # Chronological tabular feature extractor (15 features)
│   │   ├── dataset.py                # Telemetry dataset builder with leakage prevention & purge gap
│   │   ├── candidate_evaluator.py    # Isolated candidate model evaluation without production promotion
│   │   ├── model.py                  # RuleBasedBaseline, ModelTrainer (RandomForest), promotion gate
│   │   ├── provenance.py             # PredictionProvenance enum (trained_model, rules_baseline, demo)
│   │   ├── diagnostics.py            # DiagnosticEngine (latency, timeout, 4xx, 5xx analysis)
│   │   ├── explainability.py         # ModelExplainer (native shap.TreeExplainer & lime.LimeTabularExplainer)
│   │   ├── fairness.py               # Group fairness evaluation (Fairlearn & IBM AIF360)
│   │   ├── mlflow_tracker.py         # MLflow Tracking & SQLite Model Registry wrapper
│   │   ├── pipeline.py               # CLI pipeline entrypoints (prepare, train, evaluate)
│   │   └── sagemaker_adapter.py      # AWS SageMaker compatibility stub
│   │
│   ├── models/                       # SQLAlchemy ORM persistent entities
│   │   ├── user.py                   # User model
│   │   ├── session.py                # UserSession model (active cookie tokens)
│   │   ├── api.py                    # ApiEndpoint model (configurations, credentials, thresholds)
│   │   ├── test_result.py            # TestResultRecord model (probe results, assertions)
│   │   └── ml.py                     # PredictionRecord, AlertRecord, SettingRecord
│   │
│   ├── schemas/                      # Pydantic validation and serialization models
│   │   ├── auth.py                   # UserRegisterRequest, UserLoginRequest, UserResponse, CsrfResponse
│   │   ├── api.py                    # ApiEndpointInput, ApiEndpointUpdate, ApiEndpointResponse
│   │   ├── testing.py                # TestRequestSchema, TestResultResponse, ValidationResultSchema
│   │   ├── monitoring.py             # MetricPoint, TimeRange
│   │   ├── ml.py                     # PredictionResponse, DiagnosticReport, AlertResponse, UserSettings
│   │   └── error.py                  # Standard ErrorDetail and ErrorResponse envelope
│   │
│   └── services/                     # Business logic layer
│       ├── auth_service.py           # User registration, password verification, session DB persistence
│       ├── api_service.py            # API configuration CRUD, Fernet encryption/decryption
│       ├── test_service.py           # Ad-hoc & saved API execution, anti-SSRF enforcement
│       ├── monitoring_service.py     # Background async HTTP probing scheduler
│       ├── metrics_service.py        # Bucket aggregation of time-series monitoring metrics
│       ├── prediction_service.py     # Active model loading, fallback gate, risk persistence
│       ├── diagnostic_service.py     # Root cause evaluation and recommendations
│       ├── alert_service.py          # Alert triggering, fingerprinting, and status updates
│       ├── report_service.py         # Monitoring summary computation and CSV generation
│       └── settings_service.py       # User setting management with safe defaults
│
├── artifacts/
│   ├── models/
│   │   ├── latest_model.joblib       # Active production Random Forest model artifact
│   │   └── latest_model_meta.json    # Model metadata (model_version: model_v20261026_182719)
│   └── experimental/
│       ├── candidate_model.joblib    # Isolated candidate model artifact
│       └── candidate_evaluation_report.json # Candidate evaluation metrics & split breakdown
│
├── data/
│   ├── telemetry_dataset.json        # Production dataset (50 samples, status: ready)
│   └── experimental_telemetry_dataset.json # Experimental dataset (800 raw observations, 785 purged samples)
│
├── migrations/                       # Alembic migrations
│   └── versions/
│       ├── 0001_initial_user_and_session.py
│       ├── 0002_api_and_test_history.py
│       ├── 0003_monitoring_and_metric_indexes.py
│       └── 0004_predictions_alerts_settings.py
│
├── monitoring/
│   ├── prometheus.yml                # Prometheus scraping configuration (scrape_interval: 10s)
│   └── grafana/
│       ├── provisioning/             # Datasource and dashboard providers
│       └── dashboards/
│           └── apishield-overview.json # Provisioned 9-panel Grafana dashboard
│
└── tests/                            # 141 automated unit, integration, and security tests
```

---

## C. Local Setup & Execution Guide

### Prerequisites & Supported Runtimes

- **Python Runtime:** Python 3.11, 3.12, or 3.13 (Python 3.13.14 verified with 100% test pass rate).
- **PostgreSQL Database:** PostgreSQL 14, 15, or 16 (or local SQLite for automated testing).
- **Package Manager:** `pip` version 23.0+.
- **Optional Tools:** Docker & Docker Compose (for complete stack execution), WSL2 Ubuntu (if executing Airflow DAGs).

### Virtual Environment Setup (Windows & POSIX)

#### On Windows (PowerShell)

```powershell
# Navigate to the backend directory
cd D:\College\3rd_Year\MLOPS\CP\backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements-dev.txt
```

#### On Linux / macOS / WSL2

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

### Environment Configuration (.env)

The application requires a `.env` file in the `backend/` root. Copy the provided `.env.example`:

```bash
cp .env.example .env
```

Ensure the following variables are defined (see [Section K](#k-environment-configuration-reference) for the complete reference):

```ini
ENVIRONMENT=development
DEBUG=false
APP_HOST=0.0.0.0
APP_PORT=8000

# Secret key for session hashing (minimum 32 characters)
SECRET_KEY=apishield-dev-secret-key-change-in-production-min32chars

# Fernet 32-byte urlsafe base64 key for encrypting stored credentials at rest
CREDENTIALS_ENCRYPTION_KEY=vME3wCp5mpWfOD-IFGp1koWNHgtnGUKnY00-_-WDAEE=

# Database URL
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/apishield
DATABASE_ECHO=false

# Allowed CORS origins
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173

# Security & Scheduler
AUTH_RATE_LIMIT_PER_MINUTE=20
MONITORING_ENABLED=true
MONITORING_TICK_SECONDS=5
MONITORING_MAX_CONCURRENCY=10
```

> [!WARNING]
> In `ENVIRONMENT=production`, the application strictly rejects default development keys, keys containing substrings like `change-in-production` or `dev-secret`, and low-entropy secrets. Always generate high-entropy keys for production deployments.

### Database Migrations (Alembic)

Initialize or upgrade the PostgreSQL schema to the latest revision:

```bash
# Apply all migrations
alembic upgrade head

# Verify migration status
alembic current
```

*Applied migration revisions:*
- `0001_initial_user_and_session`: Creates `users` and `user_sessions` tables.
- `0002_api_and_test_history`: Creates `api_endpoints` and `test_results` tables.
- `0003_monitoring_and_metric_indexes`: Adds next check, lease expiration, and compound telemetry indexes.
- `0004_predictions_alerts_settings`: Creates `prediction_records`, `alert_records`, and `user_settings` tables.

### Running the Backend Locally

Start the ASGI server with Uvicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The application will bind to `http://localhost:8000`. On startup, it checks database availability and launches the background probe scheduler (unless `ENVIRONMENT=testing`).

### Running the Docker Compose Stack

The full containerized stack is defined in `../docker-compose.yml` (located in the project root):

```bash
# From the project root (D:\College\3rd_Year\MLOPS\CP)
docker compose up -d --build
```

#### Services Started by Docker Compose

| Service Container | Image / Build | Port Binding | Description |
|---|---|---|---|
| `apishield-postgres` | `postgres:16-alpine` | `5432:5432` | Primary PostgreSQL database with persistent volume |
| `apishield-backend` | `./backend/Dockerfile` | `8000:8000` | FastAPI application, Alembic auto-upgrade, and scheduler |
| `apishield-prometheus` | `prom/prometheus:v2.51.0` | `9090:9090` | Observability scraper targeting `/metrics` |
| `apishield-grafana` | `grafana/grafana:10.4.0` | `3000:3000` | Pre-provisioned dashboards for latency, errors & requests |

To check logs and status:

```bash
docker compose ps
docker compose logs -f backend
```

To shut down:

```bash
docker compose down
```

### Accessing Observability

When running locally or via Docker:

- **Swagger UI Interactive Docs:** [http://localhost:8000/docs](http://localhost:8000/docs) *(disabled in `ENVIRONMENT=production`)*
- **ReDoc Interactive Docs:** [http://localhost:8000/redoc](http://localhost:8000/redoc) *(disabled in `ENVIRONMENT=production`)*
- **OpenAPI Schema (JSON):** [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)
- **Liveness Health Check:** [http://localhost:8000/health/live](http://localhost:8000/health/live)
- **Readiness Health Check:** [http://localhost:8000/health/ready](http://localhost:8000/health/ready)
- **Prometheus Raw Metrics:** [http://localhost:8000/metrics](http://localhost:8000/metrics)
- **Prometheus UI:** [http://localhost:9090](http://localhost:9090)
- **Grafana Dashboard UI:** [http://localhost:3000](http://localhost:3000) *(Default credentials: `admin` / `admin`)*

### Troubleshooting Startup Failures

1. **`ValueError: SECRET_KEY must be at least 32 characters long.`**
   - Ensure `SECRET_KEY` in `.env` contains at least 32 characters.
2. **`ValueError: CREDENTIALS_ENCRYPTION_KEY must be a valid 32-byte base64-encoded Fernet key`**
   - Generate a valid key using: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and set it in `.env`.
3. **`OperationalError: connection to server at "localhost" failed`**
   - Verify PostgreSQL is running on port 5432 and the credentials match `DATABASE_URL`.
   - Run `alembic upgrade head` after starting PostgreSQL.
4. **`HTTP 503 Service Unavailable` on `/health/ready`**
   - The process is alive, but the database connection failed `SELECT 1`. Check database server health and connection strings.
5. **CORS errors in browser (`Access-Control-Allow-Origin missing`)**
   - Ensure your frontend origin (e.g. `http://localhost:5173`) is listed in `CORS_ORIGINS` in `.env`.
   - Ensure the frontend sends `credentials: 'include'` (Fetch) or `withCredentials: true` (Axios).

---

## D. API Reference & Contract Specification

### Complete Endpoint Inventory Table

The backend registers exactly **37 unique HTTP method/path combinations** across the application (36 registered in the OpenAPI specification, plus the root `/metrics` Prometheus exposition endpoint).

The routes are organized into 11 functional groups:

| # | HTTP Method | Route Path | Route Group | Auth Required | CSRF Required | Rate Limited |
|---|---|---|---|---|---|---|
| 1 | `POST` | `/api/v1/auth/register` | Authentication | Public | No | **Yes** (20/min) |
| 2 | `POST` | `/api/v1/auth/login` | Authentication | Public | No | **Yes** (20/min) |
| 3 | `GET` | `/api/v1/auth/me` | Authentication | **Yes** (Cookie) | No | No |
| 4 | `POST` | `/api/v1/auth/logout` | Authentication | **Yes** (Cookie) | **Yes** | No |
| 5 | `GET` | `/api/v1/auth/csrf` | Authentication | Public | No | No |
| 6 | `GET` | `/health/live` | Health & Readiness | Public | No | No |
| 7 | `GET` | `/health/ready` | Health & Readiness | Public | No | No |
| 8 | `GET` | `/api/v1/health/live` | Health & Readiness | Public | No | No |
| 9 | `GET` | `/api/v1/health/ready` | Health & Readiness | Public | No | No |
| 10 | `GET` | `/metrics` | Health & Readiness | Public | No | No |
| 11 | `GET` | `/api/v1/apis` | Saved APIs | **Yes** (Cookie) | No | No |
| 12 | `POST` | `/api/v1/apis` | Saved APIs | **Yes** (Cookie) | **Yes** | No |
| 13 | `GET` | `/api/v1/apis/{api_id}` | Saved APIs | **Yes** (Cookie) | No | No |
| 14 | `PATCH` | `/api/v1/apis/{api_id}` | Saved APIs | **Yes** (Cookie) | **Yes** | No |
| 15 | `DELETE`| `/api/v1/apis/{api_id}` | Saved APIs | **Yes** (Cookie) | **Yes** | No |
| 16 | `POST` | `/api/v1/apis/adhoc/test` | API Testing | **Yes** (Cookie) | **Yes** | No |
| 17 | `POST` | `/api/v1/apis/{api_id}/test` | API Testing | **Yes** (Cookie) | **Yes** | No |
| 18 | `GET` | `/api/v1/apis/{api_id}/history` | API Testing | **Yes** (Cookie) | No | No |
| 19 | `GET` | `/api/v1/monitoring/metrics` | Monitoring | **Yes** (Cookie) | No | No |
| 20 | `POST` | `/api/v1/predictions/{api_id}/predict` | Predictions | **Yes** (Cookie) | **Yes** | No |
| 21 | `GET` | `/api/v1/predictions` | Predictions | **Yes** (Cookie) | No | No |
| 22 | `GET` | `/api/v1/predictions/{id}` | Predictions | **Yes** (Cookie) | No | No |
| 23 | `GET` | `/api/v1/predictions/{id}/explanation` | Predictions | **Yes** (Cookie) | No | No |
| 24 | `GET` | `/api/v1/diagnostics/{api_id}` | Diagnostics | **Yes** (Cookie) | No | No |
| 25 | `GET` | `/api/v1/alerts` | Alerts | **Yes** (Cookie) | No | No |
| 26 | `PATCH` | `/api/v1/alerts/{id}/status` | Alerts | **Yes** (Cookie) | **Yes** | No |
| 27 | `GET` | `/api/v1/reports/summary` | Reports | **Yes** (Cookie) | No | No |
| 28 | `GET` | `/api/v1/reports/export-csv` | Reports | **Yes** (Cookie) | No | No |
| 29 | `GET` | `/api/v1/settings` | Settings | **Yes** (Cookie) | No | No |
| 30 | `PUT` | `/api/v1/settings` | Settings | **Yes** (Cookie) | **Yes** | No |
| 31 | `GET` | `/api/v1/ml/models/serving` | MLOps & Model Reg. | **Yes** (Cookie) | No | No |
| 32 | `GET` | `/api/v1/ml/experiments` | MLOps & Model Reg. | **Yes** (Cookie) | No | No |
| 33 | `GET` | `/api/v1/ml/experiments/{run_id}` | MLOps & Model Reg. | **Yes** (Cookie) | No | No |
| 34 | `GET` | `/api/v1/ml/models` | MLOps & Model Reg. | **Yes** (Cookie) | No | No |
| 35 | `GET` | `/api/v1/ml/models/{model_name}/versions`| MLOps & Model Reg. | **Yes** (Cookie) | No | No |
| 36 | `POST` | `/api/v1/ml/training-runs` | MLOps & Model Reg. | **Yes** (Cookie) | **Yes** | No |
| 37 | `GET` | `/api/v1/ml/fairness-reports` | MLOps & Model Reg. | **Yes** (Cookie) | No | No |

*(Note: Routes 6–7 and 8–9 are the dual root and versioned health checks, providing identical status responses).*

---

### Standard Error Envelope

All API errors return a uniform JSON error envelope with HTTP status codes:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request could not be processed due to validation errors.",
    "fieldErrors": {
      "name": "API name cannot be blank.",
      "url": "URL must start with http:// or https://"
    },
    "requestId": "4f50937c-d64e-4f51-a9f4-1219b160be1c"
  }
}
```

- `code` *(string)*: Machine-readable code (e.g., `UNAUTHORIZED`, `CONFLICT`, `NOT_FOUND`, `CSRF_ERROR`, `RATE_LIMITED`, `SSRF_BLOCKED`, `VALIDATION_ERROR`, `INTERNAL_SERVER_ERROR`).
- `message` *(string)*: Human-readable explanation.
- `fieldErrors` *(object)*: Map of field paths to specific error strings (empty `{}` for non-validation errors).
- `requestId` *(string)*: UUID correlation token propagated via the `X-Request-ID` HTTP header.

---

### Route Group 1: Authentication & Session Management

#### 1. `POST /api/v1/auth/register`
- **Purpose:** Register a new user account with Argon2id password hashing.
- **Auth:** Public.
- **Rate Limit:** 20 requests per minute per IP.
- **Request Body (`UserRegisterRequest`):**
  ```json
  {
    "name": "Jane Developer",
    "email": "jane@example.com",
    "password": "SecurePassword123!"
  }
  ```
  *Validation:* `name` (2–100 chars), `email` (valid email regex), `password` (8–128 chars).
- **Response (HTTP 201 Created — `UserResponse`):**
  ```json
  {
    "id": "e83cf13d-5dae-4e44-b0cf-5cfb11f5e27a",
    "name": "Jane Developer",
    "email": "jane@example.com",
    "role": "developer"
  }
  ```
- **Errors:**
  - `409 Conflict` (`code: "CONFLICT"`): Email is already registered.
  - `422 Unprocessable Entity` (`code: "VALIDATION_ERROR"`): Name, email, or password failed length/format rules.
  - `429 Too Many Requests` (`code: "RATE_LIMITED"`): Exceeded 20 requests/minute.

---

#### 2. `POST /api/v1/auth/login`
- **Purpose:** Authenticate credentials and issue secure session cookies. Prevents session fixation by generating a new session ID on each successful authentication.
- **Auth:** Public.
- **Rate Limit:** 20 requests per minute per IP.
- **Request Body (`UserLoginRequest`):**
  ```json
  {
    "email": "jane@example.com",
    "password": "SecurePassword123!"
  }
  ```
- **Response (HTTP 200 OK — `UserResponse`):**
  ```json
  {
    "id": "e83cf13d-5dae-4e44-b0cf-5cfb11f5e27a",
    "name": "Jane Developer",
    "email": "jane@example.com",
    "role": "developer"
  }
  ```
- **Side Effects (Response Headers & Cookies):**
  - Sets cookie `apishield_session=<raw_token>; HttpOnly; Path=/; Max-Age=86400; SameSite=Lax`.
  - Sets cookie `apishield_csrf=<csrf_token>; Path=/; Max-Age=86400; SameSite=Lax` (client-readable).
  - Sets header `X-CSRF-Token: <csrf_token>`.
  - Persists hashed session token (`SHA-256`) in database table `user_sessions`.
- **Errors:**
  - `401 Unauthorized` (`code: "INVALID_CREDENTIALS"`): Email not found or password incorrect.
  - `429 Too Many Requests` (`code: "RATE_LIMITED"`).

---

#### 3. `GET /api/v1/auth/me`
- **Purpose:** Retrieve the profile of the currently authenticated user.
- **Auth:** Session cookie (`apishield_session`).
- **Request:** No body or query parameters.
- **Response (HTTP 200 OK — `UserResponse`):**
  ```json
  {
    "id": "e83cf13d-5dae-4e44-b0cf-5cfb11f5e27a",
    "name": "Jane Developer",
    "email": "jane@example.com",
    "role": "developer"
  }
  ```
- **Errors:**
  - `401 Unauthorized` (`code: "UNAUTHORIZED"`): Missing, invalid, or expired session cookie.

---

#### 4. `POST /api/v1/auth/logout`
- **Purpose:** Invalidate the active database session and clear authentication cookies.
- **Auth:** Session cookie (`apishield_session`).
- **CSRF Required:** **Yes** (Header `X-CSRF-Token` must match cookie `apishield_csrf`).
- **Request:** No body.
- **Response (HTTP 200 OK):**
  ```json
  {
    "message": "Logged out successfully."
  }
  ```
- **Side Effects:**
  - Deletes active row in `user_sessions`.
  - Sends expired deletion headers for cookies `apishield_session` and `apishield_csrf`.
- **Errors:**
  - `401 Unauthorized` (`code: "UNAUTHORIZED"`).
  - `403 Forbidden` (`code: "CSRF_ERROR"`): Missing or mismatched CSRF token.

---

#### 5. `GET /api/v1/auth/csrf`
- **Purpose:** Supply a fresh CSRF token and set the `apishield_csrf` cookie for client consumption.
- **Auth:** Public.
- **Response (HTTP 200 OK — `CsrfResponse`):**
  ```json
  {
    "csrfToken": "1894b9ca0d5402df9c4dcb7c638d975ab457788472da493cf0e87b7a9561debc"
  }
  ```
- **Side Effects:** Sets `apishield_csrf` cookie and `X-CSRF-Token` response header.

---

### Route Group 2: System Health & Readiness

#### 6. `GET /health/live`
- **Purpose:** Root process liveness probe confirming the ASGI process is executing and responding. Independent of external database state. Recommended for container liveness health checks (e.g. Docker `HEALTHCHECK`).
- **Auth:** Public.
- **Response (HTTP 200 OK):**
  ```json
  {
    "status": "live",
    "timestamp": "2026-10-27T05:40:00.000000+00:00"
  }
  ```

---

#### 7. `GET /health/ready`
- **Purpose:** Root system readiness probe verifying that runtime dependencies (PostgreSQL database) are operational via `SELECT 1`. Never exposes internal connection strings or credentials.
- **Auth:** Public.
- **Response When Healthy (HTTP 200 OK):**
  ```json
  {
    "status": "ready",
    "database": "connected",
    "timestamp": "2026-10-27T05:40:00.000000+00:00"
  }
  ```
- **Response When Degraded / Disconnected (HTTP 503 Service Unavailable):**
  ```json
  {
    "status": "not_ready",
    "database": "disconnected",
    "timestamp": "2026-10-27T05:40:00.000000+00:00"
  }
  ```

---

#### 8. `GET /api/v1/health/live`
- **Purpose:** Versioned alias of the process liveness check, mounted under `/api/v1` for frontend clients standardizing all backend calls under the API prefix. Identical implementation to `/health/live`.
- **Auth:** Public.
- **Response (HTTP 200 OK):** Same schema as `/health/live`.

---

#### 9. `GET /api/v1/health/ready`
- **Purpose:** Versioned alias of the system readiness check, mounted under `/api/v1`. Checks PostgreSQL database operational status. Identical implementation to `/health/ready`.
- **Auth:** Public.
- **Response (HTTP 200 OK when ready, HTTP 503 when degraded):** Same schema as `/health/ready`.

---

#### 10. `GET /metrics`
- **Purpose:** Prometheus exposition format scraping endpoint (managed by `PrometheusMiddleware`). Excluded from OpenAPI schema via `include_in_schema=False`.
- **Auth:** Public.
- **Response (HTTP 200 OK, `text/plain`):**
  Prometheus metrics exposition with metric descriptions, labels, and types.

---

### Route Group 3: Saved API Configuration & Management

> [!NOTE]
> All API endpoint schemas inherit from `BaseCamelModel`, meaning the backend automatically accepts both camelCase and snake_case on input, and **always serializes responses in camelCase**.

#### 11. `GET /api/v1/apis`
- **Purpose:** List all saved API endpoints owned by the authenticated user.
- **Auth:** Session cookie.
- **Response (HTTP 200 OK — `List[ApiEndpointResponse]`):**
  ```json
  [
    {
      "id": "78201a09-9602-4fc8-80f4-5544cfb9cb74",
      "name": "Payment Gateway Health",
      "url": "https://api.stripe.com/v1/health",
      "method": "GET",
      "queryParams": [],
      "headers": [
        { "key": "Accept", "value": "application/json" }
      ],
      "authType": "none",
      "hasSecret": false,
      "body": null,
      "expectedStatus": 200,
      "validationRule": null,
      "timeoutMs": 5000,
      "intervalSec": 60,
      "maxLatencyMs": 1000,
      "errorRateThreshold": 5.0,
      "expectedAvailability": 99.0,
      "riskThreshold": 70.0,
      "monitoring": true,
      "health": "healthy",
      "lastStatusCode": 200,
      "lastLatencyMs": 142.5,
      "lastCheckedAt": "2026-10-27T05:35:10.123456+00:00",
      "risk": "low",
      "riskScore": 12.0,
      "createdAt": "2026-10-26T18:00:00.000000+00:00"
    }
  ]
  ```

---

#### 12. `POST /api/v1/apis`
- **Purpose:** Create a new saved API endpoint. Encrypts sensitive secrets (Bearer tokens, API keys) at rest using Fernet.
- **Auth:** Session cookie.
- **CSRF Required:** **Yes**.
- **Request Body (`ApiEndpointInput`):**
  ```json
  {
    "name": "Auth Service Probe",
    "url": "https://auth.example.com/v1/status",
    "method": "GET",
    "queryParams": [
      { "key": "env", "value": "production" }
    ],
    "headers": [
      { "key": "X-Client", "value": "APIShield" }
    ],
    "authType": "bearer",
    "secret": "secret_token_value_to_encrypt",
    "body": null,
    "expectedStatus": 200,
    "validationRule": "status==ok",
    "timeoutMs": 10000,
    "intervalSec": 60,
    "maxLatencyMs": 1000,
    "errorRateThreshold": 5.0,
    "expectedAvailability": 99.0,
    "riskThreshold": 70.0,
    "monitoring": true
  }
  ```
  *Validation:* `url` must start with `http://` or `https://`. `name` cannot be blank. `timeoutMs` (500–30000). `intervalSec` (5–86400). `body` max 1MB.
- **Response (HTTP 201 Created — `ApiEndpointResponse`):**
  Returns the created record. Note `hasSecret: true` is returned; the raw secret is never echoed back in the response.

---

#### 13. `GET /api/v1/apis/{api_id}`
- **Purpose:** Retrieve configuration details for a specific API endpoint owned by the authenticated user.
- **Auth:** Session cookie.
- **Path Parameter:** `api_id` *(string UUID)*.
- **Response (HTTP 200 OK — `ApiEndpointResponse`):**
  Endpoint details. Returns `404 Not Found` if the API does not exist or belongs to another user.

---

#### 14. `PATCH /api/v1/apis/{api_id}`
- **Purpose:** Partially update configuration, thresholds, or credentials for a saved API endpoint.
- **Auth:** Session cookie.
- **CSRF Required:** **Yes**.
- **Request Body (`ApiEndpointUpdate`):**
  Any subset of `ApiEndpointInput` fields. Pass `"secret": "new_value"` to re-encrypt a new credential.
- **Response (HTTP 200 OK — `ApiEndpointResponse`):** Updated record.

---

#### 15. `DELETE /api/v1/apis/{api_id}`
- **Purpose:** Delete a saved API endpoint and cascade-delete its test results, predictions, and alerts.
- **Auth:** Session cookie.
- **CSRF Required:** **Yes**.
- **Response (HTTP 204 No Content):** Empty body.
- **Errors:** `404 Not Found`.

---

### Route Group 4: Ad-Hoc & Saved API Testing

#### 16. `POST /api/v1/apis/adhoc/test`
- **Purpose:** Execute an immediate test request against an arbitrary URL without saving the API configuration first. Strictly applies anti-SSRF protections, evaluates response assertions, and records test telemetry.
- **Auth:** Session cookie.
- **CSRF Required:** **Yes**.
- **Request Body (`TestRequestSchema`):**
  ```json
  {
    "url": "https://httpbin.org/get",
    "method": "GET",
    "queryParams": [{ "key": "test", "value": "1" }],
    "headers": [{ "key": "Accept", "value": "application/json" }],
    "authType": "none",
    "secret": null,
    "body": null,
    "expectedStatus": 200,
    "validationRule": null,
    "timeoutMs": 5000
  }
  ```
- **Response (HTTP 200 OK — `TestResultResponse`):**
  ```json
  {
    "id": "2d8f9c0e-43a1-432d-9eb5-8e1efd630012",
    "apiId": null,
    "passed": true,
    "outcome": "success",
    "statusCode": 200,
    "expectedStatus": 200,
    "latencyMs": 182.4,
    "headers": [
      { "key": "content-type", "value": "application/json" }
    ],
    "body": "{\"args\":{\"test\":\"1\"}}",
    "validations": [],
    "error": null,
    "testedAt": "2026-10-27T05:42:15.123456+00:00",
    "simulated": false
  }
  ```
- **Security Rejections (HTTP 400 Bad Request — `code: "SSRF_BLOCKED"`):**
  Triggered if the target resolves to loopback (`127.0.0.1`), private IP ranges (`10.0.0.0/8`, `192.168.0.0/16`, `172.16.0.0/12`), link-local/cloud metadata (`169.254.169.254`), or alternate hex/octal representations.

---

#### 17. `POST /api/v1/apis/{api_id}/test`
- **Purpose:** Execute a test probe against an existing saved API endpoint. Automatically decrypts credentials, executes the request through the anti-SSRF safe transport, evaluates status and assertions, updates `last_checked_at`, `health`, and `last_latency_ms` on the API record, and persists the `test_results` record.
- **Auth:** Session cookie.
- **CSRF Required:** **Yes**.
- **Response (HTTP 200 OK — `TestResultResponse`):**
  Test execution outcome matching the schema above with `apiId` populated.

---

#### 18. `GET /api/v1/apis/{api_id}/history`
- **Purpose:** Retrieve chronologically ordered execution history for a saved API.
- **Auth:** Session cookie.
- **Query Parameter:** `limit` *(int, default: 50, min: 1, max: 100)*.
- **Response (HTTP 200 OK — `List[TestResultResponse]`):**
  List of test executions ordered descending by `testedAt`.

---

### Route Group 5: Time-Series Monitoring & Metrics

#### 19. `GET /api/v1/monitoring/metrics`
- **Purpose:** Retrieve aggregated time-series metric buckets for rendering frontend charts (latency, request counts, 4xx/5xx error rates, availability).
- **Auth:** Session cookie.
- **Query Parameters:**
  - `apiId` *(string, optional)*: Specific API UUID. Omit or pass `"all"` to aggregate across all APIs owned by the user.
  - `api_id` *(string, optional)*: Alias for `apiId`.
  - `range` *(string, default: `"24h"`)*: Allowed values: `"1h"`, `"6h"`, `"24h"`, `"7d"`.
- **Response (HTTP 200 OK — `List[MetricPoint]`):**
  ```json
  [
    {
      "t": "2026-10-27T04:00:00+00:00",
      "avgLatency": 145.2,
      "p95Latency": 210.0,
      "requests": 12,
      "errorRate4xx": 0.0,
      "errorRate5xx": 8.3,
      "errorRate": 8.3,
      "timeouts": 0,
      "availability": 91.7
    },
    {
      "t": "2026-10-27T05:00:00+00:00",
      "avgLatency": 138.0,
      "p95Latency": 185.0,
      "requests": 14,
      "errorRate4xx": 0.0,
      "errorRate5xx": 0.0,
      "errorRate": 0.0,
      "timeouts": 0,
      "availability": 100.0
    }
  ]
  ```
  *Note:* Returns cleanly formatted zeroed points if the database contains no observations for the interval.

---

### Route Group 6: Failure Risk Predictions & Explainability

#### 20. `POST /api/v1/predictions/{api_id}/predict`
- **Purpose:** Run machine learning failure risk inference on an API endpoint using the active model `model_v20261026_182719` or transparent baseline fallback.
- **Auth:** Session cookie.
- **CSRF Required:** **Yes**.
- **Query Parameters:**
  - `is_demo` *(bool, default: `false`)*: When `true`, flags provenance as `"demo"`.
  - `explain_method` *(string, default: `"shap"`)*: Choice of explainer: `"shap"`, `"lime"`, or `"heuristic"`.
- **Response (HTTP 200 OK — `PredictionResponse`):**
  ```json
  {
    "id": "5f3a09b2-32b4-4b52-9bc5-e8d1fa98124b",
    "api_id": "78201a09-9602-4fc8-80f4-5544cfb9cb74",
    "risk_score": 78.5,
    "risk_level": "high",
    "prediction": 1,
    "provenance": "trained_model",
    "model_version": "model_v20261026_182719",
    "features": {
      "avg_latency_ms": 420.5,
      "p95_latency_ms": 950.0,
      "p50_latency_ms": 380.0,
      "std_latency_ms": 110.2,
      "max_latency_ms": 1200.0,
      "latency_trend": 1.8,
      "error_rate": 20.0,
      "timeout_rate": 6.7,
      "http_4xx_rate": 0.0,
      "http_5xx_rate": 20.0,
      "availability": 80.0,
      "recent_consecutive_failures": 2.0,
      "total_observations": 15.0,
      "hour_of_day": 5.0,
      "day_of_week": 1.0
    },
    "explanation": {
      "method": "shap_tree_attribution",
      "is_fallback": false,
      "base_value": 0.15,
      "contributions": {
        "http_5xx_rate": 0.32,
        "recent_consecutive_failures": 0.25,
        "latency_trend": 0.18,
        "error_rate": 0.12
      },
      "disclaimer": "Feature attributions reflect statistical associations and model score weights, not real-world causal failure mechanics."
    },
    "inference_duration_ms": 12.4,
    "created_at": "2026-10-27T05:45:00.000000+00:00"
  }
  ```
  *Frontend Interpretation:*
  - `risk_score` (0.0 to 100.0): Overall estimated probability/severity of failure in the next observation window.
  - `risk_level`: `"low"` (< 35.0), `"medium"` (35.0-69.9), `"high"` (70.0-84.9), `"critical"` (>= 85.0).
  - `prediction`: `0` (Healthy), `1` (Failure Risk).
  - `provenance`: `"trained_model"` (Random Forest active), `"rules_baseline"` (heuristic fallback), `"demo"` (explicit demo probe).

---

#### 21. `GET /api/v1/predictions`
- **Purpose:** List paginated prediction history for the authenticated user.
- **Auth:** Session cookie.
- **Query Parameters:**
  - `api_id` *(string, optional)*: Filter by target API.
  - `provenance` *(string, optional)*: Filter by provenance (`"trained_model"`, `"rules_baseline"`, `"demo"`).
  - `limit` *(int, default: 50, min: 1, max: 200)*.
  - `offset` *(int, default: 0, min: 0)*.
- **Response (HTTP 200 OK — `PredictionHistoryResponse`):**
  ```json
  {
    "total": 42,
    "items": [ /* List of PredictionResponse objects */ ],
    "limit": 50,
    "offset": 0
  }
  ```

---

#### 22. `GET /api/v1/predictions/{id}`
- **Purpose:** Retrieve a single persisted prediction record by ID.
- **Auth:** Session cookie.
- **Response (HTTP 200 OK — `PredictionResponse`):** Single prediction record.

---

#### 23. `GET /api/v1/predictions/{id}/explanation`
- **Purpose:** Dynamically compute or re-evaluate an explanation (SHAP, LIME, or heuristic) for an existing prediction record.
- **Auth:** Session cookie.
- **Query Parameter:** `method` *(string, default: `"shap"`, pattern: `^(shap|lime|heuristic)$`)*.
- **Response (HTTP 200 OK):**
  ```json
  {
    "prediction_id": "5f3a09b2-32b4-4b52-9bc5-e8d1fa98124b",
    "api_id": "78201a09-9602-4fc8-80f4-5544cfb9cb74",
    "risk_score": 78.5,
    "provenance": "trained_model",
    "requested_method": "lime",
    "explanation": {
      "method": "lime_tabular_surrogate",
      "is_fallback": false,
      "intercept": 0.22,
      "contributions": {
        "http_5xx_rate > 10.00": 0.35,
        "recent_consecutive_failures > 1.00": 0.22
      },
      "disclaimer": "Feature attributions reflect statistical associations and model score weights, not real-world causal failure mechanics."
    }
  }
  ```

---

### Route Group 7: Root-Cause Diagnostics

#### 24. `GET /api/v1/diagnostics/{api_id}`
- **Purpose:** Run rule-based root cause analysis across telemetry facts (timeouts, latency spikes, 4xx client errors, 5xx server errors, availability drops) and deliver concrete remediations.
- **Auth:** Session cookie.
- **Response (HTTP 200 OK — `DiagnosticReport`):**
  ```json
  {
    "api_id": "78201a09-9602-4fc8-80f4-5544cfb9cb74",
    "api_name": "Payment Gateway Health",
    "time_window": "Recent 50 observations",
    "overall_status": "degraded",
    "findings": [
      {
        "category": "5xx_errors",
        "severity": "critical",
        "certainty": "confirmed_fact",
        "title": "Severe HTTP 5xx Server Error Surge",
        "evidence": {
          "http_5xx_rate": 22.5,
          "error_count": 9,
          "total_observations": 40
        },
        "recommendation": "Inspect server logs for unhandled 500 exceptions, database lockups, or upstream dependency timeouts."
      }
    ],
    "summary": "1 critical issues detected across 40 telemetry observations.",
    "generated_at": "2026-10-27T05:46:12.000000+00:00"
  }
  ```

---

### Route Group 8: Alerts & Incident Lifecycle

#### 25. `GET /api/v1/alerts`
- **Purpose:** List alerts for the authenticated user with optional status and API filtering.
- **Auth:** Session cookie.
- **Query Parameters:**
  - `status` *(string, optional)*: Filter by `"open"`, `"acknowledged"`, or `"resolved"`.
  - `api_id` *(string, optional)*: Filter by API endpoint.
  - `limit` *(int, default: 50, min: 1, max: 200)*.
  - `offset` *(int, default: 0, min: 0)*.
- **Response (HTTP 200 OK — `AlertListResponse`):**
  ```json
  {
    "total": 3,
    "items": [
      {
        "id": "18f0a912-421d-4871-9bb1-382a1e09bc42",
        "api_id": "78201a09-9602-4fc8-80f4-5544cfb9cb74",
        "title": "High Failure Risk Detected",
        "description": "Risk score reached 78.5% (high) based on elevated 5xx error rates.",
        "severity": "critical",
        "status": "open",
        "source": "prediction",
        "fingerprint": "a9f82d1...",
        "created_at": "2026-10-27T05:45:00.000000+00:00",
        "resolved_at": null
      }
    ]
  }
  ```

---

#### 26. `PATCH /api/v1/alerts/{id}/status`
- **Purpose:** Transition an alert's lifecycle status (`"open"` -> `"acknowledged"` -> `"resolved"`).
- **Auth:** Session cookie.
- **CSRF Required:** **Yes**.
- **Request Body (`AlertStatusUpdate`):**
  ```json
  {
    "status": "acknowledged"
  }
  ```
- **Response (HTTP 200 OK — `AlertResponse`):** Updated alert record.

---

### Route Group 9: Reports & Telemetry Data Exports

#### 27. `GET /api/v1/reports/summary`
- **Purpose:** Compute high-level KPI report summary for an API over a selected time window.
- **Auth:** Session cookie.
- **Query Parameters:**
  - `apiId` *(string, required)*: API UUID.
  - `range` *(string, default: `"24h"`, pattern: `^(1h|6h|24h|7d)$`)*.
- **Response (HTTP 200 OK — `MonitoringReportSummary`):**
  ```json
  {
    "api_id": "78201a09-9602-4fc8-80f4-5544cfb9cb74",
    "api_name": "Payment Gateway Health",
    "time_range": "24h",
    "total_observations": 120,
    "availability": 98.3,
    "avg_latency_ms": 142.1,
    "p95_latency_ms": 280.0,
    "error_rate": 1.7,
    "timeout_rate": 0.0,
    "prediction_count": 8,
    "high_risk_predictions": 1,
    "open_alerts": 1,
    "generated_at": "2026-10-27T05:47:00.000000+00:00"
  }
  ```

---

#### 28. `GET /api/v1/reports/export-csv`
- **Purpose:** Stream sanitized telemetry observations as a downloadable CSV file.
- **Auth:** Session cookie.
- **Query Parameters:**
  - `apiId` *(string, required)*: API UUID.
  - `limit` *(int, default: 1000, min: 1, max: 5000)*.
- **Response (HTTP 200 OK, `text/csv`):**
  Headers include:
  `Content-Disposition: attachment; filename=apishield_telemetry_{apiId}.csv`  
  `Content-Type: text/csv; charset=utf-8`

---

### Route Group 10: Application Settings

#### 29. `GET /api/v1/settings`
- **Purpose:** Retrieve user-specific monitoring thresholds and alert cooldown settings.
- **Auth:** Session cookie.
- **Response (HTTP 200 OK — `UserSettingsSchema`):**
  ```json
  {
    "alert_cooldown_minutes": 15,
    "latency_warning_threshold_ms": 1000.0,
    "error_rate_threshold_percent": 5.0,
    "availability_target_percent": 99.0,
    "risk_alert_threshold": 70.0,
    "enable_auto_diagnostics": true,
    "webhook_url": null
  }
  ```

---

#### 30. `PUT /api/v1/settings`
- **Purpose:** Update user-specific monitoring preferences.
- **Auth:** Session cookie.
- **CSRF Required:** **Yes**.
- **Request Body (`UserSettingsUpdate`):**
  Subset of settings fields to update.
- **Response (HTTP 200 OK — `UserSettingsSchema`):** Updated settings.

---

### Route Group 11: MLOps, Training & Model Registry

#### 31. `GET /api/v1/ml/models/serving`
- **Purpose:** Inspect the model actively serving inferences in production and verify artifact health.
- **Auth:** Session cookie.
- **Response (HTTP 200 OK — `ServingModelResponse`):**
  ```json
  {
    "model_name": "apishield_failure_detector",
    "model_version": "model_v20261026_182719",
    "model_type": "RandomForestClassifier",
    "provenance": "trained_model",
    "is_loaded": true,
    "artifact_exists": true,
    "expected_features": [
      "avg_latency_ms", "p95_latency_ms", "p50_latency_ms", "std_latency_ms",
      "max_latency_ms", "latency_trend", "error_rate", "timeout_rate",
      "http_4xx_rate", "http_5xx_rate", "availability",
      "recent_consecutive_failures", "total_observations",
      "hour_of_day", "day_of_week"
    ],
    "candidate_metrics": {
      "accuracy": 0.94,
      "precision": 0.91,
      "recall": 0.88,
      "f1": 0.895
    },
    "trained_at": "2026-10-26T18:27:19.000000+00:00",
    "health_status": "healthy"
  }
  ```

---

#### 32. `GET /api/v1/ml/experiments`
- **Purpose:** List training runs, hyperparameters, metrics, and promotion outcomes from MLflow / local tracking.
- **Auth:** Session cookie.
- **Query Parameter:** `limit` *(int, default: 50, min: 1, max: 200)*.
- **Response (HTTP 200 OK — `ExperimentListResponse`):**
  List of `ExperimentRunSchema` items.

---

#### 33. `GET /api/v1/ml/experiments/{run_id}`
- **Purpose:** Retrieve single experiment run metadata by run ID.
- **Auth:** Session cookie.
- **Response (HTTP 200 OK — `ExperimentRunSchema`).**

---

#### 34. `GET /api/v1/ml/models`
- **Purpose:** List registered models in the MLflow Model Registry.
- **Auth:** Session cookie.
- **Query Parameter:** `model_name` *(string, optional)*.
- **Response (HTTP 200 OK — `ModelListResponse`).**

---

#### 35. `GET /api/v1/ml/models/{model_name}/versions`
- **Purpose:** List registered versions, stages, and aliases for a specific model.
- **Auth:** Session cookie.
- **Response (HTTP 200 OK — `ModelListResponse`).**

---

#### 36. `POST /api/v1/ml/training-runs`
- **Purpose:** Trigger model training, baseline evaluation, and promotion gate.
- **Auth:** Session cookie.
- **CSRF Required:** **Yes**.
- **Request Body (`TrainingRunRequest`):**
  ```json
  {
    "dataset_path": "data/telemetry_dataset.json"
  }
  ```
- **Response (HTTP 200 OK — `TrainingRunResponse`):**
  ```json
  {
    "success": true,
    "status": "promoted",
    "model_version": "model_v20261027_054812",
    "model_type": "RandomForestClassifier",
    "is_promoted": true,
    "candidate_metrics": { "f1": 0.92, "accuracy": 0.95 },
    "baseline_metrics": { "f1": 0.85, "accuracy": 0.88 },
    "reason": null
  }
  ```

---

#### 37. `GET /api/v1/ml/fairness-reports`
- **Purpose:** Retrieve group fairness report across telemetry client tiers (enterprise, pro, free) using Fairlearn and IBM AIF360.
- **Auth:** Session cookie.
- **Response (HTTP 200 OK — `FairnessReportResponse`):**
  Contains demographic parity, selection rates, and disparate impact metrics, with an explicit disclaimer that telemetry tiers do not represent human demographic attributes.

---

## E. Authentication, Session & Security Architecture

### Session Management Mechanism

APIShield uses stateful, database-backed sessions with secure cookies. It **does not** use stateless JWTs stored in browser storage.

1. **Login:** On successful credentials validation (`POST /api/v1/auth/login`), the backend generates a cryptographically random 256-bit token (`secrets.token_urlsafe(32)`).
2. **Storage:**
   - The **SHA-256 hash** of the token is stored in the PostgreSQL `user_sessions` table with an expiration timestamp (`expires_at = now + 24 hours`), client IP, and User-Agent.
   - The **raw token** is sent to the client in an `HttpOnly` cookie named `apishield_session`.
3. **Subsequent Calls:** The browser automatically includes the cookie. The backend extracts `apishield_session`, hashes it with SHA-256, looks up the session in the database, verifies it hasn't expired, and attaches the `User` record to `request.state`.
4. **Logout:** Calling `POST /api/v1/auth/logout` deletes the database row and expires the cookies on the client.

### CSRF Protection Workflow

To prevent Cross-Site Request Forgery on cookie-authenticated sessions:

1. On login or by calling `GET /api/v1/auth/csrf`, the backend issues a random CSRF token.
2. The CSRF token is delivered in:
   - A readable cookie: `apishield_csrf` (`HttpOnly=False`).
   - A response header: `X-CSRF-Token`.
   - The JSON body of `GET /api/v1/auth/csrf`.
3. **On every state-changing request (`POST`, `PATCH`, `PUT`, `DELETE`):**
   - The frontend must extract the CSRF token from the `apishield_csrf` cookie or response header and attach it as the `X-CSRF-Token` request header.
   - The backend dependency `verify_csrf` verifies that the `X-CSRF-Token` header matches the value in the `apishield_csrf` cookie using `secrets.compare_digest`.
   - If the header is missing or mismatched, the request is rejected with `HTTP 403 Forbidden` (`code: "CSRF_ERROR"`).

### CORS Configuration & Credentialed Headers

- **Allowed Origins:** Configured via `CORS_ORIGINS` in `.env` (defaults to `http://localhost:3000`, `http://localhost:5173`, `http://127.0.0.1:3000`, `http://127.0.0.1:5173`).
- **Credentials Allowed:** `allow_credentials=True`.
- **Exposed Headers:** `X-Request-ID`, `X-CSRF-Token`.
- **Important Rule:** Because credentials are enabled, the backend **never** permits wildcard `*` origins in production.

### SSRF Protection Engine

The `TestService` executes outbound HTTP requests for ad-hoc and saved API testing. To protect local infrastructure, it enforces:

- Prohibiting non-HTTP schemes (e.g. `file://`, `ftp://`, `gopher://`).
- Blocking embedded credentials (`https://user:pass@host`).
- Blocking loopback (`localhost`, `127.0.0.1`, `::1`), private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and AWS/GCP/Azure link-local metadata (`169.254.169.254`).
- Resolving DNS prior to connection, rejecting if any resolved IP is prohibited, and pinning the socket connection to the verified IP to prevent DNS rebinding attacks.

---

## F. Canonical Frontend Integration Code Examples

The following framework-neutral JavaScript examples demonstrate how to interact with the backend API contract.

### Shared Reusable HTTP Client (`apiClient.js`)

```javascript
/**
 * apiClient.js — Canonical APIShield API Client
 */

const BASE_URL = import.meta.env?.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Read cookie value by name
 */
export function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^|;\\s*)(' + name + ')=([^;]*)'));
  return match ? decodeURIComponent(match[3]) : null;
}

/**
 * Core HTTP fetch wrapper
 */
export async function apiRequest(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const method = options.method || 'GET';
  const headers = { ...options.headers };

  // Attach JSON Content-Type if body is provided as object
  if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  // Attach CSRF token on state-changing requests
  if (['POST', 'PATCH', 'PUT', 'DELETE'].includes(method.toUpperCase())) {
    const csrfToken = getCookie('apishield_csrf');
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }
  }

  // Ensure cookies are sent and received cross-origin
  const response = await fetch(url, {
    ...options,
    method,
    headers,
    credentials: 'include',
  });

  // Handle 204 No Content
  if (response.status === 204) {
    return null;
  }

  // Handle CSV downloads or binary streams
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('text/csv')) {
    return await response.blob();
  }

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const errorEnvelope = data.error || {
      code: 'HTTP_ERROR',
      message: response.statusText,
      fieldErrors: {},
      requestId: response.headers.get('X-Request-ID') || 'unknown',
    };
    const error = new Error(errorEnvelope.message);
    error.status = response.status;
    error.code = errorEnvelope.code;
    error.fieldErrors = errorEnvelope.fieldErrors;
    error.requestId = errorEnvelope.requestId;
    throw error;
  }

  return data;
}
```

---

### Authentication & Session Workflows

```javascript
// Register a new user
export async function register(name, email, password) {
  return await apiRequest('/api/v1/auth/register', {
    method: 'POST',
    body: { name, email, password },
  });
}

// Log in and establish session
export async function login(email, password) {
  const user = await apiRequest('/api/v1/auth/login', {
    method: 'POST',
    body: { email, password },
  });
  return user;
}

// Get profile of current user
export async function fetchCurrentUser() {
  return await apiRequest('/api/v1/auth/me');
}

// Log out and clear session
export async function logout() {
  return await apiRequest('/api/v1/auth/logout', {
    method: 'POST',
  });
}

// Fetch fresh CSRF token if cookie missing
export async function refreshCsrf() {
  return await apiRequest('/api/v1/auth/csrf');
}
```

---

### API Configuration & Testing Workflows

```javascript
// List saved APIs
export async function listApis() {
  return await apiRequest('/api/v1/apis');
}

// Create new API endpoint
export async function createApi(apiConfig) {
  return await apiRequest('/api/v1/apis', {
    method: 'POST',
    body: {
      name: apiConfig.name,
      url: apiConfig.url,
      method: apiConfig.method || 'GET',
      queryParams: apiConfig.queryParams || [],
      headers: apiConfig.headers || [],
      authType: apiConfig.authType || 'none',
      secret: apiConfig.secret || null,
      expectedStatus: apiConfig.expectedStatus || 200,
      timeoutMs: apiConfig.timeoutMs || 10000,
      intervalSec: apiConfig.intervalSec || 60,
      monitoring: apiConfig.monitoring ?? true,
    },
  });
}

// Execute ad-hoc test
export async function runAdhocTest(testPayload) {
  return await apiRequest('/api/v1/apis/adhoc/test', {
    method: 'POST',
    body: testPayload,
  });
}

// Trigger test on a saved API
export async function testSavedApi(apiId) {
  return await apiRequest(`/api/v1/apis/${apiId}/test`, {
    method: 'POST',
  });
}

// Get test history
export async function getApiTestHistory(apiId, limit = 50) {
  return await apiRequest(`/api/v1/apis/${apiId}/history?limit=${limit}`);
}
```

---

### Prediction, Explainability & Diagnostics Workflows

```javascript
// Trigger failure risk prediction
export async function predictApiRisk(apiId, explainMethod = 'shap') {
  return await apiRequest(`/api/v1/predictions/${apiId}/predict?explain_method=${explainMethod}`, {
    method: 'POST',
  });
}

// Get dynamic explanation (SHAP / LIME) for past prediction
export async function getPredictionExplanation(predictionId, method = 'shap') {
  return await apiRequest(`/api/v1/predictions/${predictionId}/explanation?method=${method}`);
}

// Retrieve root-cause diagnostics
export async function getApiDiagnostics(apiId) {
  return await apiRequest(`/api/v1/diagnostics/${apiId}`);
}
```

---

### Monitoring, Reports & CSV Export

```javascript
// Fetch time-series monitoring metrics for charts
export async function fetchMetrics(apiId = null, range = '24h') {
  const query = new URLSearchParams({ range });
  if (apiId) query.set('apiId', apiId);
  return await apiRequest(`/api/v1/monitoring/metrics?${query.toString()}`);
}

// Download telemetry CSV
export async function downloadTelemetryCsv(apiId) {
  const blob = await apiRequest(`/api/v1/reports/export-csv?apiId=${apiId}`);
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `apishield_telemetry_${apiId}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
```

---

## G. Data Models & Entity Relationships

### Database Schema & ORM Relationships

```mermaid
erDiagram
    users ||--o{ user_sessions : "has"
    users ||--o{ api_endpoints : "owns"
    users ||--o{ test_results : "executes"
    users ||--o{ prediction_records : "generates"
    users ||--o{ alert_records : "receives"
    users ||--o| user_settings : "configures"

    api_endpoints ||--o{ test_results : "records"
    api_endpoints ||--o{ prediction_records : "evaluates"
    api_endpoints ||--o{ alert_records : "triggers"

    users {
        string id PK
        string email UK
        string name
        string password_hash
        string role
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    user_sessions {
        string id PK
        string user_id FK
        string token_hash UK
        timestamp created_at
        timestamp expires_at
        string user_agent
        string ip_address
    }

    api_endpoints {
        string id PK
        string user_id FK
        string name
        string url
        string method
        json query_params
        json headers
        string auth_type
        string encrypted_secret
        text body
        int expected_status
        int timeout_ms
        int interval_sec
        boolean monitoring
        string health
        float risk_score
        string risk
        timestamp last_checked_at
        timestamp next_run_at
        boolean is_probing
    }

    test_results {
        string id PK
        string api_id FK
        string user_id FK
        boolean passed
        string outcome
        int status_code
        float latency_ms
        json headers
        text body
        json validations
        string error
        timestamp tested_at
        boolean simulated
    }

    prediction_records {
        string id PK
        string api_id FK
        string user_id FK
        float risk_score
        string risk_level
        int prediction
        string provenance
        string model_version
        json features
        json explanation
        float inference_duration_ms
        timestamp created_at
    }

    alert_records {
        string id PK
        string api_id FK
        string user_id FK
        string title
        text description
        string severity
        string status
        string source
        string fingerprint
        timestamp created_at
        timestamp resolved_at
    }

    user_settings {
        string id PK
        string user_id FK
        json settings
        timestamp updated_at
    }
```

### ORM vs Pydantic Serialization Contract

- **Database Layer (SQLAlchemy):** Column names follow standard Python snake_case (`query_params`, `expected_status`, `timeout_ms`, `last_checked_at`, `risk_score`).
- **API Response Layer (Pydantic):** Endpoints extending `BaseCamelModel` serialize JSON responses in **camelCase** (`queryParams`, `expectedStatus`, `timeoutMs`, `lastCheckedAt`, `riskScore`).
- **Inputs:** Pydantic models configure `populate_by_name=True`, allowing frontend callers to submit payload keys in either camelCase or snake_case safely.

---

## H. Machine Learning Lifecycle & Prediction Behavior

### 15 Extracted Telemetry Features

Feature extraction (`app/ml/features.py`) processes historical probe test results into a 15-dimensional numeric vector:

| # | Feature Name | Type | Description | Neutral Default |
|---|---|---|---|---|
| 1 | `avg_latency_ms` | float | Arithmetic mean of latency across observation window | `0.0` |
| 2 | `p95_latency_ms` | float | 95th percentile latency | `0.0` |
| 3 | `p50_latency_ms` | float | Median (50th percentile) latency | `0.0` |
| 4 | `std_latency_ms` | float | Latency standard deviation (jitter/volatility) | `0.0` |
| 5 | `max_latency_ms` | float | Peak observed latency in window | `0.0` |
| 6 | `latency_trend` | float | Ratio of recent 3 probes latency to overall average | `1.0` |
| 7 | `error_rate` | float | Percentage of probes resulting in error or failure | `0.0` |
| 8 | `timeout_rate` | float | Percentage of probes resulting in socket/read timeouts | `0.0` |
| 9 | `http_4xx_rate` | float | Percentage of probes returning HTTP 4xx | `0.0` |
| 10 | `http_5xx_rate` | float | Percentage of probes returning HTTP 5xx | `0.0` |
| 11 | `availability` | float | Percentage of passing probes | `100.0` |
| 12 | `recent_consecutive_failures` | float | Count of consecutive failures at end of window | `0.0` |
| 13 | `total_observations` | float | Number of observations evaluated (up to 15) | `0.0` |
| 14 | `hour_of_day` | float | UTC hour (0.0 to 23.0) of reference timestamp | Current UTC hour |
| 15 | `day_of_week` | float | Day of week (0.0=Monday to 6.0=Sunday) | Current UTC weekday |

### Prediction Pipeline & Provenance Resolution

When a prediction is requested (`POST /api/v1/predictions/{api_id}/predict`):

1. **Telemetry Window:** The service queries the last 15 test results for the API.
2. **Feature Extraction:** Features are extracted with zero lookahead (all observations precede current time).
3. **Model Selection & Fallback:**
   - The service attempts to load `artifacts/models/latest_model.joblib` and verifies `latest_model_meta.json`.
   - If the model exists, is marked `is_promoted: true`, and matches the 15-feature dimension, inference runs via `model.predict_proba` (`provenance: "trained_model"`, `model_version: "model_v20261026_182719"`).
   - If missing, corrupted, unpromoted, or dimension-mismatched, the service automatically falls back to `RuleBasedBaseline` (`provenance: "rules_baseline"`, `model_version: null`).
4. **Explainability Computation:** Attributions are computed via SHAP or LIME and persisted alongside the prediction.

### Model Explanations (SHAP & LIME)

- **SHAP (`shap.TreeExplainer`):** Calculates Shapley values on tree ensembles, accurately handling binary 3D arrays (`(1, 15, 2)`).
- **LIME (`lime.LimeTabularExplainer`):** Fits local linear surrogate models around the prediction instance.
- **Disclaimers:** Every explanation response explicitly includes:
  `"Feature attributions reflect statistical associations and model score weights, not real-world causal failure mechanics."`

### Group Fairness (Fairlearn & IBM AIF360)

The `/api/v1/ml/fairness-reports` endpoint evaluates model decisions across client tiers:
- **Demographic Parity Difference:** Evaluated using Fairlearn `MetricFrame`.
- **Disparate Impact & Statistical Parity:** Evaluated using IBM AIF360 `BinaryLabelDatasetMetric`.
- **Disclaimers:** Includes explicit non-demographic fairness notices stating telemetry tiers reflect SLA tiers rather than human demographic identities.

### Candidate Evaluation vs Production Active Model

To safeguard the production deployment:
- **Active Production Model:** `model_v20261026_182719` remains locked and served in production.
- **Candidate Evaluation:** Conducted via `app/ml/candidate_evaluator.py` against `data/experimental_telemetry_dataset.json` with a 4-step purge gap. Candidate models remain isolated in `artifacts/experimental/` and **are not** automatically promoted to production.

---

## I. Monitoring, Background Workflows & Observability

### Automated Background Probing Scheduler

The `MonitoringService` (`app/services/monitoring_service.py`) runs an async loop on a 5-second tick:
- Queries `api_endpoints` where `monitoring == True`, `next_run_at <= now`, and `is_probing == False`.
- Claims the endpoint using lease timeout safeguards to prevent concurrent duplicate probes.
- Executes the HTTP check, evaluates status codes and assertions, updates `health`, and schedules `next_run_at = now + interval_sec`.
- Automatically evaluates alert thresholds; if failure rates or risk exceed limits, triggers an alert with a 15-minute cooldown deduplication fingerprint.

### Prometheus Metrics Instruments

Exposed at `GET /metrics`:

| Metric Name | Type | Labels | Description |
|---|---|---|---|
| `apishield_http_requests_total` | Counter | `method`, `endpoint`, `status` | Normalized request counter |
| `apishield_http_request_duration_seconds` | Histogram | `method`, `endpoint` | Request latency distribution |
| `apishield_api_probe_total` | Counter | `outcome`, `status_code` | Background probe execution counts |
| `apishield_api_probe_latency_seconds` | Histogram | None | Probe network latency histogram |
| `apishield_predictions_total` | Counter | `provenance`, `risk_level` | Inference count by provenance and risk |
| `apishield_prediction_duration_seconds` | Histogram | None | Prediction inference runtime duration |
| `apishield_scheduler_running` | Gauge | None | `1` when scheduler active, `0` otherwise |
| `apishield_scheduler_tick_duration_seconds`| Histogram | None | Time taken to process scheduler tick |

### Grafana Dashboard

Located at `monitoring/grafana/dashboards/apishield-overview.json`:
- Pre-provisioned with 9 panels: Active Traffic, HTTP Latency P95/P50, HTTP Error Rates, Scheduled Probes Total, Probe Latency, Prediction Provenance Distribution, High-Risk Alerts, and Scheduler Health.

### Apache Airflow Workflows

Two production DAGs are located in `airflow/dags/`:
1. `apishield_telemetry_data_preparation` (`dag_telemetry_prep.py`):
   - **Schedule:** `@hourly`
   - **Tasks:** `extract_monitoring_telemetry` -> `validate_data_quality`
2. `apishield_model_training_and_evaluation` (`dag_model_training.py`):
   - **Schedule:** `@daily`
   - **Tasks:** `check_dataset_readiness` -> `train_and_evaluate_model` -> `verify_model_promotion`

### DVC Reproducibility

Defined in `dvc.yaml`:
- Stage 1: `prepare_dataset` -> Outputs `data/telemetry_dataset.json`.
- Stage 2: `train_model` -> Outputs `artifacts/models/latest_model_meta.json` and `latest_model.joblib`.

---

## J. Error Handling & Troubleshooting Reference

| Error Code | HTTP Status | Common Cause | Recommended Frontend Handling | Retry Safe? |
|---|---|---|---|---|
| `UNAUTHORIZED` | 401 | Missing, expired, or invalid session cookie | Redirect to `/login` or display re-authentication modal | No (until re-auth) |
| `INVALID_CREDENTIALS` | 401 | Incorrect email or password during login | Display "Invalid email or password" | No (wait for user) |
| `CSRF_ERROR` | 403 | Missing or mismatched `X-CSRF-Token` header | Call `GET /api/v1/auth/csrf`, update header, and retry | **Yes** (once after fetch) |
| `NOT_FOUND` | 404 | Endpoint ID or Prediction ID does not exist | Display "Resource not found" notice | No |
| `CONFLICT` | 409 | Registering with an already-used email | Highlight email input: "Account already exists" | No |
| `SSRF_BLOCKED` | 400 | Target URL resolves to localhost, private IP, or cloud metadata | Display warning: "Target URL rejected for security reasons" | No |
| `RATE_LIMITED` | 429 | Exceeded 20 requests/minute on auth routes | Display "Too many attempts. Please wait 60 seconds." | Wait 60s, then retry |
| `VALIDATION_ERROR` | 422 | Pydantic payload validation failure | Map `error.fieldErrors` to individual form input fields | No (until user corrects) |
| `SERVICE_UNAVAILABLE` | 503 | Database unreachable during readiness check | Display maintenance banner: "System initializing" | **Yes** (exponential backoff) |
| `INTERNAL_SERVER_ERROR`| 500 | Unhandled server exception | Display "An unexpected error occurred. Request ID: {requestId}" | **Yes** (idempotent GETs only) |

---

## K. Environment Configuration Reference

| Variable Name | Required | Default | Consuming Component | Description | Example Placeholder |
|---|---|---|---|---|---|
| `ENVIRONMENT` | Yes | `development` | FastAPI, Settings, Docker | Runtime mode (`development`, `testing`, `production`) | `development` |
| `DEBUG` | No | `false` | FastAPI | Detailed debug logging | `false` |
| `APP_HOST` | No | `0.0.0.0` | Uvicorn | Network host interface | `0.0.0.0` |
| `APP_PORT` | No | `8000` | Uvicorn, Docker | Port number | `8000` |
| `SECRET_KEY` | **Yes** | Dev secret | Security, Session | Minimum 32-char key for session signatures | `openssl rand -hex 32` |
| `CREDENTIALS_ENCRYPTION_KEY` | **Yes** | Dev Fernet key | ApiService | 32-byte urlsafe base64 Fernet key for credential encryption | `Fernet.generate_key()` |
| `DATABASE_URL` | **Yes** | Postgres local | SQLAlchemy, Alembic | Connection string (`postgresql+psycopg://...`) | `postgresql+psycopg://user:pass@host:5432/db` |
| `DATABASE_ECHO` | No | `false` | SQLAlchemy | Echo raw SQL queries to console | `false` |
| `CORS_ORIGINS` | **Yes** | Localhost origins | CORSMiddleware | Comma-separated list of allowed frontend origins | `http://localhost:5173,http://localhost:3000` |
| `SESSION_COOKIE_NAME` | No | `apishield_session`| Auth, Deps | Name of HttpOnly session cookie | `apishield_session` |
| `CSRF_COOKIE_NAME` | No | `apishield_csrf` | Middleware, Deps | Name of client-readable CSRF cookie | `apishield_csrf` |
| `SESSION_MAX_AGE_SECONDS`| No | `86400` (24h) | Auth, Cookies | Session lifetime in seconds | `86400` |
| `SESSION_COOKIE_SECURE` | No | `false` | Auth, Cookies | Set `true` in production over HTTPS | `false` |
| `SESSION_COOKIE_SAMESITE`| No | `lax` | Auth, Cookies | Cookie SameSite policy (`lax`, `strict`, `none`) | `lax` |
| `AUTH_RATE_LIMIT_PER_MINUTE`| No| `20` | RateLimiter | Max auth attempts per minute per IP | `20` |
| `MONITORING_ENABLED` | No | `true` | Lifespan, Scheduler | Enables background probe scheduler | `true` |
| `MONITORING_TICK_SECONDS`| No | `5` | MonitoringService | Probe evaluation interval in seconds | `5` |
| `MONITORING_MAX_CONCURRENCY`| No| `10` | MonitoringService | Max concurrent asynchronous probes | `10` |
| `MLFLOW_TRACKING_URI` | No | `sqlite:///mlruns/mlflow.db` | MLflowTracker | MLflow tracking database URI | `http://localhost:5000` |

---

## L. Testing & Verification Runbook

### Running the Full Test Suite

Execute pytest from the `backend/` directory:

```bash
# Run the entire test suite with summary
pytest -v

# Run with concise output
pytest -q
```

### Verified Test Suite Breakdown (141 Passed Tests)

- `test_auth.py` (5 tests): Registration, duplicate prevention, password length validation, login cookies, session invalidation on logout.
- `test_security.py` (6 tests): CSRF enforcement, session tampering prevention, rate limiting, Request ID propagation.
- `test_ssrf.py` (19 tests): Scheme validation, private IP blocks, cloud metadata rejection, DNS rebinding prevention, IPv6 NAT64 handling.
- `test_apis.py` (8 tests): Saved API CRUD, Fernet credential encryption, ownership scoping.
- `test_testing.py` (4 tests): Ad-hoc testing, saved API probe execution, assertion evaluations.
- `test_monitoring.py` (11 tests): Scheduler ticks, concurrency claims, empty dataset handling, time-series bucket calculations.
- `test_predictions.py` (8 tests): Risk prediction, provenance resolution, model loading, transparent baseline fallback.
- `test_explainability.py` (5 tests): Genuine SHAP TreeExplainer, LIME TabularExplainer, non-causal disclaimer checks.
- `test_ml_endpoints.py` (7 tests): Experiments listing, registered models, serving status, fairness endpoints.
- `test_ml_pipeline.py` (9 tests): 15-feature extraction, sliding window builder, training pipeline, promotion gate.
- `test_candidate_evaluation.py` (7 tests): Isolated candidate evaluation, holdout test isolation, comprehensive metrics.
- `test_experimental_dataset.py` (8 tests): Purge gap verification, non-overlapping window boundaries, sequence coverage.
- `test_fairness.py` (3 tests): Native Fairlearn & IBM AIF360 demographic parity reports.
- `test_alerts_reports_settings.py` (11 tests): Alert lifecycle, fingerprint deduplication, CSV export, user settings.
- `test_health.py` (4 tests): Liveness and database-driven readiness checks.
- `test_prometheus_metrics.py` (3 tests): Prometheus exposition format, cardinality protection.
- `test_airflow_dags.py` (3 tests): Airflow DAG compilation and task callable isolation.
- `test_config.py` (10 tests): Strict production secret validators and entropy requirements.
- `test_migrations.py` (1 test): Alembic migration upgrade and downgrade cycle.

---

## M. Frontend Integration Checklist

Follow this checklist in sequence to integrate the frontend with APIShield:

- [ ] **1. Base URL Configuration:** Set your frontend API client base URL to `http://localhost:8000` (or your deployed backend host).
- [ ] **2. Verify System Readiness:** Confirm `GET /health/live` returns `200` and `GET /health/ready` returns `200` (database connected).
- [ ] **3. CORS & Credential Setup:** Ensure your frontend origin is in `CORS_ORIGINS` and your HTTP client specifies `credentials: 'include'` (Fetch) or `withCredentials: true` (Axios).
- [ ] **4. Shared HTTP Client:** Implement the shared HTTP client with automatic `X-CSRF-Token` extraction from the `apishield_csrf` cookie on `POST`, `PATCH`, `PUT`, `DELETE`.
- [ ] **5. Authentication Flow:**
  - Implement registration (`POST /api/v1/auth/register`).
  - Implement login (`POST /api/v1/auth/login`).
  - On app load, call `GET /api/v1/auth/me` to rehydrate the user session.
  - Implement logout (`POST /api/v1/auth/logout`).
- [ ] **6. Saved API Management:** Build forms for creating and editing API endpoints. Use camelCase response fields (`queryParams`, `expectedStatus`, `intervalSec`, `monitoring`).
- [ ] **7. Testing Interface:** Connect ad-hoc test execution (`POST /api/v1/apis/adhoc/test`) and saved API test execution (`POST /api/v1/apis/{api_id}/test`).
- [ ] **8. Prediction & Explainability Views:**
  - Call `POST /api/v1/predictions/{api_id}/predict` to calculate risk.
  - Display `risk_score`, `risk_level` badges, and feature contribution charts.
  - Allow users to toggle between SHAP and LIME via `GET /api/v1/predictions/{id}/explanation`.
- [ ] **9. Telemetry Charts & Reports:**
  - Render time-series charts using `GET /api/v1/monitoring/metrics?range=24h`.
  - Wire up the CSV download button using `GET /api/v1/reports/export-csv?apiId={api_id}`.
- [ ] **10. Alert Management & Settings:**
  - Display active alerts (`GET /api/v1/alerts`).
  - Allow acknowledging or resolving alerts (`PATCH /api/v1/alerts/{id}/status`).
  - Render user threshold configuration (`GET /api/v1/settings` and `PUT /api/v1/settings`).

---

## N. Verified cURL Smoke Test Scripts

These tested cURL commands demonstrate the complete workflow from the terminal:

### 1. Register, Login, and Capture Cookies

```bash
# Register
curl -i -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"name": "Dev User", "email": "dev@example.com", "password": "Password123!"}'

# Login and save session cookies to cookies.txt
curl -i -X POST "http://localhost:8000/api/v1/auth/login" \
  -c cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"email": "dev@example.com", "password": "Password123!"}'

# Verify current profile
curl -i -X GET "http://localhost:8000/api/v1/auth/me" -b cookies.txt
```

### 2. Create Saved API & Run Test (with CSRF Extraction)

```bash
# Extract CSRF token from cookies.txt (or fetch via /auth/csrf)
CSRF_TOKEN=$(grep apishield_csrf cookies.txt | awk '{print $7}')

# Create an API endpoint
curl -i -X POST "http://localhost:8000/api/v1/apis" \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  -d '{
    "name": "HTTPBin Health",
    "url": "https://httpbin.org/status/200",
    "method": "GET",
    "expectedStatus": 200,
    "monitoring": true
  }'

# Run an ad-hoc test
curl -i -X POST "http://localhost:8000/api/v1/apis/adhoc/test" \
  -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  -d '{"url": "https://httpbin.org/get", "method": "GET"}'
```

### 3. Check Serving Model & Run Prediction

```bash
# Check active serving model
curl -i -X GET "http://localhost:8000/api/v1/ml/models/serving" -b cookies.txt

# Run prediction for API endpoint
curl -i -X POST "http://localhost:8000/api/v1/predictions/<API_ID>/predict?explain_method=shap" \
  -b cookies.txt \
  -H "X-CSRF-Token: $CSRF_TOKEN"
```

### 4. Logout

```bash
curl -i -X POST "http://localhost:8000/api/v1/auth/logout" \
  -b cookies.txt \
  -H "X-CSRF-Token: $CSRF_TOKEN"
```

---

## O. OpenAPI Specification Export Guide

The backend automatically generates an OpenAPI 3.1.0 specification compliant with the active codebase.

### Option 1: Live Export from Running Server

When the backend is running in `development` mode:

```bash
# Download formatted OpenAPI JSON
curl -s http://localhost:8000/openapi.json | python -m json.tool > openapi.json
```

### Option 2: Headless Python Export (Without Running Server)

From the `backend/` directory:

```bash
python -c "import json; from app.main import app; open('openapi.json', 'w').write(json.dumps(app.openapi(), indent=2))"
```

This exports the entire schema, including all 36 registered OpenAPI routes (all application endpoints except root `/metrics` which is excluded via `include_in_schema=False`), request/response models, field descriptions, and validations, directly into `openapi.json`.

---

## P. Documentation Verification & Audit Trail

This documentation was derived directly from inspection of the active backend implementation files:

- **Routing & Lifespan:** `app/main.py`, `app/api/v1/router.py`, `app/api/deps.py`
- **Endpoints:** `app/api/v1/endpoints/*.py` (`auth.py`, `apis.py`, `monitoring.py`, `predictions.py`, `diagnostics.py`, `alerts.py`, `reports.py`, `settings.py`, `ml.py`, `health.py`)
- **Data Models:** `app/models/*.py` (`user.py`, `session.py`, `api.py`, `test_result.py`, `ml.py`)
- **Schemas:** `app/schemas/*.py` (`auth.py`, `api.py`, `testing.py`, `monitoring.py`, `ml.py`, `error.py`)
- **Services:** `app/services/*.py` (`auth_service.py`, `api_service.py`, `test_service.py`, `prediction_service.py`, `monitoring_service.py`, `metrics_service.py`, `diagnostic_service.py`, `alert_service.py`, `report_service.py`, `settings_service.py`)
- **ML Subsystem:** `app/ml/*.py` (`features.py`, `dataset.py`, `candidate_evaluator.py`, `model.py`, `provenance.py`, `explainability.py`, `fairness.py`, `mlflow_tracker.py`, `pipeline.py`)
- **Core Security & Middleware:** `app/core/config.py`, `app/core/security.py`, `app/core/middleware.py`, `app/core/metrics.py`
- **Infrastructure & Deployment:** `Dockerfile`, `../docker-compose.yml`, `monitoring/prometheus.yml`, `monitoring/grafana/dashboards/apishield-overview.json`, `airflow/dags/*.py`, `dvc.yaml`
- **Automated Tests:** 21 test files in `tests/` (141 total tests verified).
