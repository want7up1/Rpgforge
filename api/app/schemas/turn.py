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
