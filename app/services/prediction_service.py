import json
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from sqlalchemy.orm import Session

from app.core.errors import AppException
from app.models.api import ApiEndpoint
from app.models.ml import PredictionRecord
from app.models.test_result import TestResultRecord
from app.ml.dataset import TelemetryDatasetBuilder
from app.ml.diagnostics import DiagnosticEngine
from app.ml.explainability import ModelExplainer
from app.ml.features import FEATURE_NAMES, extract_features_from_observations, feature_vector
from app.ml.model import RuleBasedBaseline
from app.ml.provenance import PredictionProvenance, resolve_prediction_provenance


class PredictionService:
    def __init__(self, artifact_dir: Optional[Union[str, Path]] = None):
        self.artifact_dir_spec = artifact_dir or "artifacts/models"
        self.artifact_dir = self._resolve_artifact_dir(self.artifact_dir_spec)
        self.baseline = RuleBasedBaseline()
        self.explainer = ModelExplainer()
        self.cached_model = None
        self.model_version: Optional[str] = None
        self.expected_feature_names: List[str] = list(FEATURE_NAMES)
        self._model_mtime: Optional[float] = None
        self._load_cached_model()

    def _resolve_artifact_dir(self, spec: Union[str, Path]) -> Path:
        p = Path(spec)
        if p.is_absolute() and p.exists():
            return p

        candidates = [
            Path.cwd() / p,
            Path(__file__).resolve().parent.parent.parent / p,
            Path(__file__).resolve().parent.parent.parent.parent / p,
        ]

        for cand in candidates:
            if (cand / "latest_model.joblib").exists() or (cand / "latest_model_meta.json").exists():
                return cand

        for cand in candidates:
            if cand.exists():
                return cand

        return Path.cwd() / p

    def _load_cached_model(self) -> None:
        """
        Loads the promoted model artifact and its metadata.
        Validates promotion status, feature contract, and model compatibility.
        Safely falls back on missing, corrupt, incompatible, or unpromoted artifacts.
        """
        model_path = self.artifact_dir / "latest_model.joblib"
        if not model_path.exists():
            self.artifact_dir = self._resolve_artifact_dir(self.artifact_dir_spec)
            model_path = self.artifact_dir / "latest_model.joblib"

        if not model_path.exists():
            self._reset_model_state()
            return

        meta_path = self.artifact_dir / "latest_model_meta.json"
        if not meta_path.exists():
            # Missing metadata prevents verification of promotion or feature contract
            self._reset_model_state()
            return

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            is_promoted = bool(meta.get("is_promoted", False))
            if not is_promoted:
                self._reset_model_state()
                return

            model_version = meta.get("model_version")
            if not model_version:
                self._reset_model_state()
                return

            expected_features = meta.get("feature_names")
            if not expected_features or not isinstance(expected_features, list):
                expected_features = list(FEATURE_NAMES)

            import joblib
            model = joblib.load(model_path)

            if not hasattr(model, "predict"):
                self._reset_model_state()
                return

            expected_n = len(expected_features)
            model_n = getattr(model, "n_features_in_", expected_n)
            if model_n != expected_n:
                # Incompatible feature vector dimension
                self._reset_model_state()
                return

            # Model successfully validated
            self.cached_model = model
            self.model_version = str(model_version)
            self.expected_feature_names = [str(f) for f in expected_features]
            self._model_mtime = model_path.stat().st_mtime
            self.explainer = ModelExplainer(model=self.cached_model)

        except Exception:
            self._reset_model_state()

    def _reset_model_state(self) -> None:
        self.cached_model = None
        self.model_version = None
        self.expected_feature_names = list(FEATURE_NAMES)
        self._model_mtime = None
        self.explainer = ModelExplainer(model=None)

    def _ensure_model_loaded(self) -> None:
        """
        Dynamically refreshes the loaded model if an artifact was created after
        service initialization, or hot-reloads if the artifact mtime changed.
        """
        model_path = self.artifact_dir / "latest_model.joblib"
        if not model_path.exists():
            new_dir = self._resolve_artifact_dir(self.artifact_dir_spec)
            if (new_dir / "latest_model.joblib").exists():
                self.artifact_dir = new_dir
                model_path = self.artifact_dir / "latest_model.joblib"

        if model_path.exists():
            try:
                current_mtime = model_path.stat().st_mtime
                if self.cached_model is None or self._model_mtime != current_mtime:
                    self._load_cached_model()
            except Exception:
                pass
        else:
            if self.cached_model is not None:
                self._reset_model_state()

    def predict_api_risk(
        self,
        db: Session,
        api_id: str,
        user_id: str,
        override_features: Optional[Dict[str, float]] = None,
        is_demo: bool = False,
        explain_method: str = "shap",
    ) -> PredictionRecord:
        """
        Runs failure risk inference for an authenticated user's API endpoint.
        Persists the prediction record with explicit provenance, features, and explainability.
        """
        start_time = time.perf_counter()

        # 1. Ownership & existence check
        api = db.query(ApiEndpoint).filter(ApiEndpoint.id == api_id, ApiEndpoint.user_id == user_id).first()
        if not api:
            raise AppException(status_code=404, code="NOT_FOUND", message="API endpoint not found")

        # 2. Extract features
        if override_features:
            features = override_features
        else:
            recent_tests = (
                db.query(TestResultRecord)
                .filter(TestResultRecord.api_id == api_id)
                .order_by(TestResultRecord.tested_at.desc())
                .limit(15)
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

        # 3. Model Inference & Provenance
        self._ensure_model_loaded()

        has_active_model = self.cached_model is not None
        provenance = resolve_prediction_provenance(has_active_trained_model=has_active_model, is_demo_mode=is_demo)
        model_version = self.model_version if provenance == PredictionProvenance.TRAINED_MODEL.value else None

        if provenance == PredictionProvenance.TRAINED_MODEL.value and self.cached_model is not None:
            try:
                feature_order = self.expected_feature_names or FEATURE_NAMES
                vec = [[float(features.get(name, 0.0)) for name in feature_order]]
                pred_raw = int(self.cached_model.predict(vec)[0])
                if hasattr(self.cached_model, "predict_proba"):
                    probs = self.cached_model.predict_proba(vec)[0]
                    risk_score = round(float(probs[1]) * 100.0, 1) if len(probs) > 1 else (100.0 if pred_raw == 1 else 0.0)
                else:
                    risk_score = 80.0 if pred_raw == 1 else 15.0

                prediction = pred_raw
                if risk_score >= 70.0:
                    risk_level = "critical" if risk_score >= 85.0 else "high"
                elif risk_score >= 35.0:
                    risk_level = "medium"
                else:
                    risk_level = "low"
            except Exception:
                # Transparent fallback
                provenance = PredictionProvenance.RULES_BASELINE.value
                model_version = None
                prediction, risk_score, risk_level, _ = self.baseline.predict_one(features)
        else:
            provenance = PredictionProvenance.RULES_BASELINE.value
            model_version = None
            prediction, risk_score, risk_level, _ = self.baseline.predict_one(features)

        # 4. Explainability
        explanation = self.explainer.explain(
            features, risk_score, provenance, feature_names=self.expected_feature_names, method=explain_method
        )

        inference_duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        # 5. Persist record
        record = PredictionRecord(
            api_id=api_id,
            user_id=user_id,
            risk_score=risk_score,
            risk_level=risk_level,
            prediction=prediction,
            provenance=provenance,
            model_version=model_version,
            features=features,
            explanation=explanation,
            inference_duration_ms=inference_duration_ms,
            created_at=datetime.now(timezone.utc),
        )
        db.add(record)

        # Update ApiEndpoint cached risk summary
        api.risk = risk_level
        api.risk_score = risk_score

        try:
            from app.core.metrics import PREDICTIONS_TOTAL, PREDICTION_DURATION_SECONDS
            PREDICTIONS_TOTAL.labels(provenance=provenance, risk_level=risk_level).inc()
            PREDICTION_DURATION_SECONDS.observe(inference_duration_ms / 1000.0)
        except Exception:
            pass

        db.commit()
        db.refresh(record)
        return record

    def list_prediction_history(
        self,
        db: Session,
        user_id: str,
        api_id: Optional[str] = None,
        provenance: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[int, List[PredictionRecord]]:
        query = db.query(PredictionRecord).filter(PredictionRecord.user_id == user_id)
        if api_id:
            query = query.filter(PredictionRecord.api_id == api_id)
        if provenance:
            query = query.filter(PredictionRecord.provenance == provenance)

        total = query.count()
        items = query.order_by(PredictionRecord.created_at.desc()).offset(offset).limit(limit).all()
        return total, items
