import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PredictionRecord(Base):
    __tablename__ = "prediction_records"

    __table_args__ = (
        Index("ix_prediction_records_api_created_at", "api_id", "created_at"),
        Index("ix_prediction_records_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    api_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("api_endpoints.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    risk_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,  # 0.0 - 100.0
    )
    risk_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,  # "low" | "medium" | "high" | "critical"
    )
    prediction: Mapped[int] = mapped_column(
        Integer,
        nullable=False,  # 0: healthy / 1: failure risk
    )
    provenance: Mapped[str] = mapped_column(
        String(30),
        nullable=False,  # "trained_model" | "rules_baseline" | "demo"
    )
    model_version: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    features: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    explanation: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    inference_duration_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        index=True,
        nullable=False,
    )

    # Relationships
    api_endpoint = relationship("ApiEndpoint", back_populates="predictions")
    user = relationship("User", back_populates="predictions")


class AlertRecord(Base):
    __tablename__ = "alert_records"

    __table_args__ = (
        Index("ix_alert_records_api_status", "api_id", "status"),
        Index("ix_alert_records_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    api_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("api_endpoints.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        default="warning",
        nullable=False,  # "info" | "warning" | "critical"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="open",
        nullable=False,  # "open" | "acknowledged" | "resolved"
    )
    source: Mapped[str] = mapped_column(
        String(30),
        default="monitoring",
        nullable=False,  # "monitoring" | "prediction" | "system"
    )
    fingerprint: Mapped[str] = mapped_column(
        String(128),
        index=True,
        nullable=False,  # Hash of (api_id, condition) for deduplication / cooldown
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        index=True,
        nullable=False,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    api_endpoint = relationship("ApiEndpoint", back_populates="alerts")
    user = relationship("User", back_populates="alerts")


class SettingRecord(Base):
    __tablename__ = "user_settings"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    settings: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="app_settings")
