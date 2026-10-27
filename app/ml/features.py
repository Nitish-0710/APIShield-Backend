import math
from datetime import UTC, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

FEATURE_NAMES = [
    "avg_latency_ms",
    "p95_latency_ms",
    "p50_latency_ms",
    "std_latency_ms",
    "max_latency_ms",
    "latency_trend",
    "error_rate",
    "timeout_rate",
    "http_4xx_rate",
    "http_5xx_rate",
    "availability",
    "recent_consecutive_failures",
    "total_observations",
    "hour_of_day",
    "day_of_week",
]


def extract_features_from_observations(
    observations: list[dict[str, Any]],
    reference_time: datetime | None = None,
) -> dict[str, float]:
    """
    Extract tabular telemetry features from a chronological sequence of test observations.
    All observations MUST be prior to reference_time to prevent target leakage.
    Returns a dictionary of named numeric features.
    """
    if reference_time is None:
        reference_time = datetime.now(UTC)
    elif reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=UTC)

    if not observations:
        # Default neutral baseline features when no observations exist
        return {
            "avg_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "p50_latency_ms": 0.0,
            "std_latency_ms": 0.0,
            "max_latency_ms": 0.0,
            "latency_trend": 1.0,
            "error_rate": 0.0,
            "timeout_rate": 0.0,
            "http_4xx_rate": 0.0,
            "http_5xx_rate": 0.0,
            "availability": 100.0,
            "recent_consecutive_failures": 0.0,
            "total_observations": 0.0,
            "hour_of_day": float(reference_time.hour),
            "day_of_week": float(reference_time.weekday()),
        }

    latencies: list[float] = []
    error_count = 0
    timeout_count = 0
    http_4xx_count = 0
    http_5xx_count = 0
    passed_count = 0

    for obs in observations:
        lat = obs.get("latency_ms")
        if lat is not None and not math.isnan(lat) and lat >= 0:
            latencies.append(float(lat))

        passed = bool(obs.get("passed", False))
        if passed:
            passed_count += 1

        outcome = str(obs.get("outcome", "error")).lower()
        status_code = obs.get("status_code")

        if outcome == "timeout":
            timeout_count += 1
            error_count += 1
        elif outcome in ("failure", "error"):
            error_count += 1

        if status_code is not None:
            try:
                sc = int(status_code)
                if 400 <= sc < 500:
                    http_4xx_count += 1
                elif sc >= 500:
                    http_5xx_count += 1
            except (ValueError, TypeError):
                pass

    n = len(observations)
    if latencies:
        sorted_lat = sorted(latencies)
        avg_lat = sum(sorted_lat) / len(sorted_lat)
        max_lat = max(sorted_lat)

        # Quantiles
        p50_idx = int(0.50 * (len(sorted_lat) - 1))
        p95_idx = int(0.95 * (len(sorted_lat) - 1))
        p50_lat = sorted_lat[p50_idx]
        p95_lat = sorted_lat[p95_idx]

        # Standard deviation
        variance = sum((x - avg_lat) ** 2 for x in sorted_lat) / len(sorted_lat)
        std_lat = math.sqrt(variance)

        # Recent latency trend: last 3 tests vs overall average
        recent_lat = latencies[-3:] if len(latencies) >= 3 else latencies
        recent_avg = sum(recent_lat) / len(recent_lat)
        latency_trend = round(recent_avg / (avg_lat + 1e-4), 3)
    else:
        avg_lat = 0.0
        p95_lat = 0.0
        p50_lat = 0.0
        std_lat = 0.0
        max_lat = 0.0
        latency_trend = 1.0

    # Consecutive failures at the end of the observation window
    consecutive_failures = 0
    for obs in reversed(observations):
        if not obs.get("passed", False):
            consecutive_failures += 1
        else:
            break

    return {
        "avg_latency_ms": round(avg_lat, 2),
        "p95_latency_ms": round(p95_lat, 2),
        "p50_latency_ms": round(p50_lat, 2),
        "std_latency_ms": round(std_lat, 2),
        "max_latency_ms": round(max_lat, 2),
        "latency_trend": float(latency_trend),
        "error_rate": round((error_count / n) * 100.0, 2),
        "timeout_rate": round((timeout_count / n) * 100.0, 2),
        "http_4xx_rate": round((http_4xx_count / n) * 100.0, 2),
        "http_5xx_rate": round((http_5xx_count / n) * 100.0, 2),
        "availability": round((passed_count / n) * 100.0, 2),
        "recent_consecutive_failures": float(consecutive_failures),
        "total_observations": float(n),
        "hour_of_day": float(reference_time.hour),
        "day_of_week": float(reference_time.weekday()),
    }


def feature_vector(features: dict[str, float]) -> list[float]:
    """Convert features dict into ordered list matching FEATURE_NAMES."""
    return [float(features.get(name, 0.0)) for name in FEATURE_NAMES]
