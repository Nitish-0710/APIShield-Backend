import json
from pathlib import Path
import pytest

from airflow.dags.dag_telemetry_prep import (
    task_extract_monitoring_telemetry,
    task_validate_data_quality,
)
from airflow.dags.dag_model_training import (
    task_check_dataset_readiness,
    task_train_and_evaluate_model,
    task_verify_model_promotion,
)


def test_airflow_dag_files_import_cleanly():
    """Verify that Airflow DAG Python files import cleanly without raising errors."""
    import airflow.dags.dag_telemetry_prep as prep_module
    import airflow.dags.dag_model_training as train_module

    assert hasattr(prep_module, "task_extract_monitoring_telemetry")
    assert hasattr(train_module, "task_train_and_evaluate_model")


def test_airflow_telemetry_prep_task_execution(tmp_path: Path, monkeypatch, db_session):
    """Verify data prep task logic can be executed standalone."""
    monkeypatch.chdir(tmp_path)

    # Run extraction (database has 0 records in fresh test dir, should return insufficient_data gracefully)
    res = task_extract_monitoring_telemetry(db=db_session)
    assert res["status"] in ("ready", "insufficient_data")

    # Run quality validation
    val_res = task_validate_data_quality()
    assert val_res["status"] in ("valid", "insufficient_data")


def test_airflow_model_training_task_execution(tmp_path: Path, monkeypatch):
    """Verify model training task logic executes and enforces promotion policy."""
    monkeypatch.chdir(tmp_path)

    # 1. Create a ready test dataset
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    dataset_file = data_dir / "telemetry_dataset.json"

    X = [[100.0, 150.0, 100.0, 10.0, 200.0, 1.0, 0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 10.0, 12.0, 2.0]] * 10 + \
        [[1500.0, 2000.0, 1500.0, 200.0, 3000.0, 2.5, 50.0, 20.0, 0.0, 50.0, 50.0, 3.0, 10.0, 12.0, 2.0]] * 10
    y = [0] * 10 + [1] * 10

    test_data = {
        "status": "ready",
        "train": {"X": X, "y": y},
        "val": {"X": X, "y": y},
        "samples_count": 20,
    }
    with open(dataset_file, "w", encoding="utf-8") as f:
        json.dump(test_data, f)

    # 2. Check dataset readiness task
    ready_res = task_check_dataset_readiness()
    assert ready_res["ready"] is True

    # 3. Train & evaluate task
    train_res = task_train_and_evaluate_model()
    assert train_res["success"] is True

    # 4. Verify promotion task
    promo_res = task_verify_model_promotion()
    assert promo_res["is_promoted"] is True
