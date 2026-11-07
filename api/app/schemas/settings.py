from typing import Literal

from pydantic import BaseModel, Field

ModelSlot = Literal["flash", "pro"]


class DeepSeekSettingsRead(BaseModel):
    api_key_configured: bool
    api_key_masked: str | None
    api_key_source: Literal["database", "environment", "missing"]
    base_url: str
    flash_model: str
    pro_model: str
    task_model_routes: dict[str, ModelSlot]
    settings_protected: bool = False


class DeepSeekModelDiscoveryRequest(BaseModel):
    base_url: str | None = Field(default=None, max_length=512)
    api_key: str | None = Field(default=None, max_length=4096)


class DeepSeekModelChoice(BaseModel):
    id: str


class DeepSeekModelDiscoveryRead(BaseModel):
    models: list[DeepSeekModelChoice]
    flash_model: str | None
    pro_model: str | None


class DeepSeekSettingsUpdate(BaseModel):
    api_key: str | None = Field(default=None, max_length=4096)
    clear_api_key: bool = False
    base_url: str | None = Field(default=None, max_length=512)
    flash_model: str | None = Field(default=None, min_length=1, max_length=128)
    pro_model: str | None = Field(default=None, min_length=1, max_length=128)
    task_model_routes: dict[str, ModelSlot] | None = None
