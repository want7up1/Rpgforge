from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TurnEvaluation(Base):
    """LLM-as-Judge 对单回合 GM 输出的评分。

    手动触发（admin endpoint 或 CLI），不在 maintenance 中自动跑——judge 自身也消耗
    quota，默认 opt-in。
    """

    __tablename__ = "turn_evaluations"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    turn_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("turns.id", ondelete="CASCADE"),
        nullable=False,
    )
    game_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
    )

    canon_fidelity: Mapped[int | None] = mapped_column(SmallInteger)
    state_consistency: Mapped[int | None] = mapped_column(SmallInteger)
    pacing: Mapped[int | None] = mapped_column(SmallInteger)
    prose_quality: Mapped[int | None] = mapped_column(SmallInteger)
    freshness: Mapped[int | None] = mapped_column(SmallInteger)
    safety: Mapped[int | None] = mapped_column(SmallInteger)

    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    rationale: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    judge_model: Mapped[str | None] = mapped_column(String(128))
    trace_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
