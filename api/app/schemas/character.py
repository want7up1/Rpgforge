from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

CharacterRole = Literal["protagonist", "npc", "companion", "other"]
CharacterVisibility = Literal["visible", "hidden"]


class CharacterBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list)
    role: CharacterRole = "npc"
    identity: str | None = None
    description: str | None = None
    appearance: str | None = None
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
    portrait_mime_type: str | None = None
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
