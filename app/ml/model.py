import json
import math
import os
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.ml.features import FEATURE_NAMES, feature_vector


class RuleBasedBaseline:
    """
    Transparent heuristic baseline for API failure prediction.
    Classifies risk based on direct domain thresholds on observed features.
    """

    def __init__(
        self,
        error_rate_threshold: float = 10.0,
        timeout_rate_threshold: float = 5.0,
        consecutive_failures_threshold: int = 2,
        availability_threshold: float = 95.0,
    ):
        self.error_rate_threshold = error_rate_threshold
        self.timeout_rate_threshold = timeout_rate_threshold
        self.consecutive_failures_threshold = consecutive_failures_threshold
        self.availability_threshold = availability_threshold

    def predict_one(self, features: dict[str, float]) -> tuple[int, float, str, dict[str, Any]]:
        """
        Returns (prediction, risk_score, risk_level, reasons).
        prediction: 0 or 1
        risk_score: 0.0 - 100.0
        risk_level: 'low' | 'medium' | 'high' | 'critical'
        """
        reasons: list[str] = []
        score = 0.0

        err_rate = features.get("error_rate", 0.0)
        timeout_rate = features.get("timeout_rate", 0.0)
        consec_fail = features.get("recent_consecutive_failures", 0.0)
        avail = features.get("availability", 100.0)
        trend = features.get("latency_trend", 1.0)
        http_5xx = features.get("http_5xx_rate", 0.0)

        if consec_fail >= self.consecutive_failures_threshold:
            score += 40.0
            reasons.append(f"{int(consec_fail)} consecutive probe failures")

        if err_rate >= self.error_rate_threshold:
            score += 30.0
            reasons.append(f"Elevated error rate ({err_rate}% >= {self.error_rate_threshold}%)")

        if http_5xx > 0:
            score += 25.0
            reasons.append(f"HTTP 5xx server errors detected ({http_5xx}%)")

        if timeout_rate >= self.timeout_rate_threshold:
            score += 25.0
            reasons.append(f"Timeout rate elevated ({timeout_rate}%)")

        if avail < self.availability_threshold:
            score += 20.0
            reasons.append(f"Availability degraded ({avail}% < {self.availability_threshold}%)")

        if trend > 1.5:
            score += 15.0
            reasons.append(f"Latency worsening ({trend}x increase)")

        risk_score = min(max(round(score, 1), 0.0), 100.0)

        if risk_score >= 70.0:
            risk_level = "critical" if risk_score >= 85.0 else "high"
            prediction = 1
        elif risk_score >= 35.0:
            risk_level = "medium"
            prediction = 0
        else:
            risk_level = "low"
            prediction = 0

        explanation = {
            "method": "rules_heuristic",
            "contributing_reasons": reasons if reasons else ["Telemetry within normal operating thresholds"],
            "thresholds": {
                "error_rate": self.error_rate_threshold,
                "timeout_rate": self.timeout_rate_threshold,
                "consecutive_failures": self.consecutive_failures_threshold,
                "availability": self.availability_threshold,
            },
        }

        return prediction, risk_score, risk_level, explanation

    def predict(self, X: list[list[float]]) -> list[int]:
        preds = []
        for vec in X:
            feat_dict = dict(zip(FEATURE_NAMES, vec))
            p, _, _, _ = self.predict_one(feat_dict)
            preds.append(p)
        return preds


def compute_classification_metrics(y_true: list[int], y_pred: list[int]) -> dict[str, Any]:
    """Computes precision, recall, F1, accuracy, and confusion matrix without external dependencies."""
    if len(y_true) != len(y_pred) or not y_true:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "accuracy": 0.0, "confusion_matrix": [[0, 0], [0, 0]]}

    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 1)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 0)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 0 and yp == 1)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == 1 and yp == 0)

    total = len(y_true)
    accuracy = (tp + tn) / total if total > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "confusion_matrix": [
            [tn, fp],
            [fn, tp],
        ],
        "total_samples": total,
    }


class ModelTrainer:
    """
    Trains, evaluates, and validates ML classification models for API failure prediction.
    Enforces candidate validation policies before model promotion.
    """

    def __init__(self, artifact_dir: str = "artifacts/models"):
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.baseline = RuleBasedBaseline()
        self.latest_candidate_model = None

    def train_and_evaluate(self, dataset: dict[str, Any]) -> dict[str, Any]:
        """
        Trains a candidate classifier, evaluates against the rule-based baseline,
        and applies the promotion validation policy.
        """
        if dataset.get("status") != "ready":
            return {
                "success": False,
                "status": "rejected",
                "reason": dataset.get("message", "Dataset is not ready for training."),
            }

        X_train = dataset["train"]["X"]
        y_train = dataset["train"]["y"]
        X_val = dataset["val"]["X"]
        y_val = dataset["val"]["y"]

        if not X_train or not X_val:
            return {
                "success": False,
                "status": "rejected",
                "reason": "Training or validation set is empty.",
            }

        # 1. Evaluate baseline on validation set
        baseline_preds = self.baseline.predict(X_val)
        baseline_metrics = compute_classification_metrics(y_val, baseline_preds)

        # 2. Train candidate model
        candidate_model = None
        candidate_preds = []
        model_type = "RandomForestClassifier"

        try:
            from sklearn.ensemble import RandomForestClassifier
            clf = RandomForestClassifier(n_estimators=30, max_depth=5, random_state=42)
            clf.fit(X_train, y_train)
            candidate_preds = clf.predict(X_val).tolist()
            candidate_model = clf
        except Exception:
            # Fallback to HistGradientBoosting or baseline if sklearn is not ready
            candidate_preds = baseline_preds
            model_type = "RulesBaselineFallback"

        self.latest_candidate_model = candidate_model
        candidate_metrics = compute_classification_metrics(y_val, candidate_preds)

        # 3. Model Promotion Policy:
        # A candidate model is promoted only if its F1 or accuracy is >= baseline metrics
        is_promoted = (
            candidate_metrics["f1"] >= baseline_metrics["f1"]
            or candidate_metrics["accuracy"] >= baseline_metrics["accuracy"]
        )

        model_version = f"model_v{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"

        result = {
            "success": True,
            "status": "promoted" if is_promoted else "rejected_inferior",
            "model_version": model_version,
            "model_type": model_type,
            "is_promoted": is_promoted,
            "candidate_metrics": candidate_metrics,
            "baseline_metrics": baseline_metrics,
            "dataset_samples": dataset.get("samples_count", 0),
            "trained_at": datetime.now(UTC).isoformat(),
            "feature_names": FEATURE_NAMES,
        }

        # Save metadata artifact
        meta_path = self.artifact_dir / "latest_model_meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        # Save model weights/artifact if candidate model exists
        if candidate_model is not None and is_promoted:
            try:
                import joblib
                joblib.dump(candidate_model, self.artifact_dir / "latest_model.joblib")
            except Exception:
                pass

        return result
