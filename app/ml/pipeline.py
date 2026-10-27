import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.db.session import SessionLocal
from app.ml.dataset import TelemetryDatasetBuilder
from app.ml.mlflow_tracker import MLflowTracker
from app.ml.model import ModelTrainer
from app.models.test_result import TestResultRecord


def prepare_dataset_from_db(
    output_path: str = "data/telemetry_dataset.json",
    api_id: str | None = None,
    limit: int = 1000,
    db: Any | None = None,
) -> dict[str, Any]:
    """
    Reads persisted monitoring observations from database and exports versioned dataset.
    """
    builder = TelemetryDatasetBuilder()

    def _query_and_extract(session) -> list[dict[str, Any]]:
        query = session.query(TestResultRecord)
        if api_id:
            query = query.filter(TestResultRecord.api_id == api_id)
        records_models = query.order_by(TestResultRecord.tested_at.asc()).limit(limit).all()

        return [
            {
                "id": r.id,
                "api_id": r.api_id,
                "passed": r.passed,
                "outcome": r.outcome,
                "status_code": r.status_code,
                "latency_ms": r.latency_ms,
                "tested_at": r.tested_at,
            }
            for r in records_models
        ]

    if db is not None:
        records = _query_and_extract(db)
    else:
        with SessionLocal() as session:
            records = _query_and_extract(session)

    dataset = builder.build_dataset_from_records(records)
    saved_path = builder.save_dataset_artifact(dataset, output_path)
    return {
        "status": dataset.get("status"),
        "samples_count": dataset.get("samples_count", 0),
        "artifact_path": saved_path,
        "class_distribution": dataset.get("class_distribution", {}),
    }


def train_and_log_pipeline(
    dataset_path: str = "data/telemetry_dataset.json",
    artifact_dir: str = "artifacts/models",
) -> dict[str, Any]:
    """
    Runs model training, baseline evaluation, promotion check, and MLflow tracking.
    """
    path = Path(dataset_path)
    if not path.exists():
        return {
            "success": False,
            "status": "error",
            "reason": f"Dataset file not found at {dataset_path}",
        }

    with open(path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    trainer = ModelTrainer(artifact_dir=artifact_dir)
    train_result = trainer.train_and_evaluate(dataset)

    if train_result.get("success"):
        tracker = MLflowTracker()
        tracker.log_training_run(
            model_version=train_result["model_version"],
            model_type=train_result["model_type"],
            params={"window_size": dataset.get("metadata", {}).get("window_size", 5)},
            metrics={
                "f1": train_result["candidate_metrics"]["f1"],
                "accuracy": train_result["candidate_metrics"]["accuracy"],
                "precision": train_result["candidate_metrics"]["precision"],
                "recall": train_result["candidate_metrics"]["recall"],
                "baseline_f1": train_result["baseline_metrics"]["f1"],
            },
            is_promoted=train_result["is_promoted"],
            dataset_meta=dataset.get("metadata"),
            model_obj=trainer.latest_candidate_model,
        )

    return train_result


def evaluate_candidate_pipeline(
    dataset_path: str = "data/experimental_telemetry_dataset.json",
    output_dir: str = "artifacts/experimental",
) -> dict[str, Any]:
    """
    Runs isolated candidate training, validation model selection, and holdout evaluation.
    Guaranteed not to promote or overwrite production model artifacts.
    """
    from app.ml.candidate_evaluator import IsolatedCandidateEvaluator

    evaluator = IsolatedCandidateEvaluator(dataset_path=dataset_path, output_dir=output_dir)
    return evaluator.run_evaluation()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="APIShield ML Pipeline")
    parser.add_argument("action", choices=["prepare", "train", "evaluate-candidate"])
    parser.add_argument("--dataset-path", default=None)
    parser.add_argument("--output-dir", default="artifacts/experimental")
    parser.add_argument("--api-id", default=None)
    args = parser.parse_args()

    if args.action == "prepare":
        path = args.dataset_path or "data/telemetry_dataset.json"
        res = prepare_dataset_from_db(output_path=path, api_id=args.api_id)
        print(json.dumps(res, indent=2))
    elif args.action == "train":
        path = args.dataset_path or "data/telemetry_dataset.json"
        res = train_and_log_pipeline(dataset_path=path)
        print(json.dumps(res, indent=2))
    elif args.action == "evaluate-candidate":
        path = args.dataset_path or "data/experimental_telemetry_dataset.json"
        res = evaluate_candidate_pipeline(dataset_path=path, output_dir=args.output_dir)
        print(json.dumps(res, indent=2))
