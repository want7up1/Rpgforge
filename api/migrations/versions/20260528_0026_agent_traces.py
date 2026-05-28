"""Add agent_traces table for LLM call observability.

Revision ID: 20260528_0026
Revises: 20260528_0025
Create Date: 2026-05-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260528_0026"
down_revision: str | None = "20260528_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # 弱关联到 job：不加 FK，避免 turn_job 删除时 trace 也消失（trace 是审计资产）。
        sa.Column("job_kind", sa.String(length=32), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Agent 标识：agent 字段 = task_type 的语义化命名；task_type 是路由用的原始 key。
        sa.Column("agent", sa.String(length=64), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        # 调用内容。prompt_messages 完整存 JSONB；output_text 是 LLM 原始返回。
        sa.Column(
            "prompt_messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("reasoning_text", sa.Text(), nullable=True),
        # 度量
        sa.Column("tokens_input", sa.Integer(), nullable=True),
        sa.Column("tokens_output", sa.Integer(), nullable=True),
        sa.Column("tokens_reasoning", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        # 结果状态：success | timeout | error | empty_content
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        # 附加 JSONB：例如 streaming=True、max_tokens、reasoning_effort 等。
        sa.Column(
            "extras",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_agent_traces_job",
        "agent_traces",
        ["job_kind", "job_id"],
    )
    op.create_index(
        "ix_agent_traces_agent_created",
        "agent_traces",
        ["agent", "created_at"],
    )
    op.create_index(
        "ix_agent_traces_status_created",
        "agent_traces",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_traces_status_created", table_name="agent_traces")
    op.drop_index("ix_agent_traces_agent_created", table_name="agent_traces")
    op.drop_index("ix_agent_traces_job", table_name="agent_traces")
    op.drop_table("agent_traces")
