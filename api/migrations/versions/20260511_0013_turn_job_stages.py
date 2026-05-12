"""turn job stages

Revision ID: 20260511_0013
Revises: 20260511_0012
Create Date: 2026-05-11

"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260511_0013"
down_revision: str | None = "20260511_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE turn_jobs
            ADD COLUMN IF NOT EXISTS stage VARCHAR(64),
            ADD COLUMN IF NOT EXISTS stage_label TEXT,
            ADD COLUMN IF NOT EXISTS stage_index INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS stage_total INTEGER NOT NULL DEFAULT 8,
            ADD COLUMN IF NOT EXISTS stage_started_at TIMESTAMP WITH TIME ZONE
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE turn_jobs
            DROP COLUMN IF EXISTS stage_started_at,
            DROP COLUMN IF EXISTS stage_total,
            DROP COLUMN IF EXISTS stage_index,
            DROP COLUMN IF EXISTS stage_label,
            DROP COLUMN IF EXISTS stage
        """
    )
