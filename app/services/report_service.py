import csv
from datetime import datetime, timedelta, timezone
import io
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.errors import AppException
from app.models.api import ApiEndpoint
from app.models.ml import AlertRecord, PredictionRecord
from app.models.test_result import TestResultRecord


def sanitize_csv_cell(value: Any) -> str:
    """Prevents CSV formula injection by prepending a single quote if string starts with formula characters."""
    val_str = str(value) if value is not None else ""
    if val_str and val_str[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{val_str}"
    return val_str


class ReportService:
    def get_monitoring_summary(
        self,
        db: Session,
        api_id: str,
        user_id: str,
        time_range: str = "24h",
    ) -> Dict[str, Any]:
        api = db.query(ApiEndpoint).filter(ApiEndpoint.id == api_id, ApiEndpoint.user_id == user_id).first()
        if not api:
            raise AppException(status_code=404, code="NOT_FOUND", message="API endpoint not found")

        range_deltas = {
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
        }
        delta = range_deltas.get(time_range, timedelta(hours=24))
        cutoff = datetime.now(timezone.utc) - delta

        tests = (
            db.query(TestResultRecord)
            .filter(TestResultRecord.api_id == api_id, TestResultRecord.tested_at >= cutoff)
            .order_by(TestResultRecord.tested_at.asc())
            .all()
        )

        total_obs = len(tests)
        latencies = [t.latency_ms for t in tests if t.latency_ms is not None]
        passed_count = sum(1 for t in tests if t.passed)
        error_count = sum(1 for t in tests if t.outcome in ("failure", "error", "timeout") or (t.status_code and t.status_code >= 400))
        timeout_count = sum(1 for t in tests if t.outcome == "timeout")

        availability = round((passed_count / total_obs) * 100.0, 2) if total_obs > 0 else None
        avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else None
        p95_latency = None
        if latencies:
            sorted_lat = sorted(latencies)
            p95_latency = round(sorted_lat[int(0.95 * (len(sorted_lat) - 1))], 2)

        predictions_count = db.query(PredictionRecord).filter(PredictionRecord.api_id == api_id, PredictionRecord.created_at >= cutoff).count()
        high_risk_count = db.query(PredictionRecord).filter(PredictionRecord.api_id == api_id, PredictionRecord.risk_level.in_(["high", "critical"]), PredictionRecord.created_at >= cutoff).count()
        open_alerts_count = db.query(AlertRecord).filter(AlertRecord.api_id == api_id, AlertRecord.status == "open").count()

        return {
            "api_id": api.id,
            "api_name": api.name,
            "time_range": time_range,
            "total_observations": total_obs,
            "availability": availability,
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
            "error_rate": round((error_count / total_obs) * 100.0, 2) if total_obs > 0 else 0.0,
            "timeout_rate": round((timeout_count / total_obs) * 100.0, 2) if total_obs > 0 else 0.0,
            "prediction_count": predictions_count,
            "high_risk_predictions": high_risk_count,
            "open_alerts": open_alerts_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def export_telemetry_csv(
        self,
        db: Session,
        api_id: str,
        user_id: str,
        limit: int = 1000,
    ) -> str:
        """
        Exports sanitized monitoring observations as CSV.
        Explicitly excludes authorization headers, session cookies, and sensitive tokens.
        """
        api = db.query(ApiEndpoint).filter(ApiEndpoint.id == api_id, ApiEndpoint.user_id == user_id).first()
        if not api:
            raise AppException(status_code=404, code="NOT_FOUND", message="API endpoint not found")

        records = (
            db.query(TestResultRecord)
            .filter(TestResultRecord.api_id == api_id)
            .order_by(TestResultRecord.tested_at.desc())
            .limit(limit)
            .all()
        )

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "record_id",
            "api_id",
            "api_name",
            "tested_at",
            "passed",
            "outcome",
            "status_code",
            "expected_status",
            "latency_ms",
            "error",
        ])

        for r in records:
            writer.writerow([
                sanitize_csv_cell(r.id),
                sanitize_csv_cell(r.api_id),
                sanitize_csv_cell(api.name),
                sanitize_csv_cell(r.tested_at.isoformat() if r.tested_at else ""),
                sanitize_csv_cell(r.passed),
                sanitize_csv_cell(r.outcome),
                sanitize_csv_cell(r.status_code),
                sanitize_csv_cell(r.expected_status),
                sanitize_csv_cell(r.latency_ms),
                sanitize_csv_cell(r.error),
            ])

        return output.getvalue()
