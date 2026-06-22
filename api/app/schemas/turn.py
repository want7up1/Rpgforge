from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ActionOption(BaseModel):
    key: Literal["A", "B", "C", "D"]
    label: str = Field(min_length=1)


class TurnCreate(BaseModel):
    player_input: str | None = Field(default=None, max_length=8000)
    selected_option: ActionOption | None = None

    @model_validator(mode="after")
    def validate_action_source(self) -> "TurnCreate":
        if self.selected_option is None and not (self.player_input or "").strip():
            raise ValueError("player_input or selected_option is required.")
        return self

    @property
    def resolved_player_input(self) -> str:
        if self.selected_option is not None:
            return f"{self.selected_option.key}. {self.selected_option.label}"
        return (self.player_input or "").strip()


class TurnRewindRequest(BaseModel):
    """C6 后悔药：回退到第 to_turn 回合（删除其后的回合）。to_turn=0 回到开局。"""

    to_turn: int = Field(ge=0)


class GMRuntimeOutput(BaseModel):
    narrative: str = Field(min_length=1)
    visible_clues: list[str] = Field(default_factory=list)
    action_options: list[ActionOption] = Field(min_length=4, max_length=4)

    @field_validator("action_options")
    @classmethod
    def require_abcd(cls, value: list[ActionOption]) -> list[ActionOption]:
        keys = [option.key for option in value]
        if keys != ["A", "B", "C", "D"]:
            raise ValueError("action_options must contain A, B, C, D in order.")
        return value


class TurnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    game_id: UUID
    turn_number: int
    player_input: str
    gm_output: str
    visible_summary: str | None
    hidden_summary: str | None
    state_delta_json: dict[str, Any]
    action_options_json: list[ActionOption]
    model_used: str | None
    created_at: datetime


class TurnAgentCost(BaseModel):
    """单个 agent 在某回合的 token / cache 消耗。"""

    agent: str
    model: str | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    tokens_reasoning: int | None = None
    cache_hit_tokens: int | None = None
    cache_miss_tokens: int | None = None


class TurnInsights(BaseModel):
    """游戏界面"本回合详情"折叠面板的数据：观测 + token/cache。"""

    turn_id: UUID
    observation: dict[str, Any] | None = None
    agents: list[TurnAgentCost] = Field(default_factory=list)
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_cache_hit_tokens: int = 0
    total_cache_miss_tokens: int = 0
    cache_hit_rate: float | None = None


TurnJobStatus = Literal["pending", "running", "completed", "failed"]
TurnJobMaintenanceStatus = Literal["pending", "running", "completed", "failed", "skipped"]


class TurnJobCreateResponse(BaseModel):
    id: UUID
    status: TurnJobStatus


class TurnJobRead(BaseModel):
    id: UUID
    game_id: UUID
    status: TurnJobStatus
    turn: TurnRead | None = None
    turn_id: UUID | None = None
    model_used: str | None = None
    error_message: str | None = None
    reasoning_content: str = ""
    content_buffer: str = ""
    narrative_buffer: str = ""
    progress_message: str | None = None
    stage: str | None = None
    stage_label: str | None = None
    stage_index: int = 0
    stage_total: int = 7
    stage_started_at: datetime | None = None
    maintenance_status: TurnJobMaintenanceStatus = "completed"
    maintenance_stage: str | None = None
    maintenance_message: str | None = None
    maintenance_error: str | None = None
    maintenance_started_at: datetime | None = None
    maintenance_completed_at: datetime | None = None
    director_used_fallback: bool = False
    drift_severity: str | None = None
    rewrite_triggered: bool = False
    extractor_failed: bool = False
    stream_started_at: datetime | None = None
    last_event_at: datetime | None = None
