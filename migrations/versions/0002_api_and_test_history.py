"""create api_endpoints and test_results tables

Revision ID: 0002_api_and_test_history
Revises: 0001_initial_user_and_session
Create Date: 2026-10-25 02:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_api_and_test_history"
down_revision: Union[str, None] = "0001_initial_user_and_session"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_endpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False, server_default="GET"),
        sa.Column("query_params", sa.JSON(), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("auth_type", sa.String(length=20), nullable=False, server_default="none"),
        sa.Column("encrypted_secret", sa.String(length=1024), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("expected_status", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("validation_rule", sa.String(length=255), nullable=True),
        sa.Column("timeout_ms", sa.Integer(), nullable=False, server_default="10000"),
        sa.Column("interval_sec", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("max_latency_ms", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("error_rate_threshold", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("expected_availability", sa.Float(), nullable=False, server_default="99.0"),
        sa.Column("risk_threshold", sa.Float(), nullable=False, server_default="70.0"),
        sa.Column("monitoring", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("health", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_latency_ms", sa.Float(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_api_endpoints_user_id"), "api_endpoints", ["user_id"], unique=False)

    op.create_table(
        "test_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("api_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("expected_status", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("validations", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["api_id"], ["api_endpoints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_test_results_api_id"), "test_results", ["api_id"], unique=False)
    op.create_index(op.f("ix_test_results_user_id"), "test_results", ["user_id"], unique=False)
    op.create_index(op.f("ix_test_results_tested_at"), "test_results", ["tested_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_test_results_tested_at"), table_name="test_results")
    op.drop_index(op.f("ix_test_results_user_id"), table_name="test_results")
    op.drop_index(op.f("ix_test_results_api_id"), table_name="test_results")
    op.drop_table("test_results")
    op.drop_index(op.f("ix_api_endpoints_user_id"), table_name="api_endpoints")
    op.drop_table("api_endpoints")
