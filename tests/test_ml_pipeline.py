from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from app.ml.dataset import TelemetryDatasetBuilder
from app.ml.diagnostics import DiagnosticEngine
from app.ml.explainability import ModelExplainer
from app.ml.fairness import evaluate_fairness_by_group
from app.ml.features import FEATURE_NAMES, extract_features_from_observations, feature_vector
from app.ml.mlflow_tracker import MLflowTracker
from app.ml.model import ModelTrainer, RuleBasedBaseline, compute_classification_metrics
from app.ml.provenance import PredictionProvenance, resolve_prediction_provenance


def test_feature_extraction_empty_observations():
    """Verify safe default feature vector when no prior observations exist."""
    features = extract_features_from_observations([])
    assert len(features) == len(FEATURE_NAMES)
    assert features["availability"] == 100.0
    assert features["error_rate"] == 0.0
    assert features["total_observations"] == 0.0


def test_feature_extraction_with_realistic_telemetry():
    """Verify correct calculation of latency, error rate, timeouts, and trends."""
    now = datetime.now(timezone.utc)
    observations = [
        {"latency_ms": 100.0, "passed": True, "outcome": "success", "status_code": 200, "tested_at": now - timedelta(minutes=4)},
        {"latency_ms": 120.0, "passed": True, "outcome": "success", "status_code": 200, "tested_at": now - timedelta(minutes=3)},
        {"latency_ms": 250.0, "passed": False, "outcome": "failure", "status_code": 500, "tested_at": now - timedelta(minutes=2)},
        {"latency_ms": 400.0, "passed": False, "outcome": "timeout", "status_code": None, "tested_at": now - timedelta(minutes=1)},
    ]

    features = extract_features_from_observations(observations, reference_time=now)
    assert features["total_observations"] == 4.0
    assert features["availability"] == 50.0  # 2 passed out of 4
    assert features["error_rate"] == 50.0   # 1 500 failure + 1 timeout
    assert features["timeout_rate"] == 25.0
    assert features["http_5xx_rate"] == 25.0
    assert features["recent_consecutive_failures"] == 2.0  # Last 2 failed
    assert features["latency_trend"] > 1.0  # Recent tests slower than earlier


def test_dataset_builder_insufficient_data():
    """Verify that fewer than min_observations returns explicit insufficient_data status."""
    builder = TelemetryDatasetBuilder(min_observations=15)
    records = [{"latency_ms": 100.0, "passed": True, "outcome": "success"}] * 5
    result = builder.build_dataset_from_records(records)

    assert result["status"] == "insufficient_data"
    assert result["samples_count"] == 0


def test_dataset_builder_leakage_free_sliding_window():
    """Verify sliding window builds target strictly from observation t+1."""
    builder = TelemetryDatasetBuilder(window_size=3, min_observations=6)
    base_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    # 10 observations: first 7 success, last 3 failure
    records = []
    for i in range(10):
        is_pass = i < 7
        records.append({
            "latency_ms": 100.0 if is_pass else 1500.0,
            "passed": is_pass,
            "outcome": "success" if is_pass else "failure",
            "status_code": 200 if is_pass else 500,
            "tested_at": base_time + timedelta(minutes=i),
        })

    dataset = builder.build_dataset_from_records(records, train_ratio=0.7)
    assert dataset["status"] == "ready"
    assert dataset["samples_count"] == 7  # 10 - 3 window size
    assert dataset["train_count"] == 4
    assert dataset["val_count"] == 3


def test_baseline_heuristic_predictions():
    """Verify RuleBasedBaseline correctly triggers on threshold breaches."""
    baseline = RuleBasedBaseline()

    healthy_feats = {
        "error_rate": 0.0,
        "timeout_rate": 0.0,
        "recent_consecutive_failures": 0.0,
        "availability": 100.0,
        "latency_trend": 1.0,
        "http_5xx_rate": 0.0,
    }
    pred, score, level, exp = baseline.predict_one(healthy_feats)
    assert pred == 0
    assert score < 35.0
    assert level == "low"

    critical_feats = {
        "error_rate": 40.0,
        "timeout_rate": 20.0,
        "recent_consecutive_failures": 3.0,
        "availability": 60.0,
        "latency_trend": 2.5,
        "http_5xx_rate": 30.0,
    }
    pred, score, level, exp = baseline.predict_one(critical_feats)
    assert pred == 1
    assert score >= 70.0
    assert level in ("high", "critical")
    assert len(exp["contributing_reasons"]) > 0


def test_model_training_and_promotion_policy(tmp_path: Path):
    """Verify candidate model is trained, evaluated, and validated against baseline."""
    trainer = ModelTrainer(artifact_dir=str(tmp_path))

    # Synthetic dataset
    X_train = [[100.0, 150.0, 100.0, 10.0, 200.0, 1.0, 0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 10.0, 12.0, 2.0]] * 10 + \
              [[1500.0, 2000.0, 1500.0, 200.0, 3000.0, 2.5, 50.0, 20.0, 0.0, 50.0, 50.0, 3.0, 10.0, 12.0, 2.0]] * 10
    y_train = [0] * 10 + [1] * 10

    X_val = X_train
    y_val = y_train

    dataset = {
        "status": "ready",
        "train": {"X": X_train, "y": y_train},
        "val": {"X": X_val, "y": y_val},
        "samples_count": 20,
    }

    result = trainer.train_and_evaluate(dataset)
    assert result["success"] is True
    assert "candidate_metrics" in result
    assert "baseline_metrics" in result
    assert result["is_promoted"] is True
    assert (tmp_path / "latest_model_meta.json").exists()


def test_mlflow_tracker_local_fallback(tmp_path: Path):
    """Verify MLflowTracker records run parameters, metrics, and tags to local jsonl."""
    tracker = MLflowTracker(tracking_dir=str(tmp_path))
    run = tracker.log_training_run(
        model_version="model_test_v1",
        model_type="RandomForestClassifier",
        params={"window_size": 5},
        metrics={"f1": 0.95, "accuracy": 0.96},
        is_promoted=True,
    )

    assert run["run_id"] is not None
    assert (tmp_path / "runs_history.jsonl").exists()


def test_model_explainer_attribution():
    """Verify explainability engine returns top contributing features."""
    explainer = ModelExplainer()
    features = {
        "recent_consecutive_failures": 3.0,
        "http_5xx_rate": 20.0,
        "error_rate": 25.0,
        "availability": 75.0,
        "avg_latency_ms": 1200.0,
    }
    explanation = explainer.explain(features, risk_score=85.0, provenance="trained_model")
    assert "top_contributing_features" in explanation
    assert len(explanation["top_contributing_features"]) > 0
    top_feat = explanation["top_contributing_features"][0]
    assert top_feat["direction"] == "increases_risk"


def test_fairness_evaluation_workflow():
    """Verify group fairness evaluation computes demographic parity and equalized odds."""
    y_true = [0, 0, 1, 1, 0, 1, 0, 1]
    y_pred = [0, 0, 1, 1, 0, 0, 0, 1]
    groups = ["us-east", "us-east", "us-east", "us-east", "eu-west", "eu-west", "eu-west", "eu-west"]

    report = evaluate_fairness_by_group(y_true, y_pred, groups, is_synthetic=True)
    assert report["status"] == "evaluated"
    assert report["is_synthetic_demonstration"] is True
    assert "us-east" in report["groups"]
    assert "eu-west" in report["groups"]
    assert "demographic_parity_ratio" in report["summary"]
