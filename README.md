# APIShield Backend & MLOps Platform

APIShield is an AI-based API failure prediction, automated telemetry monitoring, root-cause diagnostics, and comprehensive MLOps platform. This backend service provides the REST API built with FastAPI, PostgreSQL / SQLAlchemy 2.x, Alembic, scikit-learn, native SHAP, native LIME, native MLflow Tracking & Model Registry, DVC versioning, Fairlearn, IBM AIF360, Apache Airflow 3.3.0 workflows, Prometheus metrics, and Grafana dashboarding.

---

## 1. Backend Architecture & Components

```text
backend/
├── airflow/
│   ├── dags/
│   │   ├── dag_telemetry_prep.py     # DAG A: Telemetry preparation, validation & feature extraction
│   │   └── dag_model_training.py     # DAG B: Model training, baseline evaluation & promotion
│   └── discover_wsl_airflow.sh       # WSL Airflow discovery helper script
├── app/
│   ├── api/
│   │   ├── deps.py                   # Dependency injection (DB, auth, CSRF, rate limit)
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── auth.py           # Authentication (/register, /login, /me, /logout, /csrf)
│   │       │   ├── apis.py           # Saved API endpoint management
│   │       │   ├── testing.py        # Ad-hoc and saved API testing engine
│   │       │   ├── monitoring.py     # Background scheduler state & time-series metrics
│   │       │   ├── predictions.py    # Failure prediction, history & dynamic explanations
│   │       │   ├── ml.py             # ML management (experiments, models, serving, fairness, runs)
│   │       │   ├── diagnostics.py    # Root-cause rule-based diagnostic analysis
│   │       │   ├── alerts.py         # Persistent alert records with cooldown deduplication
│   │       │   ├── reports.py        # Summary reports & sanitized CSV export
│   │       │   ├── settings.py       # User-level application settings
│   │       │   └── health.py         # Liveness (/health/live) and Readiness (/health/ready)
│   │       └── router.py             # Router aggregation
│   ├── core/
│   │   ├── config.py                 # Pydantic Settings & environment variables
│   │   ├── errors.py                 # Standardized AppException
│   │   ├── logging.py                # Structured sanitized logging (masks secrets/tokens)
│   │   ├── metrics.py                # Prometheus metric instruments & ASGI middleware
│   │   ├── middleware.py             # Request ID, rate limiting, and CSRF protection
│   │   └── security.py               # Argon2id password hashing, Fernet credential encryption
│   ├── db/
│   │   ├── base.py                   # SQLAlchemy DeclarativeBase
│   │   └── session.py                # Engine, sessionmaker, DB readiness check
│   ├── ml/
│   │   ├── features.py               # Chronological tabular feature extraction (15 features)
│   │   ├── dataset.py                # Telemetry dataset builder with leakage prevention
│   │   ├── model.py                  # RuleBasedBaseline, ModelTrainer (RandomForest), evaluation
│   │   ├── provenance.py             # PredictionProvenance (trained_model, rules_baseline, demo)
│   │   ├── diagnostics.py            # DiagnosticEngine (latency, timeout, 4xx, 5xx analysis)
│   │   ├── explainability.py         # ModelExplainer (genuine SHAP TreeExplainer & LIME TabularExplainer)
│   │   ├── fairness.py               # Group fairness evaluation (native Fairlearn & IBM AIF360)
│   │   ├── mlflow_tracker.py         # MLflow Tracking & SQLite Model Registry wrapper
│   │   ├── pipeline.py               # Dataset preparation & training pipeline entrypoints
│   │   └── sagemaker_adapter.py      # AWS SageMaker compatibility stub
│   ├── models/                       # SQLAlchemy ORM models (User, Session, Api, TestResult, etc.)
│   ├── schemas/                      # Pydantic models for validation and serialization
│   ├── services/                     # Business logic (Auth, Test, Monitoring, Prediction, etc.)
│   └── main.py                       # FastAPI entrypoint, Prometheus /metrics, CORS
├── migrations/                       # Alembic migrations (0001 through 0004)
├── monitoring/
│   ├── prometheus.yml                # Prometheus scraping configuration
│   └── grafana/
│       ├── dashboards/
│       │   └── apishield-overview.json  # 9-panel provisioned Grafana dashboard
│       └── provisioning/             # Datasource and dashboard providers
├── tests/                            # 121 automated unit, integration, and security tests
├── Dockerfile                        # Multi-stage production container
├── docker-compose.yml                # Complete local stack (Backend, DB, Prometheus, Grafana)
├── dvc.yaml                          # DVC reproducible pipeline stages
├── requirements.txt                  # Production dependencies (including MLOps packages)
└── requirements-dev.txt              # Development & test dependencies
```

---

## 2. Environment Setup & Supported Python Version

### Prerequisites
* **Python**: 3.11, 3.12, or 3.13 (Python 3.13.14 verified with zero regressions across 121 tests)
* **Database**: PostgreSQL 14+ (or SQLite for lightweight test runs)
* **ML Packages**: `shap`, `lime`, `mlflow`, `dvc`, `fairlearn`, `aif360`, `boto3`

### Step 1: Virtual Environment Setup
```bash
cd backend
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Linux / WSL / macOS
source .venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install -r requirements-dev.txt
```

---

## 3. Environment Variables (.env)

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Key variables and safe development defaults:
```ini
ENVIRONMENT=development
DEBUG=false
APP_HOST=0.0.0.0
APP_PORT=8000

# Security (minimum 32 chars)
SECRET_KEY=change-this-to-a-secure-random-secret-key-min-32-chars
# Fernet 32-byte urlsafe base64 key
CREDENTIALS_ENCRYPTION_KEY=vME3wCp5mpWfOD-IFGp1koWNHgtnGUKnY00-_-WDAEE=

# Database
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/apishield
DATABASE_ECHO=false

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173

# Rate Limiting & Scheduler
AUTH_RATE_LIMIT_PER_MINUTE=20
MONITORING_ENABLED=true
MONITORING_TICK_SECONDS=5
MONITORING_MAX_CONCURRENCY=10

# MLflow Tracking (defaults to local SQLite DB at sqlite:///mlruns/mlflow.db with full Model Registry)
# MLFLOW_TRACKING_URI=sqlite:///D:/College/3rd_Year/MLOPS/CP/backend/mlruns/mlflow.db
```

---

## 4. PostgreSQL Setup & Database Migrations

Apply Alembic migrations to the latest revision (`head`):
```bash
alembic upgrade head
```

Verify migration history:
```bash
alembic history --verbose
```

Roll back migration if necessary:
```bash
alembic downgrade -1
```

*Migration revisions:*
- `0001_initial_user_and_session`: Users and UserSession models.
- `0002_api_endpoints_and_test_results`: ApiEndpoint and TestResult models.
- `0003_monitoring_scheduler_fields`: Next check, lease expiration, error counts.
- `0004_predictions_alerts_settings`: PredictionRecord, AlertRecord, SettingRecord.

---

## 5. Startup & Health Checks

Start the FastAPI ASGI server:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive documentation:
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

Health endpoints:
- `GET /health/live` — Liveness check. Returns `{"status": "alive"}` as long as the process is responsive.
- `GET /health/ready` — Readiness check. Verifies database connectivity with `SELECT 1`. Returns `503 Service Unavailable` if database is unreachable.
- `GET /metrics` — Prometheus metrics exposition in text format.

---

## 6. Machine Learning Explainability (SHAP & LIME)

APIShield provides genuine machine learning explainability via `app/ml/explainability.py`:

### SHAP (`shap.TreeExplainer`)
- Computes exact Shapley feature attributions on tree-based models (`RandomForestClassifier`).
- Correctly handles binary classification 3D output arrays (`(1, 15, 2)`), 2D arrays, and multi-class lists.
- Maps attributions to exact feature names and orders them by absolute contribution.
- Returns `method: "shap_tree_attribution"` and `is_fallback: False`.

### LIME (`lime.lime_tabular.LimeTabularExplainer`)
- Constructs local linear surrogate approximations using empirical training data background distributions.
- Calls `model.predict_proba` to explain instances locally with condition bounds.
- Returns `method: "lime_tabular_surrogate"` and `is_fallback: False`.

### Transparent Heuristic Fallback
- When no model is loaded or rules baseline is active, computes normalized feature deviations from baseline healthy thresholds.
- Always flags `method: "normalized_feature_attribution"` and `is_fallback: True`.
- Never claims SHAP or LIME ran if the fallback was used.

### Non-Causal Interpretation Warnings
Every explanation includes an explicit disclaimer noting that attributions reflect statistical associations and model score weights, not real-world causal failure mechanics.

### Dynamic Explanation Endpoint
Retrieve explanations dynamically for any existing prediction:
```bash
# Get SHAP Tree Attribution
curl -b cookies.txt "http://localhost:8000/api/v1/predictions/{id}/explanation?method=shap"

# Get LIME Local Surrogate Explanation
curl -b cookies.txt "http://localhost:8000/api/v1/predictions/{id}/explanation?method=lime"
```

---

## 7. ML Management APIs

The `/api/v1/ml/` route provides endpoints for managing the MLOps lifecycle:

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/ml/experiments` | `GET` | List experiment runs, parameters, metrics, and promotion status. |
| `/api/v1/ml/experiments/{run_id}` | `GET` | Retrieve single experiment run details by run ID. |
| `/api/v1/ml/models` | `GET` | List registered models, versions, stages, and aliases. |
| `/api/v1/ml/models/{model_name}/versions` | `GET` | List all versions of a specific registered model. |
| `/api/v1/ml/models/serving` | `GET` | Report the active serving model, provenance, version, and health. |
| `/api/v1/ml/training-runs` | `POST` | Trigger model training, evaluation, and promotion pipeline. |
| `/api/v1/ml/fairness-reports` | `GET` | Retrieve group fairness & demographic parity report. |

---

## 8. MLflow Tracking & Model Registry

APIShield integrates MLflow Tracking and the Model Registry (`app/ml/mlflow_tracker.py`):
- **Local SQLite Backend Store:** Automatically configures `sqlite:///{tracking_dir}/mlflow.db`, enabling the complete native Model Registry without requiring external cloud databases.
- **Run Tracking:** Logs parameters (`window_size`, `n_estimators`, `max_depth`), metrics (`accuracy`, `precision`, `recall`, `f1`), tags, and artifacts.
- **Model Registration:** Automatically registers candidate models under `apishield_failure_detector`.
- **Model Promotion & Aliasing:** Assigns the `production` alias to models that satisfy promotion criteria; assigns `staging` or `rejected_inferior` otherwise.
- **Offline Fallback Store:** Writes JSONL run records to `mlruns/runs_history.jsonl` if MLflow native libraries encounter runtime issues, clearly flagged as `backend: "local_file_tracking"`.

To launch the MLflow UI:
```bash
mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db --port 5000
```
Open [http://localhost:5000](http://localhost:5000) to inspect registered models, versions, and metrics.

---

## 9. DVC Data & Model Versioning

APIShield uses Data Version Control (`dvc.yaml`) for reproducible data preparation and model training:

```bash
# Verify the DVC pipeline DAG
dvc dag

# Run dry-run pipeline verification
dvc repro --dry

# Execute the reproducible pipeline
dvc repro
```

Stages defined in `dvc.yaml`:
1. `prepare_dataset`:
   - Command: `python -m app.ml.pipeline prepare --dataset-path data/telemetry_dataset.json`
   - Dependencies: `app/ml/dataset.py`, `app/ml/features.py`, `app/ml/pipeline.py`
   - Output: `data/telemetry_dataset.json`
2. `train_model`:
   - Command: `python -m app.ml.pipeline train --dataset-path data/telemetry_dataset.json`
   - Dependencies: `data/telemetry_dataset.json`, `app/ml/model.py`, `app/ml/pipeline.py`, `app/ml/mlflow_tracker.py`
   - Outputs: `artifacts/models/latest_model_meta.json`, `artifacts/models/latest_model.joblib`

---

## 10. Fairlearn & IBM AIF360 Group Fairness

Fairness evaluation is implemented in `app/ml/fairness.py`:
- **Fairlearn Integration:** Uses `fairlearn.metrics.MetricFrame` to compute group-level `selection_rate` (Demographic Parity), `true_positive_rate`, and `false_positive_rate` (Equalized Odds).
- **IBM AIF360 Integration:** Uses `aif360.datasets.BinaryLabelDataset` and `BinaryLabelDatasetMetric` to calculate `disparate_impact` and `statistical_parity_difference` between privileged and unprivileged client tiers.
- **Synthetic Data Labeling & Disclaimers:** Synthetic demonstrations are clearly marked (`is_synthetic_demonstration: True`) and include non-demographic fairness disclaimers stating that telemetry tiers do not represent human demographic attributes.
- **Graceful Error Handling:** Safely handles single-group inputs, empty vectors, or missing attributes with informative error messages.

---

## 11. Apache Airflow 3.3.0 Integration (WSL2 Ubuntu)

APIShield reuses the existing WSL2 Apache Airflow installation located at:
* **Airflow Home:** `/home/nitish/airflow`
* **Virtualenv:** `/home/nitish/airflow_venv` (Python 3.14.4)
* **Airflow Version:** Apache Airflow 3.3.0 (LocalExecutor, SQLite database)
* **DAGs Directory:** `/home/nitish/airflow/dags`

### Airflow 3 Compatibility Adjustments
- Replaced deprecated `schedule_interval` with Airflow 3.x `schedule` (`@hourly`, `@daily`).
- Utilized `airflow.providers.standard.operators.python.PythonOperator`.
- Implemented cross-environment execution boundary: Airflow tasks in Python 3.14 delegate execution of the ML pipeline to the backend's Python 3.13 virtual environment (`/mnt/d/College/3rd_Year/MLOPS/CP/backend/.venv/Scripts/python.exe`), maintaining environment isolation.

### Discover & Test DAGs in WSL
```bash
# 1. Sync DAGs to Airflow dags folder
cp -u /mnt/d/College/3rd_Year/MLOPS/CP/backend/airflow/dags/*.py /home/nitish/airflow/dags/

# 2. Activate Airflow virtualenv
source /home/nitish/airflow_venv/bin/activate

# 3. Test telemetry data prep DAG
airflow dags test apishield_telemetry_data_preparation

# 4. Test model training & promotion DAG
airflow dags test apishield_model_training_and_evaluation
```
Both DAGs execute through all task instances and finish in `state=success`.

---

## 12. Testing & Quality Assurance

Run the comprehensive pytest suite:
```bash
pytest -v
```

**Results:**
- **121 passed, 0 failures** across 17 test modules.
- Includes unit and integration tests for auth, security, SSRF validation, monitoring scheduler, predictions, explainability, ML management APIs, MLflow, fairness, migrations, and Airflow DAGs.

---

## 13. Docker, Prometheus & Grafana

Start the containerized stack:
```bash
docker compose up -d --build
```

### Services
* **Backend:** `http://localhost:8001` (container port 8000)
* **PostgreSQL 16:** `localhost:5432`
* **Prometheus:** `http://localhost:9090` (scrapes `/metrics` every 15s)
* **Grafana:** `http://localhost:3000` (provisioned datasource and 9-panel dashboard)
