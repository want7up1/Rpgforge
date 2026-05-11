"""summaries and lore vector index

Revision ID: 20260511_0010
Revises: 20260509_0009
Create Date: 2026-05-11

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260511_0010"
down_revision: str | None = "20260509_0009"
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
        "summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("range_start_turn", sa.Integer(), nullable=True),
        sa.Column("range_end_turn", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("important_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        timestamp_column("created_at"),
        timestamp_column("updated_at"),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_summaries_game_id", "summaries", ["game_id"])
    op.create_index(
        "ix_summaries_game_type_range",
        "summaries",
        ["game_id", "type", "range_end_turn"],
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_lore_entries_embedding_cosine
        ON lore_entries
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_lore_entries_embedding_cosine")
    op.drop_index("ix_summaries_game_type_range", table_name="summaries")
    op.drop_index("ix_summaries_game_id", table_name="summaries")
    op.drop_table("summaries")
