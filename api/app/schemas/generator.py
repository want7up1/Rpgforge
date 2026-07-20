from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.game import GameDetail

GeneratorJobStatus = Literal["pending", "running", "completed", "failed"]


class GeneratorMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class GeneratorChatRequest(BaseModel):
    user_input: str = Field(min_length=1)
    history: list[GeneratorMessage] = Field(default_factory=list)
    confirmed_requirements: dict[str, Any] = Field(default_factory=dict)
    locked_fields: list[str] = Field(default_factory=list)


class GeneratorChatResponse(BaseModel):
    stage: Literal["interview", "ready_to_generate"]
    confirmed_requirements: dict[str, Any] = Field(default_factory=dict)
    missing_questions: list[str] = Field(default_factory=list)
    assistant_reply: str
    model_used: str


class GeneratorChatJobCreateResponse(BaseModel):
    id: UUID
    status: GeneratorJobStatus


class GeneratorChatJobRead(BaseModel):
    id: UUID
    status: GeneratorJobStatus
    response: GeneratorChatResponse | None = None
    model_used: str | None = None
    error_message: str | None = None
    reasoning_content: str = ""
    content_buffer: str = ""
    progress_message: str | None = None
    stream_started_at: datetime | None = None
    last_event_at: datetime | None = None


class GeneratedGameConfig(BaseModel):
    title: str = Field(min_length=1)
    genre: str | None = None
    description: str | None = None
    story_settings: dict[str, Any] = Field(default_factory=dict)
    initial_state: dict[str, Any] = Field(default_factory=dict)
    voice_profiles: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("title", mode="before")
    @classmethod
    def fill_game_title(cls, value: Any) -> str:
        if isinstance(value, str) and value.strip():
            return value
        return "未命名游戏"

    @field_validator("story_settings", "initial_state", mode="before")
    @classmethod
    def coerce_object_field(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return {"summary": value}
        return {"value": value}


class GeneratorFinalizeRequest(BaseModel):
    concept: str = Field(min_length=1)
    history: list[GeneratorMessage] = Field(default_factory=list)
    confirmed_requirements: dict[str, Any] = Field(default_factory=dict)


class GeneratorFinalizeResponse(BaseModel):
    config: GeneratedGameConfig
    model_used: str
    warnings: list[str] = Field(default_factory=list)


class GeneratorFinalizeJobCreateResponse(BaseModel):
    id: UUID
    status: GeneratorJobStatus


class GeneratorFinalizeJobRead(BaseModel):
    id: UUID
    status: GeneratorJobStatus
    config: GeneratedGameConfig | None = None
    warnings: list[str] = Field(default_factory=list)
    model_used: str | None = None
    error_message: str | None = None
    reasoning_content: str = ""
    content_buffer: str = ""
    progress_message: str | None = None
    stream_started_at: datetime | None = None
    last_event_at: datetime | None = None


class GeneratorCreateGameRequest(BaseModel):
    generated_config: GeneratedGameConfig


class GeneratorCreateGameResponse(BaseModel):
    game: GameDetail
