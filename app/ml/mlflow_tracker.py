import json
import logging
import os
import uuid
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MLflowTracker:
    """
    MLflow Tracking and Model Registry integration for APIShield training runs.
    Logs parameters, metrics, dataset metadata, and artifacts.
    Registers candidate models and handles promotion states (e.g. production, staging).
    Maintains a robust local JSONL fallback store for offline development.
    """

    DEFAULT_REGISTERED_MODEL = "apishield_failure_detector"

    def __init__(
        self,
        experiment_name: str = "apishield_failure_prediction",
        tracking_dir: str = "mlruns",
    ):
        self.experiment_name = experiment_name
        self.tracking_dir = Path(tracking_dir)
        self.tracking_dir.mkdir(parents=True, exist_ok=True)
        self.is_mlflow_available = False
        self._mlflow = None
        self._client = None
        self.tracking_uri = ""
        self._init_mlflow()

    def _init_mlflow(self) -> None:
        try:
            import mlflow
            from mlflow.tracking import MlflowClient

            # Use env var if configured, otherwise local SQLite DB in tracking_dir for full Registry support
            env_uri = os.environ.get("MLFLOW_TRACKING_URI")
            if env_uri:
                self.tracking_uri = env_uri
            else:
                db_path = (self.tracking_dir / "mlflow.db").resolve().as_posix()
                self.tracking_uri = f"sqlite:///{db_path}"

            mlflow.set_tracking_uri(self.tracking_uri)
            mlflow.set_experiment(self.experiment_name)
            self._mlflow = mlflow
            self._client = MlflowClient(tracking_uri=self.tracking_uri)
            self.is_mlflow_available = True
        except Exception as e:
            logger.warning(f"Native MLflow unavailable, falling back to local JSON file tracking: {e}")
            self.is_mlflow_available = False
            self._mlflow = None
            self._client = None

    def log_training_run(
        self,
        model_version: str,
        model_type: str,
        params: dict[str, Any],
        metrics: dict[str, Any],
        is_promoted: bool,
        dataset_meta: dict[str, Any] | None = None,
        model_obj: Any | None = None,
    ) -> dict[str, Any]:
        """
        Logs a training run with parameters, metrics, tags, and promotion outcome.
        Registers the model in MLflow Model Registry and sets alias/tag if promoted.
        """
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        run_timestamp = datetime.now(UTC).isoformat()
        reg_model_name = self.DEFAULT_REGISTERED_MODEL
        reg_version = None
        promotion_status = "promoted" if is_promoted else "rejected_inferior"

        run_record: dict[str, Any] = {
            "run_id": run_id,
            "experiment_name": self.experiment_name,
            "model_version": model_version,
            "model_type": model_type,
            "params": params,
            "metrics": metrics,
            "is_promoted": is_promoted,
            "promotion_status": promotion_status,
            "dataset_meta": dataset_meta or {},
            "timestamp": run_timestamp,
            "backend": "mlflow_native" if self.is_mlflow_available else "local_file_tracking",
            "registered_model_name": reg_model_name if is_promoted else None,
            "registered_model_version": None,
        }

        # 1. Native MLflow Run & Registration
        if self.is_mlflow_available and self._mlflow is not None and self._client is not None:
            try:
                # Ensure registered model exists
                try:
                    self._client.get_registered_model(reg_model_name)
                except Exception:
                    try:
                        self._client.create_registered_model(
                            reg_model_name,
                            description="APIShield automated API failure detection model",
                        )
                    except Exception:
                        pass

                with self._mlflow.start_run(run_name=model_version) as active_run:
                    actual_run_id = active_run.info.run_id
                    run_record["run_id"] = actual_run_id
                    run_record["artifact_uri"] = active_run.info.artifact_uri

                    # Log params
                    if params:
                        self._mlflow.log_params(params)

                    # Log scalar metrics
                    scalar_metrics = {
                        k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))
                    }
                    if scalar_metrics:
                        self._mlflow.log_metrics(scalar_metrics)

                    # Set tags
                    self._mlflow.set_tags({
                        "model_version": model_version,
                        "model_type": model_type,
                        "is_promoted": str(is_promoted),
                        "promotion_status": promotion_status,
                    })

                    # If model object is provided, log it and register
                    if model_obj is not None:
                        try:
                            import mlflow.sklearn
                            mlflow.sklearn.log_model(
                                model_obj,
                                name="model",
                                skops_trusted_types=["sklearn.tree._tree.Tree"],
                            )
                            # Register model version
                            source_uri = f"{active_run.info.artifact_uri}/model"
                            mv = self._client.create_model_version(
                                name=reg_model_name,
                                source=source_uri,
                                run_id=actual_run_id,
                                description=f"Candidate model version {model_version} (Promoted: {is_promoted})",
                            )
                            reg_version = str(mv.version)
                            run_record["registered_model_version"] = reg_version

                            # Set alias / tag
                            target_alias = "production" if is_promoted else "staging"
                            try:
                                self._client.set_registered_model_alias(reg_model_name, target_alias, reg_version)
                                self._client.set_model_version_tag(reg_model_name, reg_version, "stage", target_alias)
                            except Exception as alias_err:
                                logger.warning(f"Could not set MLflow model alias: {alias_err}")
                        except Exception as log_err:
                            logger.warning(f"Could not log/register sklearn model: {log_err}")
                            run_record["mlflow_model_log_error"] = str(log_err)
            except Exception as e:
                logger.warning(f"Error during MLflow run logging: {e}")
                run_record["mlflow_error"] = str(e)

        # 2. Local Fallback JSONL Run Log
        history_file = self.tracking_dir / "runs_history.jsonl"
        try:
            with open(history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(run_record) + "\n")
        except Exception as e:
            logger.warning(f"Could not write local runs_history.jsonl: {e}")

        return run_record

    def list_experiments(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Retrieves training runs and experiment records from MLflow if available,
        falling back to local runs_history.jsonl.
        """
        runs: list[dict[str, Any]] = []

        if self.is_mlflow_available and self._mlflow is not None and self._client is not None:
            try:
                exp = self._client.get_experiment_by_name(self.experiment_name)
                if exp:
                    mlflow_runs = self._client.search_runs(
                        experiment_ids=[exp.experiment_id],
                        max_results=limit,
                    )
                    for r in mlflow_runs:
                        runs.append({
                            "run_id": r.info.run_id,
                            "experiment_name": self.experiment_name,
                            "model_version": r.data.tags.get("model_version", r.info.run_name or r.info.run_id),
                            "model_type": r.data.tags.get("model_type", "unknown"),
                            "params": r.data.params,
                            "metrics": r.data.metrics,
                            "is_promoted": r.data.tags.get("is_promoted", "False") == "True",
                            "promotion_status": r.data.tags.get("promotion_status", "unknown"),
                            "backend": "mlflow_native",
                            "timestamp": datetime.fromtimestamp(r.info.start_time / 1000.0, UTC).isoformat(),
                            "status": r.info.status,
                            "artifact_uri": r.info.artifact_uri,
                        })
                    return runs
            except Exception as e:
                logger.warning(f"Failed to query MLflow runs, reading fallback: {e}")

        # Fallback to runs_history.jsonl
        history_file = self.tracking_dir / "runs_history.jsonl"
        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                runs.append(json.loads(line))
                            except Exception:
                                pass
            except Exception as e:
                logger.warning(f"Error reading runs_history.jsonl: {e}")

        runs.reverse()
        return runs[:limit]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Retrieves details of a specific training run by run_id."""
        if self.is_mlflow_available and self._client is not None:
            try:
                r = self._client.get_run(run_id)
                return {
                    "run_id": r.info.run_id,
                    "experiment_name": self.experiment_name,
                    "model_version": r.data.tags.get("model_version", r.info.run_name or r.info.run_id),
                    "model_type": r.data.tags.get("model_type", "unknown"),
                    "params": r.data.params,
                    "metrics": r.data.metrics,
                    "is_promoted": r.data.tags.get("is_promoted", "False") == "True",
                    "promotion_status": r.data.tags.get("promotion_status", "unknown"),
                    "backend": "mlflow_native",
                    "timestamp": datetime.fromtimestamp(r.info.start_time / 1000.0, UTC).isoformat(),
                    "status": r.info.status,
                    "artifact_uri": r.info.artifact_uri,
                }
            except Exception:
                pass

        # Check fallback file
        for r in self.list_experiments(limit=200):
            if r.get("run_id") == run_id:
                return r
        return None

    def list_model_versions(self, model_name: str | None = None) -> list[dict[str, Any]]:
        """
        Lists registered model versions from MLflow Model Registry or latest_model_meta.json.
        """
        name = model_name or self.DEFAULT_REGISTERED_MODEL
        versions: list[dict[str, Any]] = []

        if self.is_mlflow_available and self._client is not None:
            try:
                mvs = self._client.search_model_versions(f"name = '{name}'")
                for mv in mvs:
                    versions.append({
                        "model_name": name,
                        "version": str(mv.version),
                        "status": mv.status,
                        "stage": mv.current_stage or "None",
                        "aliases": list(mv.aliases) if hasattr(mv, "aliases") else [],
                        "run_id": mv.run_id,
                        "source": mv.source,
                        "created_at": datetime.fromtimestamp(mv.creation_timestamp / 1000.0, UTC).isoformat(),
                    })
                if versions:
                    return versions
            except Exception as e:
                logger.warning(f"Error querying MLflow model versions: {e}")

        # Fallback to local latest_model_meta.json
        meta_path = Path("artifacts/models/latest_model_meta.json")
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                versions.append({
                    "model_name": name,
                    "version": meta.get("model_version", "1"),
                    "status": "promoted" if meta.get("is_promoted") else "rejected",
                    "stage": "Production" if meta.get("is_promoted") else "Staging",
                    "aliases": ["production"] if meta.get("is_promoted") else [],
                    "run_id": "local_artifact",
                    "source": "artifacts/models/latest_model.joblib",
                    "created_at": meta.get("trained_at", datetime.now(UTC).isoformat()),
                    "metrics": meta.get("candidate_metrics", {}),
                })
            except Exception:
                pass

        return versions
