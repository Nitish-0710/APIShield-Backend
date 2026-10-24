from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.security import encrypt_credential
from app.models.api import ApiEndpoint
from app.models.user import User
from app.schemas.api import (
    ApiEndpointInput,
    ApiEndpointResponse,
    ApiEndpointUpdate,
    KeyValueSchema,
)


def to_api_response(api: ApiEndpoint) -> ApiEndpointResponse:
    """Transform an ApiEndpoint ORM instance into the contract-compliant response schema."""
    qp = [
        KeyValueSchema(key=item.get("key", ""), value=item.get("value", ""))
        for item in (api.query_params or [])
        if isinstance(item, dict)
    ]
    hdrs = [
        KeyValueSchema(key=item.get("key", ""), value=item.get("value", ""))
        for item in (api.headers or [])
        if isinstance(item, dict)
    ]
    return ApiEndpointResponse(
        id=api.id,
        name=api.name,
        url=api.url,
        method=api.method,
        query_params=qp,
        headers=hdrs,
        auth_type=api.auth_type,
        has_secret=bool(api.encrypted_secret),
        body=api.body,
        expected_status=api.expected_status,
        validation_rule=api.validation_rule,
        timeout_ms=api.timeout_ms,
        interval_sec=api.interval_sec,
        max_latency_ms=api.max_latency_ms,
        error_rate_threshold=api.error_rate_threshold,
        expected_availability=api.expected_availability,
        risk_threshold=api.risk_threshold,
        monitoring=api.monitoring,
        health=api.health,
        last_status_code=api.last_status_code,
        last_latency_ms=api.last_latency_ms,
        last_checked_at=api.last_checked_at.isoformat() if api.last_checked_at else None,
        risk=api.risk,
        risk_score=api.risk_score,
        created_at=api.created_at.isoformat() if api.created_at else "",
    )


class ApiService:
    @staticmethod
    def create_api(db: Session, user: User, data: ApiEndpointInput) -> ApiEndpoint:
        encrypted_secret: Optional[str] = None
        if data.secret:
            encrypted_secret = encrypt_credential(data.secret)

        qp = [q.model_dump() for q in data.query_params]
        hdrs = [h.model_dump() for h in data.headers]

        api = ApiEndpoint(
            user_id=user.id,
            name=data.name,
            url=data.url,
            method=data.method,
            query_params=qp,
            headers=hdrs,
            auth_type=data.auth_type,
            encrypted_secret=encrypted_secret,
            body=data.body,
            expected_status=data.expected_status,
            validation_rule=data.validation_rule,
            timeout_ms=data.timeout_ms,
            interval_sec=data.interval_sec,
            max_latency_ms=data.max_latency_ms,
            error_rate_threshold=data.error_rate_threshold,
            expected_availability=data.expected_availability,
            risk_threshold=data.risk_threshold,
            monitoring=data.monitoring,
            health="unknown",
            risk="unknown",
        )
        db.add(api)
        db.commit()
        db.refresh(api)
        return api

    @staticmethod
    def list_apis(db: Session, user: User) -> List[ApiEndpoint]:
        stmt = (
            select(ApiEndpoint)
            .where(ApiEndpoint.user_id == user.id)
            .order_by(ApiEndpoint.created_at.desc())
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get_api(db: Session, user: User, api_id: str) -> Optional[ApiEndpoint]:
        stmt = select(ApiEndpoint).where(
            ApiEndpoint.id == api_id,
            ApiEndpoint.user_id == user.id,
        )
        return db.scalar(stmt)

    @staticmethod
    def update_api(
        db: Session,
        user: User,
        api_id: str,
        data: ApiEndpointUpdate,
    ) -> Optional[ApiEndpoint]:
        api = ApiService.get_api(db, user, api_id)
        if not api:
            return None

        # Handle secret update semantics
        if data.secret is not None:
            if data.secret == "" or (data.auth_type is not None and data.auth_type == "none"):
                api.encrypted_secret = None
            else:
                api.encrypted_secret = encrypt_credential(data.secret)
        elif data.auth_type == "none":
            api.encrypted_secret = None

        if data.name is not None:
            api.name = data.name
        if data.url is not None:
            api.url = data.url
        if data.method is not None:
            api.method = data.method
        if data.query_params is not None:
            api.query_params = [q.model_dump() for q in data.query_params]
        if data.headers is not None:
            api.headers = [h.model_dump() for h in data.headers]
        if data.auth_type is not None:
            api.auth_type = data.auth_type
        if data.body is not None:
            api.body = data.body
        if data.expected_status is not None:
            api.expected_status = data.expected_status
        if data.validation_rule is not None:
            api.validation_rule = data.validation_rule
        if data.timeout_ms is not None:
            api.timeout_ms = data.timeout_ms
        if data.interval_sec is not None:
            api.interval_sec = data.interval_sec
        if data.max_latency_ms is not None:
            api.max_latency_ms = data.max_latency_ms
        if data.error_rate_threshold is not None:
            api.error_rate_threshold = data.error_rate_threshold
        if data.expected_availability is not None:
            api.expected_availability = data.expected_availability
        if data.risk_threshold is not None:
            api.risk_threshold = data.risk_threshold
        if data.monitoring is not None:
            api.monitoring = data.monitoring

        db.commit()
        db.refresh(api)
        return api

    @staticmethod
    def delete_api(db: Session, user: User, api_id: str) -> bool:
        api = ApiService.get_api(db, user, api_id)
        if not api:
            return False

        db.delete(api)
        db.commit()
        return True
