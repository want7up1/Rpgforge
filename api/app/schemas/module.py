from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

MODULE_EXPORT_FORMAT_VERSION = "rpgforge.modules.v1"


class SettingModuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    module_type: str = Field(min_length=1, max_length=32)
    payload: dict[str, Any]
    tags: list[str] = Field(default_factory=list)
    source_game_id: UUID | None = None


class SettingModulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    tags: list[str] | None = None


class SettingModuleRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    module_type: str
    payload: dict[str, Any]
    tags: list[str]
    source_game_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ModuleImportFile(BaseModel):
    format_version: str
    modules: list[SettingModuleCreate]


class MergePreviewRequest(BaseModel):
    target_settings: dict[str, Any]
    module_ids: list[UUID]
    adapt: bool = False
    conflict_resolutions: dict[str, str] = Field(default_factory=dict)


class MergePreviewResult(BaseModel):
    merged_settings: dict[str, Any]
    report: dict[str, Any]
    adapted: list[dict[str, Any]]
