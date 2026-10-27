import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApiEndpoint(Base):
    __tablename__ = "api_endpoints"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )
    method: Mapped[str] = mapped_column(
        String(10),
        default="GET",
        nullable=False,
    )
    query_params: Mapped[List[dict]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    headers: Mapped[List[dict]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    auth_type: Mapped[str] = mapped_column(
        String(20),
        default="none",
        nullable=False,
    )
    encrypted_secret: Mapped[Optional[str]] = mapped_column(
        String(1024),
        nullable=True,
    )
    body: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    expected_status: Mapped[int] = mapped_column(
        Integer,
        default=200,
        nullable=False,
    )
    validation_rule: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    timeout_ms: Mapped[int] = mapped_column(
        Integer,
        default=10000,
        nullable=False,
    )
    interval_sec: Mapped[int] = mapped_column(
        Integer,
        default=60,
        nullable=False,
    )
    max_latency_ms: Mapped[int] = mapped_column(
        Integer,
        default=1000,
        nullable=False,
    )
    error_rate_threshold: Mapped[float] = mapped_column(
        Float,
        default=5.0,
        nullable=False,
    )
    expected_availability: Mapped[float] = mapped_column(
        Float,
        default=99.0,
        nullable=False,
    )
    risk_threshold: Mapped[float] = mapped_column(
        Float,
        default=70.0,
        nullable=False,
    )
    monitoring: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    health: Mapped[str] = mapped_column(
        String(20),
        default="unknown",
        nullable=False,
    )
    last_status_code: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    last_latency_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    next_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    is_probing: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    risk: Mapped[str] = mapped_column(
        String(20),
        default="unknown",
        nullable=False,
    )
    risk_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="api_endpoints")
    test_results = relationship(
        "TestResultRecord",
        back_populates="api_endpoint",
        cascade="all, delete-orphan",
        order_by="desc(TestResultRecord.tested_at)",
    )
    predictions = relationship(
        "PredictionRecord",
        back_populates="api_endpoint",
        cascade="all, delete-orphan",
        order_by="desc(PredictionRecord.created_at)",
    )
    alerts = relationship(
        "AlertRecord",
        back_populates="api_endpoint",
        cascade="all, delete-orphan",
        order_by="desc(AlertRecord.created_at)",
    )
