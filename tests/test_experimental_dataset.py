"""
Tests for experimental telemetry dataset generation and validation.

Validates:
1. Deterministic generation with fixed random seed.
2. Sequence coverage (healthy 200s, isolated 500, 5xx bursts, 429/404, timeouts, mixed cascade).
3. Target label construction (strictly observation t+1 failure, no lookahead leakage).
4. Chronological 3-way split (train/validation/test non-overlapping and ordered).
5. Feature variance (non-zero variance for http_4xx_rate and http_5xx_rate across all splits).
6. Recovery sequence dynamics (error rates decay, target marks recovery).
7. Artifact isolation (does not overwrite production telemetry_dataset.json).
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest

from app.ml.dataset import (
    TelemetryDatasetBuilder,
    generate_synthetic_telemetry_stream,
    generate_experimental_dataset,
)
from app.ml.features import FEATURE_NAMES


def test_deterministic_generation():
    """Verify that identical seeds produce identical streams and dataset artifacts."""
    stream_1 = generate_synthetic_telemetry_stream(total_records=200, seed=42)
    stream_2 = generate_synthetic_telemetry_stream(total_records=200, seed=42)
    stream_different = generate_synthetic_telemetry_stream(total_records=200, seed=99)

    assert len(stream_1) == 200
    assert len(stream_2) == 200
    assert stream_1 == stream_2
    assert stream_1 != stream_different


def test_synthetic_stream_sequence_coverage():
    """Verify the stream contains all required failure and recovery sequences."""
    stream = generate_synthetic_telemetry_stream(total_records=500, seed=42)
    status_codes = {r.get("status_code") for r in stream}
    outcomes = {r.get("outcome") for r in stream}

    # Status code coverage
    assert 200 in status_codes, "Stream must include healthy HTTP 200 responses"
    assert 500 in status_codes, "Stream must include HTTP 500 internal server errors"
    assert {502, 503}.intersection(status_codes), "Stream must include HTTP 502/503 server errors"
    assert 429 in status_codes, "Stream must include HTTP 429 rate limit responses"
    assert 404 in status_codes, "Stream must include HTTP 404 not found responses"
    assert None in status_codes or "timeout" in outcomes, "Stream must include timeout events"

    # Verify presence of consecutive healthy records
    healthy_runs = 0
    current_run = 0
    for r in stream:
        if r.get("status_code") == 200 and r.get("passed") is True:
            current_run += 1
            if current_run >= 5:
                healthy_runs += 1
        else:
            current_run = 0
    assert healthy_runs > 0, "Stream must have sustained healthy 200 runs"


def test_target_label_construction_and_no_lookahead_leakage():
    """
    Verify target y strictly reflects observation t+1 failure status and
    that feature extraction only uses the window [t - window_size + 1, t].
    """
    builder = TelemetryDatasetBuilder(window_size=5, min_observations=5)
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)

    # 10 records: first 6 pass, 7th fails, 8th passes, 9th fails, 10th fails
    # indices: 0..5 (pass), 6 (fail), 7 (pass), 8 (fail), 9 (fail)
    pattern = [
        (True, 200),   # 0
        (True, 200),   # 1
        (True, 200),   # 2
        (True, 200),   # 3
        (True, 200),   # 4
        (True, 200),   # 5
        (False, 500),  # 6 -> failure
        (True, 200),   # 7 -> recovery
        (False, 503),  # 8 -> failure
        (False, 500),  # 9 -> failure
    ]

    records = [
        {
            "latency_ms": 100.0 if p else 1500.0,
            "passed": p,
            "outcome": "success" if p else "failure",
            "status_code": sc,
            "tested_at": base_time.replace(minute=i),
        }
        for i, (p, sc) in enumerate(pattern)
    ]

    dataset = builder.build_dataset_from_records(
        records, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2
    )

    # With window_size=5 and 10 records:
    # Sample 0: window [0..4], target is record 5 (pass) -> y=0
    # Sample 1: window [1..5], target is record 6 (fail) -> y=1
    # Sample 2: window [2..6], target is record 7 (pass) -> y=0 (isolated 500 followed by recovery!)
    # Sample 3: window [3..7], target is record 8 (fail) -> y=1
    # Sample 4: window [4..8], target is record 9 (fail) -> y=1
    assert dataset["samples_count"] == 5
    all_y = dataset["train"]["y"] + dataset["val"]["y"] + dataset["test"]["y"]
    assert all_y == [0, 1, 0, 1, 1]

    # Check that sample 1 feature vector has error_rate == 0.0 because records [1..5] are all pass
    all_X = dataset["train"]["X"] + dataset["val"]["X"] + dataset["test"]["X"]
    sample_1_features = all_X[1]
    err_rate_idx = FEATURE_NAMES.index("error_rate")
    assert sample_1_features[err_rate_idx] == 0.0, "Window [1..5] had no errors, no leakage of record 6"

    # Sample 2 feature vector has record 6 in window -> error_rate should be 20.0 (1 out of 5)
    sample_2_features = all_X[2]
    assert sample_2_features[err_rate_idx] == 20.0
    # But target for sample 2 is 0 because record 7 recovered to 200!
    assert all_y[2] == 0


def test_chronological_three_way_split():
    """Verify chronological train/val/test splits are strictly non-overlapping and ordered."""
    records = generate_synthetic_telemetry_stream(total_records=400, seed=42)
    builder = TelemetryDatasetBuilder(window_size=5)
    dataset = builder.build_dataset_from_records(
        records=records,
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
    )

    assert dataset["status"] == "ready"
    assert dataset["samples_count"] == 395  # 400 - 5
    assert dataset["train_count"] == 276
    assert dataset["val_count"] == 59
    assert dataset["test_count"] == 60
    assert dataset["train_count"] + dataset["val_count"] + dataset["test_count"] == dataset["samples_count"]

    train_times = [datetime.fromisoformat(t) for t in dataset["train"]["timestamps"]]
    val_times = [datetime.fromisoformat(t) for t in dataset["val"]["timestamps"]]
    test_times = [datetime.fromisoformat(t) for t in dataset["test"]["timestamps"]]

    # Strictly ordered: max(train) <= min(val) and max(val) <= min(test)
    assert max(train_times) <= min(val_times)
    assert max(val_times) <= min(test_times)


def test_feature_variation_across_all_splits():
    """Verify http_4xx_rate and http_5xx_rate have non-zero variance in train, val, and test splits."""
    records = generate_synthetic_telemetry_stream(total_records=800, seed=42)
    builder = TelemetryDatasetBuilder(window_size=5)
    dataset = builder.build_dataset_from_records(
        records=records,
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
    )

    idx_5xx = FEATURE_NAMES.index("http_5xx_rate")
    idx_4xx = FEATURE_NAMES.index("http_4xx_rate")

    for split_name in ["train", "val", "test"]:
        split_data = dataset[split_name]
        vals_5xx = [row[idx_5xx] for row in split_data["X"]]
        vals_4xx = [row[idx_4xx] for row in split_data["X"]]

        # Non-zero variance: at least two distinct values, and max > 0
        unique_5xx = set(vals_5xx)
        unique_4xx = set(vals_4xx)

        assert len(unique_5xx) > 1, f"{split_name} split must have non-zero variance for http_5xx_rate"
        assert max(vals_5xx) > 0.0, f"{split_name} split must contain non-zero http_5xx_rate"

        assert len(unique_4xx) > 1, f"{split_name} split must have non-zero variance for http_4xx_rate"
        assert max(vals_4xx) > 0.0, f"{split_name} split must contain non-zero http_4xx_rate"


def test_recovery_sequences_reflect_in_features_and_labels():
    """
    Verify that following an isolated HTTP 500 or burst, subsequent healthy HTTP 200
    observations correctly reduce error rates and the model target predicts recovery (y=0).
    """
    builder = TelemetryDatasetBuilder(window_size=5, min_observations=5)
    base_time = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)

    # 1 burst of 3 500s followed by 6 healthy 200s
    observations = []
    for i in range(3):
        observations.append({
            "latency_ms": 1200.0,
            "passed": False,
            "outcome": "failure",
            "status_code": 500,
            "tested_at": base_time.replace(minute=i),
        })
    for i in range(3, 9):
        observations.append({
            "latency_ms": 120.0,
            "passed": True,
            "outcome": "success",
            "status_code": 200,
            "tested_at": base_time.replace(minute=i),
        })

    dataset = builder.build_dataset_from_records(
        observations, train_ratio=0.5, val_ratio=0.25, test_ratio=0.25
    )

    all_X = dataset["train"]["X"] + dataset["val"]["X"] + dataset["test"]["X"]
    all_y = dataset["train"]["y"] + dataset["val"]["y"] + dataset["test"]["y"]
    idx_5xx = FEATURE_NAMES.index("http_5xx_rate")

    # The 5xx rate across consecutive sliding windows should strictly decrease as recovery progresses
    rates = [row[idx_5xx] for row in all_X]
    assert rates[0] > rates[-1], "5xx rate must decrease across recovery windows"
    # The last target y should be 0 because subsequent observation is healthy
    assert all_y[-1] == 0


def test_experimental_dataset_artifact_generation(tmp_path):
    """
    Verify generate_experimental_dataset produces valid JSON artifact at custom path
    without touching the production telemetry dataset.
    """
    out_file = tmp_path / "custom_experimental_telemetry.json"
    prod_path = Path("data/telemetry_dataset.json")

    prod_mtime_before = prod_path.stat().st_mtime if prod_path.exists() else None

    dataset = generate_experimental_dataset(
        total_records=300,
        seed=42,
        output_path=str(out_file),
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
    )

    assert out_file.exists()
    assert dataset["metadata"]["dataset_type"] == "experimental_synthetic"
    assert dataset["metadata"]["seed"] == 42
    assert "test" in dataset

    # Validate JSON structure
    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["status"] == "ready"
    assert len(data["test"]["X"]) == data["test_count"]
    assert len(data["val"]["X"]) == data["val_count"]
    assert len(data["train"]["X"]) == data["train_count"]

    # Verify production dataset was not modified
    if prod_path.exists() and prod_mtime_before is not None:
        assert prod_path.stat().st_mtime == prod_mtime_before, "Production dataset must remain untouched"


def test_purge_gap_eliminates_boundary_overlap():
    """
    Verify that specifying a purge_gap (embargo) discards boundary samples and
    guarantees that no raw observations from the preceding split enter the subsequent split.
    """
    records = generate_synthetic_telemetry_stream(total_records=400, seed=42)
    builder = TelemetryDatasetBuilder(window_size=5)

    gap = 5
    dataset = builder.build_dataset_from_records(
        records=records,
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
        purge_gap=gap,
    )

    assert dataset["status"] == "ready"
    assert dataset["purge_gap"] == 5
    assert dataset["purged_count"] == 10  # 5 purged at train/val, 5 at val/test
    assert dataset["samples_count"] == 385  # 395 unpurged - 10 purged
    assert dataset["train_count"] == 276
    assert dataset["val_count"] == 54   # 59 - 5
    assert dataset["test_count"] == 55  # 60 - 5
    assert dataset["train_count"] + dataset["val_count"] + dataset["test_count"] == dataset["samples_count"]

    train_end_time = datetime.fromisoformat(dataset["train"]["timestamps"][-1])
    val_start_time = datetime.fromisoformat(dataset["val"]["timestamps"][0])
    val_end_time = datetime.fromisoformat(dataset["val"]["timestamps"][-1])
    test_start_time = datetime.fromisoformat(dataset["test"]["timestamps"][0])

    # With 1-minute steps and purge_gap=5:
    # Gap between last train target and first val target is (gap + 1) * 1 min = 6 min
    assert (val_start_time - train_end_time).total_seconds() >= (gap + 1) * 60
    assert (test_start_time - val_end_time).total_seconds() >= (gap + 1) * 60
