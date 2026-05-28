from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AgentTrace(Base):
    """每一次 LLM 调用的审计记录。

    弱关联到上游 job：删除 turn_job 不会删除 trace，便于事后回查"为什么这一轮跑成了
    这样"。trace 落库走自己的短事务，不阻塞主回合 LLM 调用。
    """

    __tablename__ = "agent_traces"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    # 弱关联：job_kind in {"turn", "generator_chat", "generator_finalize"}
    job_kind: Mapped[str | None] = mapped_column(String(32))
    job_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))

    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))

    prompt_messages: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    output_text: Mapped[str | None] = mapped_column(Text)
    reasoning_text: Mapped[str | None] = mapped_column(Text)

    tokens_input: Mapped[int | None] = mapped_column(Integer)
    tokens_output: Mapped[int | None] = mapped_column(Integer)
    tokens_reasoning: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    extras: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
