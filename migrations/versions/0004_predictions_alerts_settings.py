"""add prediction_records, alert_records, and user_settings tables

Revision ID: 0004_predictions_alerts_settings
Revises: 0003_monitoring_metrics
Create Date: 2026-10-25 08:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_predictions_alerts_settings"
down_revision: Union[str, None] = "0003_monitoring_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Prediction records
    op.create_table(
        "prediction_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("api_id", sa.String(36), sa.ForeignKey("api_endpoints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("prediction", sa.Integer(), nullable=False),
        sa.Column("provenance", sa.String(30), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("inference_duration_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_prediction_records_api_id"), "prediction_records", ["api_id"], unique=False)
    op.create_index(op.f("ix_prediction_records_user_id"), "prediction_records", ["user_id"], unique=False)
    op.create_index(op.f("ix_prediction_records_created_at"), "prediction_records", ["created_at"], unique=False)
    op.create_index("ix_prediction_records_api_created_at", "prediction_records", ["api_id", "created_at"], unique=False)
    op.create_index("ix_prediction_records_user_created_at", "prediction_records", ["user_id", "created_at"], unique=False)

    # 2. Alert records
    op.create_table(
        "alert_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("api_id", sa.String(36), sa.ForeignKey("api_endpoints.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), server_default="warning", nullable=False),
        sa.Column("status", sa.String(20), server_default="open", nullable=False),
        sa.Column("source", sa.String(30), server_default="monitoring", nullable=False),
        sa.Column("fingerprint", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_alert_records_api_id"), "alert_records", ["api_id"], unique=False)
    op.create_index(op.f("ix_alert_records_user_id"), "alert_records", ["user_id"], unique=False)
    op.create_index(op.f("ix_alert_records_fingerprint"), "alert_records", ["fingerprint"], unique=False)
    op.create_index(op.f("ix_alert_records_created_at"), "alert_records", ["created_at"], unique=False)
    op.create_index("ix_alert_records_api_status", "alert_records", ["api_id", "status"], unique=False)
    op.create_index("ix_alert_records_user_created_at", "alert_records", ["user_id", "created_at"], unique=False)

    # 3. User settings
    op.create_table(
        "user_settings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_user_settings_user_id"), "user_settings", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_table("user_settings")
    op.drop_table("alert_records")
    op.drop_table("prediction_records")
