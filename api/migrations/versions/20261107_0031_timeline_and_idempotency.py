"""Fence timeline writers and preserve complete progress replay snapshots.

Revision ID: 20261107_0031
Revises: 20260703_0030
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261107_0031"
down_revision: str | None = "20260703_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name in ("revision", "timeline_generation"):
        op.add_column("games", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.add_column("turn_jobs", sa.Column("request_id", sa.String(128), nullable=True))
    op.add_column("turn_jobs", sa.Column("request_hash", sa.String(64), nullable=True))
    for name in ("game_revision", "timeline_generation", "stream_revision", "event_seq"):
        op.add_column(
            "turn_jobs", sa.Column(name, sa.Integer(), nullable=False, server_default="0")
        )
    op.create_unique_constraint("uq_turn_jobs_game_request", "turn_jobs", ["game_id", "request_id"])
    op.add_column(
        "game_progress_saves",
        sa.Column("snapshot_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "game_progress_saves", sa.Column("initial_state_json", postgresql.JSONB(), nullable=True)
    )
    op.add_column("game_progress_saves", sa.Column("game_status", sa.String(32), nullable=True))
    op.add_column("game_progress_saves", sa.Column("config_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    for name in ("config_hash", "game_status", "initial_state_json", "snapshot_version"):
        op.drop_column("game_progress_saves", name)
    op.drop_constraint("uq_turn_jobs_game_request", "turn_jobs", type_="unique")
    for name in (
        "event_seq",
        "stream_revision",
        "timeline_generation",
        "game_revision",
        "request_hash",
        "request_id",
    ):
        op.drop_column("turn_jobs", name)
    op.drop_column("games", "timeline_generation")
    op.drop_column("games", "revision")
