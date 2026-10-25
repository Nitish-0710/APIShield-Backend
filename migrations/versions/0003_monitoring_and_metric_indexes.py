"""add monitoring tracking fields and composite metric indexes

Revision ID: 0003_monitoring_and_metric_indexes
Revises: 0002_api_and_test_history
Create Date: 2026-10-25 04:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_monitoring_metrics"
down_revision: Union[str, None] = "0002_api_and_test_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add scheduling & atomic claim columns to api_endpoints
    op.add_column(
        "api_endpoints",
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_api_endpoints_next_run_at"),
        "api_endpoints",
        ["next_run_at"],
        unique=False,
    )
    op.add_column(
        "api_endpoints",
        sa.Column("is_probing", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # 2. Add composite indexes on test_results for high-performance time-series metric queries
    op.create_index(
        "ix_test_results_api_tested_at",
        "test_results",
        ["api_id", "tested_at"],
        unique=False,
    )
    op.create_index(
        "ix_test_results_user_tested_at",
        "test_results",
        ["user_id", "tested_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_test_results_user_tested_at", table_name="test_results")
    op.drop_index("ix_test_results_api_tested_at", table_name="test_results")
    op.drop_column("api_endpoints", "is_probing")
    op.drop_index(op.f("ix_api_endpoints_next_run_at"), table_name="api_endpoints")
    op.drop_column("api_endpoints", "next_run_at")
