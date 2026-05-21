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
    story_settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class GameConfigUpdate(BaseModel):
    story_settings: Any | None = None
    story_settings_json: Any | None = None


class GameSettingVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    game_id: UUID
    scope: str
    entity_id: UUID | None
    action: str
    snapshot_json: dict[str, Any]
    created_at: datetime


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
    summaries: list[SummaryRead] = Field(default_factory=list)
    turns: list[TurnRead] = Field(default_factory=list)


class ContextDiagnosticRead(BaseModel):
    turn_id: UUID | None
    turn_number: int | None
    player_input: str
    selected_action_style: dict[str, Any] | None = None
    recent_turn_numbers: list[int]
    memory_summaries: dict[str, Any]
    runtime_story: dict[str, Any] = Field(default_factory=dict)
    related_story_materials: list[dict[str, Any]] = Field(default_factory=list)


class GameMemoryRead(BaseModel):
    game: GameListItem
    current_turn: int
    turn_count: int
    summaries: list[SummaryRead]


class SummaryRebuildResponse(BaseModel):
    total: int
    summaries: list[SummaryRead]


class GameProgressSaveCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    note: str | None = Field(default=None, max_length=1000)


class GameProgressSaveUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    note: str | None = Field(default=None, max_length=1000)


class GameProgressSaveRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    game_id: UUID
    name: str
    note: str | None
    state_current_turn: int
    turn_count: int
    summary_count: int
    created_at: datetime
    updated_at: datetime
