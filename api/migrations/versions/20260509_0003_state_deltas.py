"""state deltas

Revision ID: 20260509_0003
Revises: 20260509_0002
Create Date: 2026-05-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260509_0003"
down_revision: str | None = "20260509_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_column(name: str):
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "state_deltas",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delta_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        timestamp_column("created_at"),
        timestamp_column("updated_at"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_state_deltas_game_id", "state_deltas", ["game_id"])
    op.create_index("ix_state_deltas_turn_id", "state_deltas", ["turn_id"])
    op.create_index("ix_state_deltas_status", "state_deltas", ["status"])


def downgrade() -> None:
    op.drop_index("ix_state_deltas_status", table_name="state_deltas")
    op.drop_index("ix_state_deltas_turn_id", table_name="state_deltas")
    op.drop_index("ix_state_deltas_game_id", table_name="state_deltas")
    op.drop_table("state_deltas")
