"""runtime settings

Revision ID: 20260509_0004
Revises: 20260509_0003
Create Date: 2026-05-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260509_0004"
down_revision: str | None = "20260509_0003"
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
        "runtime_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("deepseek_api_key", sa.Text(), nullable=True),
        sa.Column("deepseek_base_url", sa.Text(), nullable=True),
        sa.Column("deepseek_flash_model", sa.Text(), nullable=True),
        sa.Column("deepseek_pro_model", sa.Text(), nullable=True),
        timestamp_column("created_at"),
        timestamp_column("updated_at"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("runtime_settings")
