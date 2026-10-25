import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
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


class TestResultRecord(Base):
    __tablename__ = "test_results"
    __test__ = False

    __table_args__ = (
        Index("ix_test_results_api_tested_at", "api_id", "tested_at"),
        Index("ix_test_results_user_tested_at", "user_id", "tested_at"),
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
    passed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    outcome: Mapped[str] = mapped_column(
        String(20),
        nullable=False,  # "success" | "failure" | "timeout" | "error"
    )
    status_code: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    expected_status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    latency_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    headers: Mapped[List[dict]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    body: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )
    validations: Mapped[List[dict]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    error: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    tested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        default=utcnow,
        nullable=False,
    )
    simulated: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="test_results")
    api_endpoint = relationship("ApiEndpoint", back_populates="test_results")
