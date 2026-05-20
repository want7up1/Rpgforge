"""progress saves

Revision ID: 20260514_0018
Revises: 20260514_0017
Create Date: 2026-05-14

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260514_0018"
down_revision: str | None = "20260514_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "game_states",
        sa.Column(
            "initial_state_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_table(
        "game_progress_saves",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("state_current_turn", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "state_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("state_summary", sa.Text(), nullable=True),
        sa.Column(
            "turns_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "summaries_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "state_deltas_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_game_progress_saves_game_updated
            ON game_progress_saves (game_id, updated_at DESC)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_game_progress_saves_game_updated", table_name="game_progress_saves")
    op.drop_table("game_progress_saves")
    op.drop_column("game_states", "initial_state_json")
