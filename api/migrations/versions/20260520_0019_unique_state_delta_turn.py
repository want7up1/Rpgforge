"""unique state delta per turn

Revision ID: 20260520_0019
Revises: 20260514_0018
Create Date: 2026-05-20

"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260520_0019"
down_revision: str | None = "20260514_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM state_deltas AS state_delta
        USING (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY turn_id
                    ORDER BY
                        CASE status
                            WHEN 'approved' THEN 0
                            WHEN 'edited' THEN 1
                            WHEN 'pending' THEN 2
                            ELSE 3
                        END,
                        COALESCE(approved_at, updated_at, created_at) DESC,
                        created_at DESC
                ) AS duplicate_rank
            FROM state_deltas
        ) AS ranked
        WHERE state_delta.id = ranked.id
            AND ranked.duplicate_rank > 1
        """
    )
    op.create_unique_constraint(
        "uq_state_deltas_turn_id",
        "state_deltas",
        ["turn_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_state_deltas_turn_id",
        "state_deltas",
        type_="unique",
    )
