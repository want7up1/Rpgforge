"""persist applied settlement receipts for player feedback

Revision ID: 20261107_0032
Revises: 20261107_0031
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261107_0032"
down_revision = "20261107_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "turns",
        sa.Column(
            "settlement_receipt",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("turns", "settlement_receipt")
