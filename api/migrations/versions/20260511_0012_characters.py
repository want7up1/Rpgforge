"""characters

Revision ID: 20260511_0012
Revises: 20260511_0011
Create Date: 2026-05-11

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260511_0012"
down_revision: str | None = "20260511_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "characters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "aliases",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=32), server_default="npc", nullable=False),
        sa.Column("identity", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("appearance", sa.Text(), nullable=True),
        sa.Column("portrait_prompt", sa.Text(), nullable=True),
        sa.Column("portrait_path", sa.Text(), nullable=True),
        sa.Column("portrait_mime_type", sa.Text(), nullable=True),
        sa.Column("portrait_original_filename", sa.Text(), nullable=True),
        sa.Column("portrait_uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visibility", sa.String(length=32), server_default="visible", nullable=False),
        sa.Column("is_visible", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("source", sa.String(length=32), server_default="generated", nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "name", name="uq_characters_game_name"),
    )
    op.create_index("ix_characters_game_id", "characters", ["game_id"])


def downgrade() -> None:
    op.drop_index("ix_characters_game_id", table_name="characters")
    op.drop_table("characters")
