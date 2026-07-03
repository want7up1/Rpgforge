from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class GeneratorChatJob(Base):
    __tablename__ = "generator_chat_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    model_used: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    reasoning_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_buffer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    progress_message: Mapped[str | None] = mapped_column(Text)
    stream_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GeneratorFinalizeJob(Base):
    __tablename__ = "generator_finalize_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    model_used: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    reasoning_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_buffer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    progress_message: Mapped[str | None] = mapped_column(Text)
    stream_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TurnJob(Base):
    __tablename__ = "turn_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    turn_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    model_used: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    reasoning_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_buffer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    narrative_buffer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    progress_message: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str | None] = mapped_column(String(64))
    stage_label: Mapped[str | None] = mapped_column(Text)
    stage_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage_total: Mapped[int] = mapped_column(Integer, nullable=False, default=6, server_default="6")
    stage_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    maintenance_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
    )
    maintenance_stage: Mapped[str | None] = mapped_column(String(64))
    maintenance_message: Mapped[str | None] = mapped_column(Text)
    maintenance_error: Mapped[str | None] = mapped_column(Text)
    maintenance_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    maintenance_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Telemetry：记录每回合 Agent 链路的降级 / 重写 / 失败情况。
    director_used_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    drift_severity: Mapped[str | None] = mapped_column(String(32))
    rewrite_triggered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extractor_failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Director 决策 + Drift 校验结果，供 maintenance 阶段的 StateExtractor 复用。
    turn_runtime_inputs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    stream_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
