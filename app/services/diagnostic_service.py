from typing import Any, Dict
from sqlalchemy.orm import Session

from app.core.errors import AppException
from app.models.api import ApiEndpoint
from app.models.test_result import TestResultRecord
from app.ml.diagnostics import DiagnosticEngine
from app.ml.features import extract_features_from_observations


class DiagnosticService:
    def __init__(self):
        self.engine = DiagnosticEngine()

    def get_api_diagnostics(
        self,
        db: Session,
        api_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        api = db.query(ApiEndpoint).filter(ApiEndpoint.id == api_id, ApiEndpoint.user_id == user_id).first()
        if not api:
            raise AppException(status_code=404, code="NOT_FOUND", message="API endpoint not found")

        recent_tests = (
            db.query(TestResultRecord)
            .filter(TestResultRecord.api_id == api_id)
            .order_by(TestResultRecord.tested_at.desc())
            .limit(20)
            .all()
        )

        obs = [
            {
                "passed": t.passed,
                "outcome": t.outcome,
                "status_code": t.status_code,
                "latency_ms": t.latency_ms,
                "tested_at": t.tested_at,
            }
            for t in reversed(recent_tests)
        ]

        features = extract_features_from_observations(obs)
        return self.engine.analyze(
            api_id=api.id,
            api_name=api.name,
            features=features,
            latency_threshold_ms=float(api.max_latency_ms),
            availability_target=float(api.expected_availability),
        )
