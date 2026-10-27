from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict

logger = logging.getLogger(__name__)


def get_backend_dir() -> Path:
    env_dir = os.environ.get("APISHIELD_BACKEND_DIR")
    if env_dir and Path(env_dir).exists():
        return Path(env_dir)
    # Prefer cwd if it has data or app (supports tmp_path tests)
    if (Path.cwd() / "data").exists() or (Path.cwd() / "app").exists():
        return Path.cwd()
    # Check WSL mount
    wsl_cand = Path("/mnt/d/College/3rd_Year/MLOPS/CP/backend")
    if (wsl_cand / "app").exists():
        return wsl_cand
    # Check parent hierarchy
    candidate = Path(__file__).resolve().parent.parent.parent
    if (candidate / "app").exists():
        return candidate
    return Path.cwd()


def run_pipeline_action(action: str, **kwargs) -> Dict[str, Any]:
    backend_dir = get_backend_dir()
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    # 1. Attempt direct python function execution
    try:
        if action == "train":
            from app.ml.pipeline import train_and_log_pipeline
            return train_and_log_pipeline(
                dataset_path=kwargs.get("dataset_path", "data/telemetry_dataset.json"),
                artifact_dir=kwargs.get("artifact_dir", "artifacts/models"),
            )
    except (ImportError, ModuleNotFoundError):
        pass

    # 2. Cross-environment execution via backend virtualenv
    venv_py_win = backend_dir / ".venv" / "Scripts" / "python.exe"
    venv_py_nix = backend_dir / ".venv" / "bin" / "python"

    if venv_py_win.exists():
        py_exe = str(venv_py_win)
    elif venv_py_nix.exists():
        py_exe = str(venv_py_nix)
    else:
        py_exe = sys.executable

    cmd = [py_exe, "-m", "app.ml.pipeline", action]
    if kwargs.get("dataset_path"):
        cmd.extend(["--dataset-path", kwargs["dataset_path"]])

    res = subprocess.run(cmd, cwd=str(backend_dir), capture_output=True, text=True, check=True)
    out = res.stdout.strip()
    start = out.find("{")
    end = out.rfind("}")
    if start != -1 and end != -1:
        return json.loads(out[start : end + 1])
    return {"status": "success", "raw_output": out}


def task_check_dataset_readiness(**context) -> Dict[str, Any]:
    """
    Ensures the prepared dataset artifact exists and has sufficient samples before training.
    """
    backend_dir = get_backend_dir()
    dataset_file = backend_dir / "data" / "telemetry_dataset.json"

    if not dataset_file.exists():
        raise FileNotFoundError(f"Prepared dataset file '{dataset_file}' does not exist.")

    with open(dataset_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("status") != "ready":
        print(f"[Airflow Task] Dataset status is '{data.get('status')}': insufficient observations for model training.")
        return {"ready": False, "status": data.get("status")}

    return {"ready": True, "samples_count": data.get("samples_count", 0)}


def task_train_and_evaluate_model(**context) -> Dict[str, Any]:
    """
    Trains candidate model, evaluates against baseline, and saves evaluation metadata.
    """
    result = run_pipeline_action("train", dataset_path="data/telemetry_dataset.json")
    print(f"[Airflow Task] Training & Evaluation result: {result.get('status')}, Model Version: {result.get('model_version')}")
    return result


def task_verify_model_promotion(**context) -> Dict[str, Any]:
    """
    Validates that model promotion criteria were enforced:
    Prevents invalid or degraded models from replacing valid models.
    """
    backend_dir = get_backend_dir()
    meta_path = backend_dir / "artifacts" / "models" / "latest_model_meta.json"

    if not meta_path.exists():
        raise FileNotFoundError(f"Model metadata artifact missing at {meta_path}.")

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    is_promoted = meta.get("is_promoted", False)
    model_version = meta.get("model_version")

    if is_promoted:
        print(f"[Airflow Task] Candidate model {model_version} met promotion criteria and is ACTIVE.")
    else:
        print(f"[Airflow Task] Candidate model {model_version} was REJECTED (inferior to baseline). Previous active model preserved.")

    return {"is_promoted": is_promoted, "model_version": model_version}


# Airflow DAG definition compatible with Airflow 2.x and 3.x
try:
    from airflow import DAG
    try:
        from airflow.providers.standard.operators.python import PythonOperator
    except ImportError:
        from airflow.operators.python import PythonOperator

    default_args = {
        "owner": "apishield_mlops",
        "depends_on_past": False,
        "email_on_failure": False,
        "email_on_retry": False,
        "retries": 1,
        "retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(minutes=30),
    }

    dag = DAG(
        dag_id="apishield_model_training_and_evaluation",
        default_args=default_args,
        description="Daily reproducible training, baseline comparison, and MLflow logging for APIShield",
        schedule="@daily",
        start_date=datetime(2026, 1, 1),
        catchup=False,
        tags=["apishield", "mlops", "training"],
    )

    t1 = PythonOperator(
        task_id="check_dataset_readiness",
        python_callable=task_check_dataset_readiness,
        dag=dag,
    )

    t2 = PythonOperator(
        task_id="train_and_evaluate_model",
        python_callable=task_train_and_evaluate_model,
        dag=dag,
    )

    t3 = PythonOperator(
        task_id="verify_model_promotion",
        python_callable=task_verify_model_promotion,
        dag=dag,
    )

    t1 >> t2 >> t3

except ImportError:
    # Airflow not installed in local environment; task functions remain directly testable
    dag = None
