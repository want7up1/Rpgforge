"""Add turn_evaluations table for LLM-as-Judge scores.

Revision ID: 20260528_0027
Revises: 20260528_0026
Create Date: 2026-05-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260528_0027"
down_revision: str | None = "20260528_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "turn_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "turn_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("turns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "game_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("games.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # 评分维度（1-5）。SMALLINT 足够。允许 NULL 意味着该维度未评（例如 prompt 改动后扩列）。
        sa.Column("canon_fidelity", sa.SmallInteger(), nullable=True),
        sa.Column("state_consistency", sa.SmallInteger(), nullable=True),
        sa.Column("pacing", sa.SmallInteger(), nullable=True),
        sa.Column("prose_quality", sa.SmallInteger(), nullable=True),
        sa.Column("freshness", sa.SmallInteger(), nullable=True),
        sa.Column("safety", sa.SmallInteger(), nullable=True),
        # 综合分（平均或加权后），方便排序。Judge 模型返回。
        sa.Column("overall_score", sa.Numeric(3, 2), nullable=True),
        # 每个维度一句话评语，自由结构（dict[str, str]）。
        sa.Column(
            "rationale",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("judge_model", sa.String(length=128), nullable=True),
        # 关联到 agent_traces 中的对应 judge 调用，便于回查 prompt。
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        # judge 自身可能失败：status in {success, error}
        sa.Column("status", sa.String(length=32), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_turn_evaluations_game_created",
        "turn_evaluations",
        ["game_id", "created_at"],
    )
    op.create_index(
        "ix_turn_evaluations_turn",
        "turn_evaluations",
        ["turn_id"],
    )
    op.create_index(
        "ix_turn_evaluations_overall",
        "turn_evaluations",
        ["overall_score"],
    )


def downgrade() -> None:
    op.drop_index("ix_turn_evaluations_overall", table_name="turn_evaluations")
    op.drop_index("ix_turn_evaluations_turn", table_name="turn_evaluations")
    op.drop_index("ix_turn_evaluations_game_created", table_name="turn_evaluations")
    op.drop_table("turn_evaluations")
