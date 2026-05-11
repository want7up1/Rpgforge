from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.game import Game
    from app.models.state_delta import StateDelta


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    player_input: Mapped[str] = mapped_column(Text, nullable=False)
    gm_output: Mapped[str] = mapped_column(Text, nullable=False)
    visible_summary: Mapped[str | None] = mapped_column(Text)
    hidden_summary: Mapped[str | None] = mapped_column(Text)
    state_delta_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    action_options_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    model_used: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    game: Mapped[Game] = relationship(back_populates="turns")
    state_deltas: Mapped[list[StateDelta]] = relationship(
        back_populates="turn",
        cascade="all, delete-orphan",
    )
