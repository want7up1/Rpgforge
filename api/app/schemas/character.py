from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CharacterRole = Literal["protagonist", "antagonist", "npc", "companion", "other"]
CharacterVisibility = Literal["visible", "hidden"]


STORY_PROFILE_KEYS = (
    "dramatic_function",
    "desire",
    "fear",
    "leverage",
    "relationship_arc",
    "public_limit",
)


class CharacterStoryProfile(BaseModel):
    dramatic_function: str = ""
    desire: str = ""
    fear: str = ""
    leverage: str = ""
    relationship_arc: str = ""
    public_limit: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_story_profile(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {
            key: str(value.get(key) or "").strip()
            for key in STORY_PROFILE_KEYS
        }


class CharacterBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list)
    role: CharacterRole = "npc"
    identity: str | None = None
    description: str | None = None
    appearance: str | None = None
    story_profile: CharacterStoryProfile = Field(default_factory=CharacterStoryProfile)
    portrait_prompt: str | None = None
    visibility: CharacterVisibility = "visible"
    is_visible: bool = True

    @field_validator("aliases", mode="before")
    @classmethod
    def normalize_aliases(cls, value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


class CharacterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    aliases: list[str] | None = None
    role: CharacterRole | None = None
    identity: str | None = None
    description: str | None = None
    appearance: str | None = None
    story_profile: CharacterStoryProfile | None = None
    portrait_prompt: str | None = None
    visibility: CharacterVisibility | None = None
    is_visible: bool | None = None

    @field_validator("aliases", mode="before")
    @classmethod
    def normalize_aliases(cls, value) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, str):
            return [value]
        return value


class CharacterRead(CharacterBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    game_id: UUID
    portrait_url: str | None = None
    portrait_thumb_url: str | None = None
    portrait_mime_type: str | None = None
    portrait_thumb_mime_type: str | None = None
    portrait_original_filename: str | None = None
    portrait_uploaded_at: datetime | None = None
    source: str
    created_at: datetime
    updated_at: datetime


class CharacterSyncResponse(BaseModel):
    total: int
    created: int
    updated: int
    characters: list[CharacterRead]
