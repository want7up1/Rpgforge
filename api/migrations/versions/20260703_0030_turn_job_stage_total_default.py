"""Set turn job stage_total default to current stage count.

Revision ID: 20260703_0030
Revises: 20260604_0029
Create Date: 2026-07-03

"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260703_0030"
down_revision: str | None = "20260604_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE turn_jobs ALTER COLUMN stage_total SET DEFAULT 6")


def downgrade() -> None:
    op.execute("ALTER TABLE turn_jobs ALTER COLUMN stage_total SET DEFAULT 8")
