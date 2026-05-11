"""phase1 schema

Revision ID: 20260509_0001
Revises:
Create Date: 2026-05-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "20260509_0001"
down_revision: str | None = None
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
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "games",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("genre", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        timestamp_column("created_at"),
        timestamp_column("updated_at"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "game_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("worldview", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("script_outline", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generation_notes", sa.Text(), nullable=True),
        timestamp_column("created_at"),
        timestamp_column("updated_at"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id"),
    )
    op.create_table(
        "game_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("current_turn", sa.Integer(), nullable=False),
        sa.Column("state_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        timestamp_column("created_at"),
        timestamp_column("updated_at"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id"),
    )
    op.create_table(
        "lore_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=True),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("trigger_words", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=True),
        sa.Column("always_on", sa.Boolean(), nullable=False),
        sa.Column("visibility", sa.String(length=64), nullable=True),
        sa.Column("public_info", sa.Text(), nullable=True),
        sa.Column("gm_secret", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("usage_note", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        timestamp_column("created_at"),
        timestamp_column("updated_at"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "modes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("triggers", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("injection", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        timestamp_column("created_at"),
        timestamp_column("updated_at"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_games_created_at", "games", ["created_at"])
    op.create_index("ix_lore_entries_game_id", "lore_entries", ["game_id"])
    op.create_index("ix_modes_game_id", "modes", ["game_id"])


def downgrade() -> None:
    op.drop_index("ix_modes_game_id", table_name="modes")
    op.drop_index("ix_lore_entries_game_id", table_name="lore_entries")
    op.drop_index("ix_games_created_at", table_name="games")
    op.drop_table("modes")
    op.drop_table("lore_entries")
    op.drop_table("game_states")
    op.drop_table("game_configs")
    op.drop_table("games")
