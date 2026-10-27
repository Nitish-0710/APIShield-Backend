import re
import time
from typing import Callable, Optional
from fastapi import Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware

# 1. HTTP Metrics
HTTP_REQUESTS_TOTAL = Counter(
    "apishield_http_requests_total",
    "Total HTTP requests received by the backend service",
    ["method", "endpoint", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "apishield_http_request_duration_seconds",
    "HTTP request latency distributions in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

HTTP_ERRORS_TOTAL = Counter(
    "apishield_http_errors_total",
    "Total HTTP error responses returned",
    ["method", "endpoint", "status_class"],
)

# 2. Monitoring & Testing Metrics
API_TESTS_TOTAL = Counter(
    "apishield_api_tests_total",
    "Total API test probes executed",
    ["outcome"],  # "success" | "failure" | "timeout" | "error"
)

API_TEST_DURATION_SECONDS = Histogram(
    "apishield_api_test_duration_seconds",
    "Duration of API monitoring and ad-hoc probes in seconds",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

API_TIMEOUTS_TOTAL = Counter(
    "apishield_api_timeouts_total",
    "Total number of API probe timeouts and connection failures",
)

# 3. Prediction & Inference Metrics
PREDICTIONS_TOTAL = Counter(
    "apishield_predictions_total",
    "Total ML and baseline prediction requests processed",
    ["provenance", "risk_level"],
)

PREDICTION_DURATION_SECONDS = Histogram(
    "apishield_prediction_duration_seconds",
    "Prediction inference duration in seconds",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

PREDICTION_ERRORS_TOTAL = Counter(
    "apishield_prediction_errors_total",
    "Total prediction and inference failures",
    ["error_type"],
)

# 4. Scheduler & Application Health Indicators
SCHEDULER_RUNNING = Gauge(
    "apishield_scheduler_running",
    "Monitoring scheduler operational state (1 = active, 0 = stopped)",
)

SCHEDULER_JOBS_TOTAL = Counter(
    "apishield_scheduler_jobs_total",
    "Total monitoring scheduler tick executions",
    ["status"],  # "success" | "error"
)

APP_HEALTHY = Gauge(
    "apishield_app_healthy",
    "Overall backend application readiness status (1 = healthy, 0 = degraded)",
)

# Initialize default states
SCHEDULER_RUNNING.set(0)
APP_HEALTHY.set(1)

# Regex to normalize dynamic UUIDs in endpoint paths for low cardinality
UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def normalize_endpoint(path: str) -> str:
    """Normalizes URL path to avoid metric cardinality explosion from dynamic IDs."""
    normalized = UUID_PATTERN.sub("{id}", path)
    return normalized


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Avoid self-observation on metrics endpoint
        if path == "/metrics":
            return await call_next(request)

        method = request.method
        endpoint = normalize_endpoint(path)
        start_time = time.perf_counter()

        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            duration = time.perf_counter() - start_time
            str_status = str(status_code)
            status_class = f"{str_status[0]}xx"

            try:
                HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status=str_status).inc()
                HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint).observe(duration)

                if status_code >= 400:
                    HTTP_ERRORS_TOTAL.labels(
                        method=method, endpoint=endpoint, status_class=status_class
                    ).inc()
            except Exception:
                pass  # Metric collection failures must never break API requests


def get_prometheus_metrics_response() -> Response:
    """Exposes Prometheus-formatted metrics output."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
