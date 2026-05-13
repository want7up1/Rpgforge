from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.game import Game


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (
        UniqueConstraint("game_id", "name", name="uq_characters_game_name"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    game_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("games.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="npc")
    identity: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    appearance: Mapped[str | None] = mapped_column(Text)
    story_profile: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    portrait_prompt: Mapped[str | None] = mapped_column(Text)
    portrait_path: Mapped[str | None] = mapped_column(Text)
    portrait_mime_type: Mapped[str | None] = mapped_column(Text)
    portrait_original_filename: Mapped[str | None] = mapped_column(Text)
    portrait_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    portrait_thumb_path: Mapped[str | None] = mapped_column(Text)
    portrait_thumb_mime_type: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="visible")
    is_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    sync_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    manual_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
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

    game: Mapped[Game] = relationship(back_populates="characters")
