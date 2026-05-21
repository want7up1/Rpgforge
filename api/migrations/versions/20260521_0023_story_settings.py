"""Replace legacy game config fields with story settings.

Revision ID: 20260521_0023
Revises: 20260520_0022
Create Date: 2026-05-21 09:10:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260521_0023"
down_revision = "20260520_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "game_configs",
        sa.Column(
            "story_settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("game_configs", "story_settings", server_default=None)
    op.drop_column("game_configs", "generation_notes")
    op.drop_column("game_configs", "generation_settings")
    op.drop_column("game_configs", "script_outline")
    op.drop_column("game_configs", "worldview")
    op.drop_column("game_configs", "system_prompt")


def downgrade() -> None:
    op.add_column("game_configs", sa.Column("system_prompt", sa.Text(), nullable=True))
    op.add_column(
        "game_configs",
        sa.Column(
            "worldview",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "game_configs",
        sa.Column(
            "script_outline",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "game_configs",
        sa.Column(
            "generation_settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("game_configs", sa.Column("generation_notes", sa.Text(), nullable=True))
    op.drop_column("game_configs", "story_settings")
