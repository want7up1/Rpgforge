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
    is_active: bool = True
    archived_at: datetime | None = None
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


class WorldviewUpdate(BaseModel):
    summary: str | None = None
    tone: str | None = None
    genre: str | None = None
    key_npcs: list[str] | None = None
    factions: list[str] | None = None
    conflicts: list[str] | None = None


class ContractUpdate(BaseModel):
    premise: str | None = None
    player_fantasy: str | None = None
    central_question: str | None = None
    emotional_arc: str | None = None
    main_goal: str | None = None
    current_act: str | None = None
    narrative_style: str | None = None
    tone: str | None = None
    pacing: str | None = None
    narrative_focus: str | None = None
    canon_terms: list[str] | None = None
    key_npcs: list[str] | None = None
    key_conflicts: list[str] | None = None
    forbidden_drift: list[str] | None = None
    forbidden_reveals: list[str] | None = None
    must_preserve: list[str] | None = None
    must_not_become: list[str] | None = None
    guardrails: list[str] | None = None
    act_plan: list[str] | None = None


class GameConfigUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    genre: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    generation_notes: str | None = None
    worldview: WorldviewUpdate | None = None
    worldview_json: Any | None = None
    script_outline_json: Any | None = None
    campaign_contract: ContractUpdate | None = None
    director_contract: ContractUpdate | None = None
    story_contract: ContractUpdate | None = None


class LoreEntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    type: str | None = "setting"
    keywords: list[str] = Field(default_factory=list)
    trigger_words: list[str] = Field(default_factory=list)
    priority: str | None = "medium"
    always_on: bool = False
    visibility: str | None = "mixed"
    public_info: str | None = None
    gm_secret: str | None = None
    content: str = Field(min_length=1)
    usage_note: str | None = None


class LoreEntryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = None
    keywords: list[str] | None = None
    trigger_words: list[str] | None = None
    priority: str | None = None
    always_on: bool | None = None
    visibility: str | None = None
    public_info: str | None = None
    gm_secret: str | None = None
    content: str | None = Field(default=None, min_length=1)
    usage_note: str | None = None
    is_active: bool | None = None


class ModeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    triggers: list[str] = Field(default_factory=list)
    injection: str = Field(min_length=1)
    priority: str | None = "medium"
    enabled: bool = True


class ModeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    triggers: list[str] | None = None
    injection: str | None = Field(default=None, min_length=1)
    priority: str | None = None
    enabled: bool | None = None


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
    campaign_contract: dict[str, Any] = Field(default_factory=dict)
    story_blueprint: dict[str, Any] = Field(default_factory=dict)
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
