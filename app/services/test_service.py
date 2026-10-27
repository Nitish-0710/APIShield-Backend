import base64
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.metrics import API_TESTS_TOTAL, API_TEST_DURATION_SECONDS, API_TIMEOUTS_TOTAL
from app.core.security import decrypt_credential
from app.core.ssrf import SSRFProtectionError, execute_safe_request
from app.models.api import ApiEndpoint
from app.models.test_result import TestResultRecord
from app.models.user import User
from app.schemas.api import KeyValueSchema
from app.schemas.testing import (
    TestRequestSchema,
    TestResultResponse,
    ValidationResultSchema,
)


def mask_sensitive_headers(headers: Dict[str, str]) -> List[KeyValueSchema]:
    """Convert header dict to KeyValue list while masking sensitive credentials."""
    result: List[KeyValueSchema] = []
    sensitive_keys = {"authorization", "x-api-key", "api-key", "cookie", "set-cookie", "token"}
    for k, v in headers.items():
        if k.lower() in sensitive_keys:
            result.append(KeyValueSchema(key=k, value="********"))
        else:
            result.append(KeyValueSchema(key=k, value=v))
    return result


def evaluate_validations(
    expected_status: int,
    actual_status: Optional[int],
    validation_rule: Optional[str],
    response_body: str,
) -> Tuple[bool, List[ValidationResultSchema]]:
    """Evaluate HTTP status code and optional validation rules against response."""
    validations: List[ValidationResultSchema] = []

    # 1. Expected status code validation
    status_passed = actual_status is not None and actual_status == expected_status
    status_detail = (
        f"Expected status {expected_status}, received {actual_status}."
        if actual_status is not None
        else f"Expected status {expected_status}, no HTTP response received."
    )
    validations.append(
        ValidationResultSchema(
            rule="Status Code Check",
            passed=status_passed,
            detail=status_detail,
        )
    )

    all_passed = status_passed

    # 2. Custom validation rule (e.g. contains substring, status check, or regex)
    if validation_rule and validation_rule.strip():
        rule_str = validation_rule.strip()
        rule_passed = False
        detail = ""

        # Check if rule is of format 'contains "..."' or 'body.contains("...")'
        contains_match = re.search(r'contains\s*\(?["\']([^"\']+)["\']\)?', rule_str, re.IGNORECASE)
        if contains_match:
            target_substring = contains_match.group(1)
            rule_passed = target_substring in response_body
            detail = (
                f"Body contains expected substring '{target_substring}'"
                if rule_passed
                else f"Body does not contain required substring '{target_substring}'"
            )
        elif rule_str.startswith("regex:"):
            pattern = rule_str[6:].strip()
            try:
                rule_passed = bool(re.search(pattern, response_body))
                detail = f"Body matched regex pattern '{pattern}'" if rule_passed else f"Body failed to match regex '{pattern}'"
            except re.error as e:
                rule_passed = False
                detail = f"Invalid regex pattern: {e}"
        else:
            # Fallback simple substring check
            rule_passed = rule_str in response_body
            detail = (
                f"Body contains phrase '{rule_str}'"
                if rule_passed
                else f"Body does not contain phrase '{rule_str}'"
            )

        validations.append(
            ValidationResultSchema(
                rule=f"Validation Rule ({rule_str[:50]})",
                passed=rule_passed,
                detail=detail,
            )
        )
        if not rule_passed:
            all_passed = False

    return all_passed, validations


class TestService:
    @staticmethod
    def run_saved_api_test(
        db: Session,
        user: Optional[User] = None,
        api_id: str = "",
        is_automated: bool = False,
    ) -> Optional[TestResultResponse]:
        """Execute test for a saved API, enforce SSRF, and persist history.

        If user is provided, validates ownership.
        If is_automated is True, omits body and headers from persistent storage to minimize overhead and data leakage.
        """
        if user is not None:
            stmt = select(ApiEndpoint).where(
                ApiEndpoint.id == api_id,
                ApiEndpoint.user_id == user.id,
            )
        else:
            stmt = select(ApiEndpoint).where(ApiEndpoint.id == api_id)

        api = db.scalar(stmt)
        if not api:
            return None

        target_user_id = user.id if user is not None else api.user_id

        # Build request headers
        req_headers: Dict[str, str] = {}
        for h in api.headers or []:
            if isinstance(h, dict) and h.get("key"):
                req_headers[h["key"]] = h.get("value", "")

        # Inject credentials based on authType if configured
        if api.encrypted_secret and api.auth_type != "none":
            secret = decrypt_credential(api.encrypted_secret)
            if api.auth_type == "bearer":
                req_headers["Authorization"] = f"Bearer {secret}"
            elif api.auth_type == "api_key":
                req_headers["X-API-Key"] = secret
            elif api.auth_type == "basic":
                encoded = base64.b64encode(secret.encode("utf-8")).decode("utf-8")
                req_headers["Authorization"] = f"Basic {encoded}"

        # Build query parameters
        req_params: Dict[str, str] = {}
        for q in api.query_params or []:
            if isinstance(q, dict) and q.get("key"):
                req_params[q["key"]] = q.get("value", "")

        tested_at_dt = datetime.now(timezone.utc)
        outcome: str
        status_code: Optional[int] = None
        resp_headers: Dict[str, str] = {}
        resp_body: str = ""
        latency_ms: Optional[float] = None
        error_msg: Optional[str] = None
        passed = False
        validations: List[ValidationResultSchema] = []

        try:
            status_code, resp_headers, resp_body, latency_ms = execute_safe_request(
                url=api.url,
                method=api.method,
                headers=req_headers,
                params=req_params,
                body=api.body,
                timeout_ms=api.timeout_ms,
            )
            passed, validations = evaluate_validations(
                expected_status=api.expected_status,
                actual_status=status_code,
                validation_rule=api.validation_rule,
                response_body=resp_body,
            )
            outcome = "success" if passed else "failure"

        except TimeoutError as te:
            outcome = "timeout"
            error_msg = str(te)
            passed, validations = evaluate_validations(
                expected_status=api.expected_status,
                actual_status=None,
                validation_rule=api.validation_rule,
                response_body="",
            )
        except SSRFProtectionError as se:
            outcome = "error"
            error_msg = f"SSRF Security Violation: {se}"
            passed = False
            validations = [
                ValidationResultSchema(
                    rule="SSRF Pre-Flight Check",
                    passed=False,
                    detail=error_msg,
                )
            ]
        except Exception as exc:
            outcome = "error"
            error_msg = f"Network Error: {exc}"
            passed = False
            validations = [
                ValidationResultSchema(
                    rule="Connection",
                    passed=False,
                    detail=error_msg,
                )
            ]

        try:
            API_TESTS_TOTAL.labels(outcome=outcome).inc()
            if latency_ms is not None:
                API_TEST_DURATION_SECONDS.observe(latency_ms / 1000.0)
            if outcome == "timeout":
                API_TIMEOUTS_TOTAL.inc()
        except Exception:
            pass

        # Update API telemetry & health status
        api.last_status_code = status_code
        api.last_latency_ms = latency_ms
        api.last_checked_at = tested_at_dt
        if outcome == "success":
            api.health = "healthy"
        elif outcome == "failure":
            api.health = "degraded"
        else:
            api.health = "failing"

        # Sanitize headers for persistent storage
        masked_headers = mask_sensitive_headers(resp_headers)

        # For automated background monitoring, avoid storing body or headers to prevent bloat and sensitive data leakage
        stored_headers = [] if is_automated else [h.model_dump() for h in masked_headers]
        stored_body = "" if is_automated else resp_body

        # Persist test result record
        record = TestResultRecord(
            api_id=api.id,
            user_id=target_user_id,
            passed=passed,
            outcome=outcome,
            status_code=status_code,
            expected_status=api.expected_status,
            latency_ms=latency_ms,
            headers=stored_headers,
            body=stored_body,
            validations=[v.model_dump() for v in validations],
            error=error_msg,
            tested_at=tested_at_dt,
            simulated=False,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        # For automated background monitoring probes, evaluate failure conditions and threshold breaches
        if is_automated:
            try:
                TestService._evaluate_and_create_alert(
                    db=db,
                    api=api,
                    user_id=target_user_id,
                    passed=passed,
                    outcome=outcome,
                    status_code=status_code,
                    latency_ms=latency_ms,
                    error_msg=error_msg,
                )
            except Exception as alert_exc:
                from app.core.logging import logger
                logger.warning(f"Failed to process automated monitoring alert for API {api.id}: {alert_exc}")

        return TestResultResponse(
            id=record.id,
            api_id=api.id,
            passed=passed,
            outcome=outcome,  # type: ignore[arg-type]
            status_code=status_code,
            expected_status=api.expected_status,
            latency_ms=latency_ms,
            headers=masked_headers,
            body=resp_body,
            validations=validations,
            error=error_msg,
            tested_at=tested_at_dt.isoformat(),
            simulated=False,
        )

    @staticmethod
    def run_adhoc_test(
        db: Session,
        user: User,
        data: TestRequestSchema,
    ) -> TestResultResponse:
        """Execute ad-hoc test without a saved API record, enforce SSRF, and persist history."""
        req_headers: Dict[str, str] = {}
        for h in data.headers or []:
            if h.key:
                req_headers[h.key] = h.value

        if data.secret and data.auth_type != "none":
            if data.auth_type == "bearer":
                req_headers["Authorization"] = f"Bearer {data.secret}"
            elif data.auth_type == "api_key":
                req_headers["X-API-Key"] = data.secret
            elif data.auth_type == "basic":
                encoded = base64.b64encode(data.secret.encode("utf-8")).decode("utf-8")
                req_headers["Authorization"] = f"Basic {encoded}"

        req_params: Dict[str, str] = {}
        for q in data.query_params or []:
            if q.key:
                req_params[q.key] = q.value

        tested_at_dt = datetime.now(timezone.utc)
        outcome: str
        status_code: Optional[int] = None
        resp_headers: Dict[str, str] = {}
        resp_body: str = ""
        latency_ms: Optional[float] = None
        error_msg: Optional[str] = None
        passed = False
        validations: List[ValidationResultSchema] = []

        try:
            status_code, resp_headers, resp_body, latency_ms = execute_safe_request(
                url=data.url,
                method=data.method,
                headers=req_headers,
                params=req_params,
                body=data.body,
                timeout_ms=data.timeout_ms,
            )
            passed, validations = evaluate_validations(
                expected_status=data.expected_status,
                actual_status=status_code,
                validation_rule=data.validation_rule,
                response_body=resp_body,
            )
            outcome = "success" if passed else "failure"

        except TimeoutError as te:
            outcome = "timeout"
            error_msg = str(te)
            passed, validations = evaluate_validations(
                expected_status=data.expected_status,
                actual_status=None,
                validation_rule=data.validation_rule,
                response_body="",
            )
        except SSRFProtectionError as se:
            outcome = "error"
            error_msg = f"SSRF Security Violation: {se}"
            passed = False
            validations = [
                ValidationResultSchema(
                    rule="SSRF Pre-Flight Check",
                    passed=False,
                    detail=error_msg,
                )
            ]
        except Exception as exc:
            outcome = "error"
            error_msg = f"Network Error: {exc}"
            passed = False
            validations = [
                ValidationResultSchema(
                    rule="Connection",
                    passed=False,
                    detail=error_msg,
                )
            ]

        try:
            API_TESTS_TOTAL.labels(outcome=outcome).inc()
            if latency_ms is not None:
                API_TEST_DURATION_SECONDS.observe(latency_ms / 1000.0)
            if outcome == "timeout":
                API_TIMEOUTS_TOTAL.inc()
        except Exception:
            pass

        masked_headers = mask_sensitive_headers(resp_headers)

        record = TestResultRecord(
            api_id=None,
            user_id=user.id,
            passed=passed,
            outcome=outcome,
            status_code=status_code,
            expected_status=data.expected_status,
            latency_ms=latency_ms,
            headers=[h.model_dump() for h in masked_headers],
            body=resp_body,
            validations=[v.model_dump() for v in validations],
            error=error_msg,
            tested_at=tested_at_dt,
            simulated=False,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        return TestResultResponse(
            id=record.id,
            api_id=None,
            passed=passed,
            outcome=outcome,  # type: ignore[arg-type]
            status_code=status_code,
            expected_status=data.expected_status,
            latency_ms=latency_ms,
            headers=masked_headers,
            body=resp_body,
            validations=validations,
            error=error_msg,
            tested_at=tested_at_dt.isoformat(),
            simulated=False,
        )

    @staticmethod
    def get_test_history(
        db: Session,
        user: User,
        api_id: str,
        limit: int = 50,
    ) -> Optional[List[TestResultResponse]]:
        """Retrieve historical test results for an API owned by the user."""
        # Ensure API exists and is owned by the user
        stmt = select(ApiEndpoint).where(
            ApiEndpoint.id == api_id,
            ApiEndpoint.user_id == user.id,
        )
        api = db.scalar(stmt)
        if not api:
            return None

        records_stmt = (
            select(TestResultRecord)
            .where(
                TestResultRecord.api_id == api_id,
                TestResultRecord.user_id == user.id,
            )
            .order_by(TestResultRecord.tested_at.desc())
            .limit(limit)
        )
        records = db.scalars(records_stmt).all()

        return [
            TestResultResponse(
                id=r.id,
                api_id=r.api_id,
                passed=r.passed,
                outcome=r.outcome,  # type: ignore[arg-type]
                status_code=r.status_code,
                expected_status=r.expected_status,
                latency_ms=r.latency_ms,
                headers=[
                    KeyValueSchema(key=h.get("key", ""), value=h.get("value", ""))
                    for h in (r.headers or [])
                    if isinstance(h, dict)
                ],
                body=r.body or "",
                validations=[
                    ValidationResultSchema(
                        rule=v.get("rule", ""),
                        passed=v.get("passed", False),
                        detail=v.get("detail", ""),
                    )
                    for v in (r.validations or [])
                    if isinstance(v, dict)
                ],
                error=r.error,
                tested_at=r.tested_at.isoformat(),
                simulated=r.simulated,
            )
            for r in records
        ]

    @staticmethod
    def _evaluate_and_create_alert(
        db: Session,
        api: ApiEndpoint,
        user_id: str,
        passed: bool,
        outcome: str,
        status_code: Optional[int],
        latency_ms: Optional[float],
        error_msg: Optional[str],
    ) -> None:
        """Evaluate automated monitoring probe outcomes and create alerts with deduplication."""
        from app.models.ml import SettingRecord
        from app.services.alert_service import AlertService

        # 1. Determine user-configured cooldown (defaults to 15 min if not configured)
        cooldown_minutes = 15
        user_setting = db.query(SettingRecord).filter(SettingRecord.user_id == user_id).first()
        if user_setting and user_setting.settings:
            cooldown_minutes = user_setting.settings.get("alert_cooldown_minutes", 15)

        alert_service = AlertService()

        # 2. Check for probe failure conditions
        if not passed:
            if outcome == "timeout":
                alert_service.create_alert_if_due(
                    db=db,
                    user_id=user_id,
                    api_id=api.id,
                    title=f"Endpoint Timeout: {api.name}",
                    description=error_msg or f"Automated probe timed out after {api.timeout_ms}ms",
                    severity="critical",
                    source="monitoring",
                    condition_key="probe_timeout",
                    cooldown_minutes=cooldown_minutes,
                )
            elif outcome == "error":
                alert_service.create_alert_if_due(
                    db=db,
                    user_id=user_id,
                    api_id=api.id,
                    title=f"Connection Failure: {api.name}",
                    description=error_msg or "Automated probe failed with a network or connection error",
                    severity="critical",
                    source="monitoring",
                    condition_key="probe_error",
                    cooldown_minutes=cooldown_minutes,
                )
            else:  # outcome == "failure"
                if status_code is not None and status_code >= 500:
                    alert_service.create_alert_if_due(
                        db=db,
                        user_id=user_id,
                        api_id=api.id,
                        title=f"Server Error (HTTP {status_code}): {api.name}",
                        description=f"Automated probe received HTTP {status_code}, expected {api.expected_status}",
                        severity="critical",
                        source="monitoring",
                        condition_key=f"http_{status_code}",
                        cooldown_minutes=cooldown_minutes,
                    )
                elif status_code is not None and status_code != api.expected_status:
                    alert_service.create_alert_if_due(
                        db=db,
                        user_id=user_id,
                        api_id=api.id,
                        title=f"Unexpected Status (HTTP {status_code}): {api.name}",
                        description=f"Automated probe received HTTP {status_code}, expected {api.expected_status}",
                        severity="warning",
                        source="monitoring",
                        condition_key=f"unexpected_status_{status_code}",
                        cooldown_minutes=cooldown_minutes,
                    )
                else:
                    alert_service.create_alert_if_due(
                        db=db,
                        user_id=user_id,
                        api_id=api.id,
                        title=f"Validation Failure: {api.name}",
                        description=error_msg or "Automated probe failed custom validation rules or assertions",
                        severity="warning",
                        source="monitoring",
                        condition_key="validation_failure",
                        cooldown_minutes=cooldown_minutes,
                    )
        # 3. Check for threshold breach on passed probes (e.g. latency breach)
        elif (
            latency_ms is not None
            and api.max_latency_ms is not None
            and latency_ms > float(api.max_latency_ms)
        ):
            alert_service.create_alert_if_due(
                db=db,
                user_id=user_id,
                api_id=api.id,
                title=f"High Latency Alert: {api.name}",
                description=f"Observed latency of {latency_ms:.1f}ms exceeded configured threshold of {api.max_latency_ms}ms",
                severity="warning",
                source="monitoring",
                condition_key="latency_breached",
                cooldown_minutes=cooldown_minutes,
            )
