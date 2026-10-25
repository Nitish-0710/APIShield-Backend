import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AppException
from app.models.api import ApiEndpoint
from app.models.test_result import TestResultRecord
from app.models.user import User
from app.schemas.monitoring import MetricPoint, TimeRange

RANGE_SPEC: Dict[str, Dict[str, int]] = {
    "1h": {"points": 30, "step_min": 2},
    "6h": {"points": 36, "step_min": 10},
    "24h": {"points": 48, "step_min": 30},
    "7d": {"points": 42, "step_min": 240},
}


def calculate_p95(latencies: List[float]) -> float:
    """Calculate 95th percentile latency using standard linear interpolation."""
    if not latencies:
        return 0.0
    sorted_lat = sorted(latencies)
    k = (len(sorted_lat) - 1) * 0.95
    f = int(k)
    c = f + 1
    if c < len(sorted_lat):
        val = sorted_lat[f] + (k - f) * (sorted_lat[c] - sorted_lat[f])
    else:
        val = sorted_lat[f]
    return round(val, 2)


class MetricsService:
    @staticmethod
    def get_metrics(
        db: Session,
        user: User,
        api_id: Optional[str] = None,
        time_range: TimeRange = "24h",
    ) -> List[MetricPoint]:
        """Aggregate real time-series metrics over persisted test results.

        - Ownership-scoped to the authenticated user.
        - Verifies API exists and belongs to the user if a specific api_id is requested.
        - Employs fixed-interval bucketing matching frontend visualization contracts.
        - Calculates latency (avg, p95), requests, 4xx/5xx/overall error rates, timeouts, and availability.
        - Empty buckets produce 0 requests and null availability (None) with 0.0 latency/error rates.
        """
        # Validate time_range
        spec = RANGE_SPEC.get(time_range)
        if not spec:
            raise AppException(
                status_code=400,
                code="INVALID_RANGE",
                message="Invalid time range. Supported: 1h, 6h, 24h, 7d",
            )

        points = spec["points"]
        step_min = spec["step_min"]
        step_seconds = step_min * 60

        # Ownership validation if specific API is targeted
        if api_id and api_id.lower() != "all":
            api = db.scalar(
                select(ApiEndpoint).where(
                    ApiEndpoint.id == api_id,
                    ApiEndpoint.user_id == user.id,
                )
            )
            if not api:
                raise AppException(
                    status_code=404,
                    code="NOT_FOUND",
                    message="API not found",
                )

        now = datetime.now(timezone.utc)
        window_duration = timedelta(minutes=points * step_min)
        window_start = now - window_duration

        # Query test results within the window, selecting only required metric fields
        stmt = (
            select(
                TestResultRecord.tested_at,
                TestResultRecord.latency_ms,
                TestResultRecord.passed,
                TestResultRecord.outcome,
                TestResultRecord.status_code,
            )
            .where(
                TestResultRecord.user_id == user.id,
                TestResultRecord.tested_at >= window_start,
                TestResultRecord.tested_at <= now,
            )
            .order_by(TestResultRecord.tested_at.asc())
        )

        if api_id and api_id.lower() != "all":
            stmt = stmt.where(TestResultRecord.api_id == api_id)

        rows = db.execute(stmt).all()

        # Bucket structures: list of dicts for each bucket index
        buckets: List[Dict] = []
        for i in range(points):
            bucket_time = now - timedelta(minutes=(points - i) * step_min)
            buckets.append({
                "t": bucket_time.isoformat(),
                "requests": 0,
                "latencies": [],
                "passed": 0,
                "status_4xx": 0,
                "status_5xx": 0,
                "timeouts": 0,
                "failures": 0,
            })

        # Partition rows into time buckets
        for tested_at, latency_ms, passed, outcome, status_code in rows:
            if tested_at.tzinfo is None:
                tested_at = tested_at.replace(tzinfo=timezone.utc)

            offset_sec = (tested_at - window_start).total_seconds()
            if offset_sec < 0:
                continue

            bucket_idx = int(offset_sec // step_seconds)
            if bucket_idx >= points:
                bucket_idx = points - 1

            b = buckets[bucket_idx]
            b["requests"] += 1
            if latency_ms is not None:
                b["latencies"].append(float(latency_ms))
            if passed:
                b["passed"] += 1
            else:
                b["failures"] += 1

            if outcome == "timeout":
                b["timeouts"] += 1

            if status_code is not None:
                if 400 <= status_code < 500:
                    b["status_4xx"] += 1
                elif 500 <= status_code < 600:
                    b["status_5xx"] += 1

        # Formulate output metric points
        metric_points: List[MetricPoint] = []
        for b in buckets:
            reqs = b["requests"]
            if reqs > 0:
                lats = b["latencies"]
                avg_lat = round(sum(lats) / len(lats), 2) if lats else 0.0
                p95_lat = calculate_p95(lats)
                e4 = round((b["status_4xx"] / reqs) * 100.0, 2)
                e5 = round((b["status_5xx"] / reqs) * 100.0, 2)
                err_rate = round((b["failures"] / reqs) * 100.0, 2)
                avail = round((b["passed"] / reqs) * 100.0, 2)
                timeouts = b["timeouts"]
            else:
                avg_lat = 0.0
                p95_lat = 0.0
                e4 = 0.0
                e5 = 0.0
                err_rate = 0.0
                timeouts = 0
                avail = None

            metric_points.append(
                MetricPoint(
                    t=b["t"],
                    avgLatency=avg_lat,
                    p95Latency=p95_lat,
                    requests=reqs,
                    errorRate4xx=e4,
                    errorRate5xx=e5,
                    errorRate=err_rate,
                    timeouts=timeouts,
                    availability=avail,
                )
            )

        return metric_points
