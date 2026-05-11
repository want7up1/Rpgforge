"""turn job narrative buffer

Revision ID: 20260509_0009
Revises: 20260509_0008
Create Date: 2026-05-09

"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260509_0009"
down_revision: str | None = "20260509_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE turn_jobs
            ADD COLUMN IF NOT EXISTS narrative_buffer TEXT NOT NULL DEFAULT ''
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE turn_jobs DROP COLUMN IF EXISTS narrative_buffer")
