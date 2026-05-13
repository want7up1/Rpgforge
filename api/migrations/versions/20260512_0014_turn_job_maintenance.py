"""turn job maintenance status

Revision ID: 20260512_0014
Revises: 20260511_0013
Create Date: 2026-05-12

"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260512_0014"
down_revision: str | None = "20260511_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE turn_jobs
            ADD COLUMN IF NOT EXISTS maintenance_status VARCHAR(32) NOT NULL DEFAULT 'completed',
            ADD COLUMN IF NOT EXISTS maintenance_stage VARCHAR(64),
            ADD COLUMN IF NOT EXISTS maintenance_message TEXT,
            ADD COLUMN IF NOT EXISTS maintenance_error TEXT,
            ADD COLUMN IF NOT EXISTS maintenance_started_at TIMESTAMP WITH TIME ZONE,
            ADD COLUMN IF NOT EXISTS maintenance_completed_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_turn_jobs_maintenance_status
            ON turn_jobs (maintenance_status)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_turn_jobs_maintenance_status")
    op.execute(
        """
        ALTER TABLE turn_jobs
            DROP COLUMN IF EXISTS maintenance_completed_at,
            DROP COLUMN IF EXISTS maintenance_started_at,
            DROP COLUMN IF EXISTS maintenance_error,
            DROP COLUMN IF EXISTS maintenance_message,
            DROP COLUMN IF EXISTS maintenance_stage,
            DROP COLUMN IF EXISTS maintenance_status
        """
    )
