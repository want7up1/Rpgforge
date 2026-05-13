from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.schemas.game import GameDetail

GeneratorJobStatus = Literal["pending", "running", "completed", "failed"]


class GeneratorMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class GeneratorChatRequest(BaseModel):
    user_input: str = Field(min_length=1)
    history: list[GeneratorMessage] = Field(default_factory=list)
    confirmed_requirements: dict[str, Any] = Field(default_factory=dict)


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


class GeneratedLoreEntry(BaseModel):
    title: str = Field(min_length=1)
    type: str = "secret"
    keywords: list[str] = Field(default_factory=list)
    trigger_words: list[str] = Field(default_factory=list)
    priority: str = "medium"
    always_on: bool = False
    visibility: str = "mixed"
    public_info: str = ""
    gm_secret: str = ""
    content: str = Field(min_length=1)
    usage_note: str = ""

    @field_validator("title", mode="before")
    @classmethod
    def fill_lore_title(cls, value: Any) -> str:
        if isinstance(value, str) and value.strip():
            return value
        return "未命名世界书条目"

    @field_validator("content", mode="before")
    @classmethod
    def fill_lore_content(cls, value: Any, info: ValidationInfo) -> str:
        if isinstance(value, str) and value.strip():
            return value
        if value is not None and not isinstance(value, str):
            return str(value)

        data = info.data
        fallback_parts = [
            data.get("public_info"),
            data.get("gm_secret"),
            data.get("title"),
        ]
        fallback = "\n".join(
            str(part).strip()
            for part in fallback_parts
            if str(part or "").strip()
        )
        return fallback or "待补全世界书条目。"

    @field_validator("keywords", "trigger_words", mode="before")
    @classmethod
    def coerce_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


class GeneratedMode(BaseModel):
    name: str = Field(min_length=1)
    triggers: list[str] = Field(default_factory=list)
    injection: str = Field(min_length=1)
    priority: str = "medium"
    enabled: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def fill_mode_name(cls, value: Any) -> str:
        if isinstance(value, str) and value.strip():
            return value
        return "默认模式"

    @field_validator("injection", mode="before")
    @classmethod
    def fill_mode_injection(cls, value: Any, info: ValidationInfo) -> str:
        if isinstance(value, str) and value.strip():
            return value
        if value is not None and not isinstance(value, str):
            return str(value)
        mode_name = str(info.data.get("name") or "当前模式")
        return f"按照{mode_name}处理当前场景，保持玩家可见信息与 GM 隐藏信息分离。"

    @field_validator("triggers", mode="before")
    @classmethod
    def coerce_trigger_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


class GeneratedCharacterProfile(BaseModel):
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    role: str = "npc"
    identity: str = ""
    description: str = ""
    appearance: str = ""
    portrait_prompt: str = ""
    visibility: str = "visible"
    dramatic_function: str = ""
    desire: str = ""
    fear: str = ""
    leverage: str = ""
    relationship_arc: str = ""
    public_limit: str = ""

    @field_validator("aliases", mode="before")
    @classmethod
    def coerce_aliases(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


class GeneratedGameConfig(BaseModel):
    title: str = Field(min_length=1)
    genre: str | None = None
    description: str | None = None
    system_prompt: str = Field(min_length=1)
    worldview: dict[str, Any] = Field(default_factory=dict)
    script_outline: dict[str, Any] = Field(default_factory=dict)
    generation_notes: str = ""
    characters: list[GeneratedCharacterProfile] = Field(default_factory=list)
    lore_entries: list[GeneratedLoreEntry] = Field(default_factory=list)
    modes: list[GeneratedMode] = Field(default_factory=list)
    initial_state: dict[str, Any] = Field(default_factory=dict)
    voice_profiles: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("title", mode="before")
    @classmethod
    def fill_game_title(cls, value: Any) -> str:
        if isinstance(value, str) and value.strip():
            return value
        return "未命名游戏"

    @field_validator("system_prompt", mode="before")
    @classmethod
    def fill_system_prompt(cls, value: Any) -> str:
        if isinstance(value, str) and value.strip():
            return value
        return (
            "你是本局 GM。每回合输出玩家可见剧情，并给出 A/B/C/D 四个具体行动选项；"
            "输出格式必须遵守 RPGForge 剧情 Markdown 契约。"
        )

    @field_validator("worldview", "script_outline", "initial_state", mode="before")
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


class GeneratorFinalizeJobCreateResponse(BaseModel):
    id: UUID
    status: GeneratorJobStatus


class GeneratorFinalizeJobRead(BaseModel):
    id: UUID
    status: GeneratorJobStatus
    config: GeneratedGameConfig | None = None
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
