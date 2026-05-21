"""state delta error message

Revision ID: 20260520_0020
Revises: 20260520_0019
Create Date: 2026-05-20

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260520_0020"
down_revision: str | None = "20260520_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("state_deltas", sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("state_deltas", "error_message")
