"""Add telemetry columns and runtime inputs to turn_jobs.

Revision ID: 20260528_0025
Revises: 20260521_0024
Create Date: 2026-05-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260528_0025"
down_revision: str | None = "20260521_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "turn_jobs",
        sa.Column(
            "director_used_fallback",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "turn_jobs",
        sa.Column("drift_severity", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "turn_jobs",
        sa.Column(
            "rewrite_triggered",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "turn_jobs",
        sa.Column(
            "extractor_failed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Director 决策 + Drift 校验结果，留给 maintenance 阶段的 StateExtractor 复用。
    op.add_column(
        "turn_jobs",
        sa.Column(
            "turn_runtime_inputs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("turn_jobs", "turn_runtime_inputs")
    op.drop_column("turn_jobs", "extractor_failed")
    op.drop_column("turn_jobs", "rewrite_triggered")
    op.drop_column("turn_jobs", "drift_severity")
    op.drop_column("turn_jobs", "director_used_fallback")
