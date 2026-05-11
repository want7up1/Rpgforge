"""turns

Revision ID: 20260509_0002
Revises: 20260509_0001
Create Date: 2026-05-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260509_0002"
down_revision: str | None = "20260509_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("player_input", sa.Text(), nullable=False),
        sa.Column("gm_output", sa.Text(), nullable=False),
        sa.Column("visible_summary", sa.Text(), nullable=True),
        sa.Column("hidden_summary", sa.Text(), nullable=True),
        sa.Column("state_delta_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("action_options_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "turn_number", name="uq_turns_game_turn_number"),
    )
    op.create_index("ix_turns_game_id", "turns", ["game_id"])
    op.create_index("ix_turns_game_turn_number", "turns", ["game_id", "turn_number"])


def downgrade() -> None:
    op.drop_index("ix_turns_game_turn_number", table_name="turns")
    op.drop_index("ix_turns_game_id", table_name="turns")
    op.drop_table("turns")
