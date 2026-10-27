import json
import os
import random
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.ml.features import FEATURE_NAMES, extract_features_from_observations, feature_vector


class TelemetryDatasetBuilder:
    """
    Transforms raw persisted monitoring observations into a reproducible,
    leakage-free, time-aware training and evaluation dataset.
    """

    def __init__(self, window_size: int = 5, min_observations: int = 15):
        self.window_size = window_size
        self.min_observations = min_observations

    def build_dataset_from_records(
        self,
        records: list[dict[str, Any]],
        train_ratio: float = 0.8,
        val_ratio: Optional[float] = None,
        test_ratio: Optional[float] = None,
        purge_gap: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        Builds feature matrix X and target vector y using a chronological sliding window.

        Target Definition:
        y = 1 if the next observation (t+1) failed (passed=False or status_code >= 400 or timeout),
        y = 0 if the next observation succeeded.

        Time-aware split:
        Chronological split without shuffling to prevent temporal data leakage.
        Supports 2-way (train/val) or 3-way (train/val/test) non-overlapping chronological splits.
        Supports optional purge_gap to embargo boundary samples and eliminate sliding-window
        feature overlap or target contamination across splits.
        """
        # Sort chronologically
        sorted_records = sorted(
            records,
            key=lambda r: r.get("tested_at") or datetime.min.replace(tzinfo=UTC),
        )

        total_obs = len(sorted_records)
        if total_obs < self.min_observations:
            return {
                "status": "insufficient_data",
                "message": f"Insufficient observations ({total_obs} found, minimum {self.min_observations} required).",
                "total_observations": total_obs,
                "feature_names": FEATURE_NAMES,
                "samples_count": 0,
            }

        samples: list[dict[str, Any]] = []

        # Sliding window over historical observations
        for i in range(self.window_size, total_obs):
            history_window = sorted_records[i - self.window_size : i]
            target_record = sorted_records[i]

            ref_time = target_record.get("tested_at")
            if isinstance(ref_time, str):
                try:
                    ref_time = datetime.fromisoformat(ref_time.replace("Z", "+00:00"))
                except Exception:
                    ref_time = datetime.now(UTC)

            # Feature extraction using strictly past observations
            features = extract_features_from_observations(history_window, reference_time=ref_time)

            # Target definition: did target_record fail?
            passed = bool(target_record.get("passed", True))
            status_code = target_record.get("status_code")
            outcome = str(target_record.get("outcome", "success")).lower()

            is_failure = (
                not passed
                or outcome in ("failure", "error", "timeout")
                or (status_code is not None and int(status_code) >= 400)
            )
            target = 1 if is_failure else 0

            samples.append({
                "features": features,
                "feature_vector": feature_vector(features),
                "target": target,
                "timestamp": ref_time.isoformat() if ref_time else None,
            })

        if not samples:
            return {
                "status": "insufficient_data",
                "message": "No valid sliding window samples could be constructed.",
                "total_observations": total_obs,
                "feature_names": FEATURE_NAMES,
                "samples_count": 0,
            }

        # Chronological split with optional purge gap (embargo)
        test_samples: list[dict[str, Any]] = []
        effective_gap = purge_gap if (purge_gap is not None and purge_gap > 0) else 0

        if test_ratio is not None and test_ratio > 0.0:
            effective_val = val_ratio if val_ratio is not None else round(1.0 - train_ratio - test_ratio, 4)
            train_end = int(len(samples) * train_ratio)
            val_end = int(len(samples) * (train_ratio + effective_val))

            val_start = min(train_end + effective_gap, val_end)
            test_start = min(val_end + effective_gap, len(samples))

            train_samples = samples[:train_end]
            val_samples = samples[val_start:val_end]
            test_samples = samples[test_start:]
        else:
            split_idx = int(len(samples) * train_ratio)
            val_start = min(split_idx + effective_gap, len(samples))
            train_samples = samples[:split_idx]
            val_samples = samples[val_start:] if val_start < len(samples) else samples

        # Class counts across retained samples
        retained_samples = train_samples + val_samples + test_samples
        purged_count = len(samples) - len(retained_samples)
        pos_count = sum(s["target"] for s in retained_samples)
        neg_count = len(retained_samples) - pos_count

        result: dict[str, Any] = {
            "status": "ready",
            "feature_names": FEATURE_NAMES,
            "total_observations": total_obs,
            "total_unpurged_samples": len(samples),
            "samples_count": len(retained_samples),
            "purged_count": purged_count,
            "purge_gap": effective_gap,
            "train_count": len(train_samples),
            "val_count": len(val_samples),
            "class_distribution": {
                "negative_healthy": neg_count,
                "positive_failure": pos_count,
                "failure_rate": round(pos_count / max(len(retained_samples), 1), 4),
            },
            "train": {
                "X": [s["feature_vector"] for s in train_samples],
                "y": [s["target"] for s in train_samples],
                "timestamps": [s["timestamp"] for s in train_samples],
            },
            "val": {
                "X": [s["feature_vector"] for s in val_samples],
                "y": [s["target"] for s in val_samples],
                "timestamps": [s["timestamp"] for s in val_samples],
            },
            "metadata": {
                "window_size": self.window_size,
                "purge_gap": effective_gap,
                "purged_samples": purged_count,
                "created_at": datetime.now(UTC).isoformat(),
                "leakage_prevention": "strictly_prior_time_window_with_purge_gap" if effective_gap > 0 else "strictly_prior_time_window",
            },
        }

        if test_samples:
            result["test_count"] = len(test_samples)
            result["test"] = {
                "X": [s["feature_vector"] for s in test_samples],
                "y": [s["target"] for s in test_samples],
                "timestamps": [s["timestamp"] for s in test_samples],
            }

        return result

    def save_dataset_artifact(
        self,
        dataset_dict: dict[str, Any],
        output_path: str,
    ) -> str:
        """Saves dataset artifact to JSON file for DVC tracking and pipeline reproducibility."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dataset_dict, f, indent=2)
        return str(path)


def generate_synthetic_telemetry_stream(
    total_records: int = 800,
    seed: int = 42,
    base_time: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """
    Generates a deterministic synthetic stream of realistic API probe observations.

    Sequence patterns modeled:
    1. Healthy baseline: Repeated HTTP 200 with normal latency.
    2. Isolated HTTP 500: Single server error followed by immediate recovery.
    3. Persistent 5xx bursts: Consecutive HTTP 500/502/503 server errors.
    4. Client errors: HTTP 429 rate limiting and HTTP 404 not found.
    5. Repeated timeouts: Unresponsive downstream services followed by recovery.
    6. Cascading failures: Latency spike -> 503 -> timeout -> 500 -> recovery.
    """
    rng = random.Random(seed)
    if base_time is None:
        base_time = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)

    records: list[dict[str, Any]] = []
    current_time = base_time

    episodes = ["isolated_500", "persistent_5xx", "client_errors", "timeouts", "mixed_cascade"]
    ep_idx = 0

    while len(records) < total_records:
        # 1. Healthy interlude between incidents
        h_len = rng.randint(6, 14)
        for _ in range(h_len):
            if len(records) >= total_records:
                break
            lat = max(round(rng.gauss(140.0, 25.0), 2), 40.0)
            records.append({
                "latency_ms": lat,
                "passed": True,
                "outcome": "success",
                "status_code": 200,
                "tested_at": current_time,
            })
            current_time += timedelta(minutes=1)

        if len(records) >= total_records:
            break

        # 2. Specific failure incident
        episode = episodes[ep_idx % len(episodes)]
        ep_idx += 1

        if episode == "isolated_500":
            # 1 failure with HTTP 500, followed by recovery
            records.append({
                "latency_ms": round(rng.gauss(950.0, 120.0), 2),
                "passed": False,
                "outcome": "failure",
                "status_code": 500,
                "tested_at": current_time,
            })
            current_time += timedelta(minutes=1)
            recovery_len = rng.randint(3, 6)
            for _ in range(recovery_len):
                if len(records) >= total_records:
                    break
                records.append({
                    "latency_ms": round(rng.gauss(145.0, 20.0), 2),
                    "passed": True,
                    "outcome": "success",
                    "status_code": 200,
                    "tested_at": current_time,
                })
                current_time += timedelta(minutes=1)

        elif episode == "persistent_5xx":
            burst_len = rng.randint(3, 6)
            for _ in range(burst_len):
                if len(records) >= total_records:
                    break
                sc = rng.choice([500, 502, 503])
                records.append({
                    "latency_ms": round(rng.gauss(1600.0, 250.0), 2),
                    "passed": False,
                    "outcome": "failure",
                    "status_code": sc,
                    "tested_at": current_time,
                })
                current_time += timedelta(minutes=1)
            # Recovery
            for _ in range(3):
                if len(records) >= total_records:
                    break
                records.append({
                    "latency_ms": round(rng.gauss(155.0, 20.0), 2),
                    "passed": True,
                    "outcome": "success",
                    "status_code": 200,
                    "tested_at": current_time,
                })
                current_time += timedelta(minutes=1)

        elif episode == "client_errors":
            burst_len = rng.randint(2, 4)
            for _ in range(burst_len):
                if len(records) >= total_records:
                    break
                sc = rng.choice([429, 404])
                records.append({
                    "latency_ms": round(rng.gauss(120.0, 20.0), 2),
                    "passed": False,
                    "outcome": "failure",
                    "status_code": sc,
                    "tested_at": current_time,
                })
                current_time += timedelta(minutes=1)
            # Recovery
            for _ in range(2):
                if len(records) >= total_records:
                    break
                records.append({
                    "latency_ms": round(rng.gauss(140.0, 15.0), 2),
                    "passed": True,
                    "outcome": "success",
                    "status_code": 200,
                    "tested_at": current_time,
                })
                current_time += timedelta(minutes=1)

        elif episode == "timeouts":
            burst_len = rng.randint(2, 4)
            for _ in range(burst_len):
                if len(records) >= total_records:
                    break
                records.append({
                    "latency_ms": 10000.0,
                    "passed": False,
                    "outcome": "timeout",
                    "status_code": None,
                    "tested_at": current_time,
                })
                current_time += timedelta(minutes=1)
            # Recovery
            for _ in range(3):
                if len(records) >= total_records:
                    break
                records.append({
                    "latency_ms": round(rng.gauss(180.0, 30.0), 2),
                    "passed": True,
                    "outcome": "success",
                    "status_code": 200,
                    "tested_at": current_time,
                })
                current_time += timedelta(minutes=1)

        elif episode == "mixed_cascade":
            cascade = [
                (450.0, True, "success", 200),
                (1200.0, False, "failure", 503),
                (10000.0, False, "timeout", None),
                (2100.0, False, "failure", 500),
                (350.0, True, "success", 200),
            ]
            for lat, p, out, sc in cascade:
                if len(records) >= total_records:
                    break
                records.append({
                    "latency_ms": lat,
                    "passed": p,
                    "outcome": out,
                    "status_code": sc,
                    "tested_at": current_time,
                })
                current_time += timedelta(minutes=1)

    return records[:total_records]


def generate_experimental_dataset(
    total_records: int = 800,
    seed: int = 42,
    output_path: str = "data/experimental_telemetry_dataset.json",
    window_size: int = 5,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    purge_gap: Optional[int] = 5,
) -> dict[str, Any]:
    """Generates an experimental dataset covering realistic HTTP status sequences and saves to a dedicated path."""
    records = generate_synthetic_telemetry_stream(total_records=total_records, seed=seed)
    builder = TelemetryDatasetBuilder(window_size=window_size)
    dataset = builder.build_dataset_from_records(
        records=records,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        purge_gap=purge_gap,
    )
    dataset["metadata"]["dataset_type"] = "experimental_synthetic"
    dataset["metadata"]["seed"] = seed
    saved_path = builder.save_dataset_artifact(dataset, output_path)
    dataset["artifact_path"] = saved_path
    return dataset
