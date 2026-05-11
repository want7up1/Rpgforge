from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.turn import TurnRead


class GameCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    genre: str | None = None
    description: str | None = None


class GameConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    game_id: UUID
    system_prompt: str | None
    worldview: dict[str, Any]
    script_outline: dict[str, Any]
    generation_notes: str | None
    created_at: datetime
    updated_at: datetime


class LoreEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    game_id: UUID
    title: str
    type: str | None
    keywords: list[str]
    trigger_words: list[str]
    priority: str | None
    always_on: bool
    visibility: str | None
    public_info: str | None
    gm_secret: str | None
    content: str
    usage_note: str | None
    created_at: datetime
    updated_at: datetime


class LoreEntryMemoryRead(LoreEntryRead):
    embedding_configured: bool = False


class ModeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    game_id: UUID
    name: str
    triggers: list[str]
    injection: str
    priority: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class GameStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    game_id: UUID
    current_turn: int
    state_json: dict[str, Any]
    summary: str | None
    created_at: datetime
    updated_at: datetime


class SummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    game_id: UUID
    type: str
    range_start_turn: int | None
    range_end_turn: int | None
    content: str
    important_facts: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class GameListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    genre: str | None
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class GameDetail(GameListItem):
    config: GameConfigRead | None
    state: GameStateRead | None
    lore_entries: list[LoreEntryRead]
    modes: list[ModeRead]
    summaries: list[SummaryRead] = Field(default_factory=list)
    turns: list[TurnRead] = Field(default_factory=list)


class LoreDiagnosticRead(BaseModel):
    id: UUID
    title: str
    type: str | None
    priority: str | None
    always_on: bool
    keywords: list[str]
    trigger_words: list[str]
    usage_note: str | None
    score: float | None = None
    keyword_score: float | None = None
    vector_score: float | None = None
    matched_terms: list[str] = Field(default_factory=list)


class ContextDiagnosticRead(BaseModel):
    turn_id: UUID | None
    turn_number: int | None
    player_input: str
    selected_mode: ModeRead | None
    recent_turn_numbers: list[int]
    memory_summaries: dict[str, Any]
    always_on_lore: list[LoreDiagnosticRead]
    related_lore: list[LoreDiagnosticRead]


class GameMemoryRead(BaseModel):
    game: GameListItem
    current_turn: int
    turn_count: int
    lore_entries: list[LoreEntryMemoryRead]
    summaries: list[SummaryRead]


class LoreReindexResponse(BaseModel):
    total: int
    updated: int


class SummaryRebuildResponse(BaseModel):
    total: int
    summaries: list[SummaryRead]
