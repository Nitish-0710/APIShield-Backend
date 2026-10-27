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
        if action == "prepare":
            from app.ml.pipeline import prepare_dataset_from_db
            return prepare_dataset_from_db(
                output_path=kwargs.get("output_path", "data/telemetry_dataset.json"),
                db=kwargs.get("db"),
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
    if kwargs.get("output_path"):
        cmd.extend(["--dataset-path", kwargs["output_path"]])

    res = subprocess.run(cmd, cwd=str(backend_dir), capture_output=True, text=True, check=True)
    out = res.stdout.strip()
    start = out.find("{")
    end = out.rfind("}")
    if start != -1 and end != -1:
        return json.loads(out[start : end + 1])
    return {"status": "success", "raw_output": out}


def task_extract_monitoring_telemetry(db=None, **context) -> Dict[str, Any]:
    """
    Reads monitoring observations and exports versioned telemetry dataset artifact.
    """
    result = run_pipeline_action("prepare", output_path="data/telemetry_dataset.json", db=db)
    print(f"[Airflow Task] Telemetry preparation completed: status={result.get('status')}, samples={result.get('samples_count', 0)}")
    return result


def task_validate_data_quality(**context) -> Dict[str, Any]:
    """
    Validates data quality, class distribution, and feature presence.
    """
    backend_dir = get_backend_dir()
    dataset_file = backend_dir / "data" / "telemetry_dataset.json"

    if not dataset_file.exists():
        raise FileNotFoundError(f"Telemetry dataset artifact missing at {dataset_file}")

    with open(dataset_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    status = data.get("status")
    samples_count = data.get("samples_count", 0)

    if status == "insufficient_data":
        print(f"[Airflow Task] Notice: Insufficient real observations ({samples_count} samples). Pipeline marked pending data.")
        return {"status": "insufficient_data", "samples": samples_count}

    if samples_count == 0:
        raise ValueError("Data validation failed: 0 samples generated.")

    print(f"[Airflow Task] Quality validated: {samples_count} samples. Class distribution: {data.get('class_distribution')}")
    return {"status": "valid", "samples": samples_count}


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
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
        "execution_timeout": timedelta(minutes=15),
    }

    dag = DAG(
        dag_id="apishield_telemetry_data_preparation",
        default_args=default_args,
        description="Hourly telemetry extraction, validation, and feature engineering for APIShield",
        schedule="@hourly",
        start_date=datetime(2026, 1, 1),
        catchup=False,
        tags=["apishield", "mlops", "data_prep"],
    )

    t1 = PythonOperator(
        task_id="extract_monitoring_telemetry",
        python_callable=task_extract_monitoring_telemetry,
        dag=dag,
    )

    t2 = PythonOperator(
        task_id="validate_data_quality",
        python_callable=task_validate_data_quality,
        dag=dag,
    )

    t1 >> t2

except ImportError:
    # Airflow not installed in local environment; task functions remain directly testable
    dag = None
