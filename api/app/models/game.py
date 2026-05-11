from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.character import Character
    from app.models.lore import LoreEntry
    from app.models.mode import Mode
    from app.models.state import GameState
    from app.models.state_delta import StateDelta
    from app.models.summary import Summary
    from app.models.turn import Turn


class Game(Base):
    __tablename__ = "games"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    genre: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
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

    config: Mapped[GameConfig | None] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        uselist=False,
    )
    state: Mapped[GameState | None] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        uselist=False,
    )
    lore_entries: Mapped[list[LoreEntry]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
    )
    modes: Mapped[list[Mode]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
    )
    turns: Mapped[list[Turn]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        order_by="Turn.turn_number",
    )
    characters: Mapped[list[Character]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        order_by="Character.name",
    )
    summaries: Mapped[list[Summary]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        order_by="Summary.range_end_turn",
    )
    state_deltas: Mapped[list[StateDelta]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
    )


class GameConfig(Base):
    __tablename__ = "game_configs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    system_prompt: Mapped[str | None] = mapped_column(Text)
    worldview: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    script_outline: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    generation_notes: Mapped[str | None] = mapped_column(Text)
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

    game: Mapped[Game] = relationship(back_populates="config")
