"""Drop legacy lore and mode tables.

Revision ID: 20260521_0024
Revises: 20260521_0023
Create Date: 2026-05-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260521_0024"
down_revision: str | None = "20260521_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("modes")
    op.drop_table("lore_entries")


def downgrade() -> None:
    op.create_table(
        "lore_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=True),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("trigger_words", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("priority", sa.Text(), nullable=True),
        sa.Column("always_on", sa.Boolean(), nullable=False),
        sa.Column("visibility", sa.Text(), nullable=True),
        sa.Column("public_info", sa.Text(), nullable=True),
        sa.Column("gm_secret", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("usage_note", sa.Text(), nullable=True),
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_lore_entries_game_id", "lore_entries", ["game_id"])
    op.create_index("ix_lore_entries_active", "lore_entries", ["game_id", "is_active"])

    op.create_table(
        "modes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("triggers", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("injection", sa.Text(), nullable=False),
        sa.Column("priority", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_modes_game_id", "modes", ["game_id"])
