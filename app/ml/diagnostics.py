from datetime import UTC, datetime, timezone
from typing import Any, Dict, List, Optional


class DiagnosticEngine:
    """
    Rule-based diagnostic engine that inspects monitoring evidence and telemetry.
    Differentiates between verified facts, rule inferences, and ML associations.
    """

    def analyze(
        self,
        api_id: str,
        api_name: str,
        features: dict[str, float],
        latency_threshold_ms: float = 1000.0,
        availability_target: float = 99.0,
        time_window: str = "recent",
    ) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []

        total_obs = int(features.get("total_observations", 0))
        if total_obs == 0:
            return {
                "api_id": api_id,
                "api_name": api_name,
                "time_window": time_window,
                "overall_status": "insufficient_data",
                "summary": "No monitoring observations available for diagnostic analysis.",
                "findings": [],
                "generated_at": datetime.now(UTC).isoformat(),
            }

        avg_lat = features.get("avg_latency_ms", 0.0)
        p95_lat = features.get("p95_latency_ms", 0.0)
        trend = features.get("latency_trend", 1.0)
        err_rate = features.get("error_rate", 0.0)
        timeout_rate = features.get("timeout_rate", 0.0)
        http_4xx = features.get("http_4xx_rate", 0.0)
        http_5xx = features.get("http_5xx_rate", 0.0)
        avail = features.get("availability", 100.0)
        consec_fail = int(features.get("recent_consecutive_failures", 0))

        # 1. Server-side failures (HTTP 5xx)
        if http_5xx > 0:
            severity = "critical" if http_5xx >= 10.0 else "warning"
            findings.append({
                "category": "5xx_server_errors",
                "severity": severity,
                "certainty": "confirmed_fact",
                "title": f"Upstream Server Errors ({http_5xx}% 5xx responses)",
                "evidence": {
                    "http_5xx_rate": http_5xx,
                    "total_observations": total_obs,
                },
                "recommendation": (
                    "Inspect backend service error logs, uncaught exceptions, and upstream database/dependency connections."
                ),
            })

        # 2. Repeated Timeouts / Connection drops
        if timeout_rate > 0:
            severity = "critical" if timeout_rate >= 10.0 else "warning"
            findings.append({
                "category": "network_timeout",
                "severity": severity,
                "certainty": "confirmed_fact",
                "title": f"Network or Gateway Timeouts ({timeout_rate}% timed out)",
                "evidence": {
                    "timeout_rate": timeout_rate,
                    "avg_latency_ms": avg_lat,
                },
                "recommendation": (
                    "Verify target service host availability, firewall/NAT rules, proxy timeout thresholds, or slow downstream dependencies."
                ),
            })

        # 3. Elevated Latency & Degradation Trend
        if avg_lat > latency_threshold_ms or p95_lat > latency_threshold_ms * 1.5 or trend > 1.5:
            severity = "warning" if avg_lat < latency_threshold_ms * 2 else "critical"
            findings.append({
                "category": "latency_degradation",
                "severity": severity,
                "certainty": "rule_inference",
                "title": f"Elevated Latency (p95: {p95_lat}ms, Trend: {trend}x baseline)",
                "evidence": {
                    "avg_latency_ms": avg_lat,
                    "p95_latency_ms": p95_lat,
                    "latency_trend": trend,
                    "configured_threshold_ms": latency_threshold_ms,
                },
                "recommendation": (
                    "Profile server CPU/memory usage, query execution times, or connection pool saturation during peak probe intervals."
                ),
            })

        # 4. Client Request Errors (HTTP 4xx)
        if http_4xx >= 10.0:
            findings.append({
                "category": "4xx_client_errors",
                "severity": "warning",
                "certainty": "confirmed_fact",
                "title": f"High Client-Side Error Rate ({http_4xx}% 4xx responses)",
                "evidence": {
                    "http_4xx_rate": http_4xx,
                },
                "recommendation": (
                    "Verify API authentication credentials, payload schemas, query parameters, or rate limit headers."
                ),
            })

        # 5. Availability target breached
        if avail < availability_target:
            findings.append({
                "category": "availability_breach",
                "severity": "critical" if avail < 90.0 else "warning",
                "certainty": "confirmed_fact",
                "title": f"SLA Availability Below Target ({avail}% vs target {availability_target}%)",
                "evidence": {
                    "measured_availability": avail,
                    "target_availability": availability_target,
                    "recent_consecutive_failures": consec_fail,
                },
                "recommendation": (
                    "Initiate automated failover, scale target replicas, or activate maintenance routing."
                ),
            })

        # 6. Consecutive probe failures (Immediate outage risk)
        if consec_fail >= 2:
            findings.append({
                "category": "consecutive_failures",
                "severity": "critical",
                "certainty": "confirmed_fact",
                "title": f"{consec_fail} Consecutive Test Failures",
                "evidence": {
                    "consecutive_failures": consec_fail,
                },
                "recommendation": (
                    "Target endpoint appears unresponsive or rejecting probes. Immediate on-call verification required."
                ),
            })

        # Determine overall health status
        has_critical = any(f["severity"] == "critical" for f in findings)
        has_warning = any(f["severity"] == "warning" for f in findings)

        if has_critical:
            overall_status = "critical"
            summary = f"Critical issues detected: {len(findings)} findings require urgent attention."
        elif has_warning:
            overall_status = "degraded"
            summary = f"Degraded performance: {len(findings)} warning findings observed."
        else:
            overall_status = "healthy"
            summary = "All observed monitoring metrics are operating within normal parameters."

        return {
            "api_id": api_id,
            "api_name": api_name,
            "time_window": time_window,
            "overall_status": overall_status,
            "summary": summary,
            "findings": findings,
            "generated_at": datetime.now(UTC).isoformat(),
        }
