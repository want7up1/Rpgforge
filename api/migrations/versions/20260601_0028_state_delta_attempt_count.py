"""Add attempt_count to state_deltas for failed-delta auto-downgrade.

Revision ID: 20260601_0028
Revises: 20260528_0027
Create Date: 2026-06-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260601_0028"
down_revision: str | None = "20260528_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 累计提取尝试次数。server_default="0" 让既有行回填 0；NOT NULL 保证读取无 None。
    op.add_column(
        "state_deltas",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("state_deltas", "attempt_count")
