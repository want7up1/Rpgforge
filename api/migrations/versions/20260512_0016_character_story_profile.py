"""character story profile

Revision ID: 20260512_0016
Revises: 20260512_0015
Create Date: 2026-05-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260512_0016"
down_revision: str | None = "20260512_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column(
            "story_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "characters",
        sa.Column(
            "sync_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "characters",
        sa.Column(
            "manual_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("characters", sa.Column("portrait_thumb_path", sa.Text(), nullable=True))
    op.add_column(
        "characters",
        sa.Column("portrait_thumb_mime_type", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("characters", "portrait_thumb_mime_type")
    op.drop_column("characters", "portrait_thumb_path")
    op.drop_column("characters", "manual_fields")
    op.drop_column("characters", "sync_meta")
    op.drop_column("characters", "story_profile")
