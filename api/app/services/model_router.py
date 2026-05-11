from collections.abc import AsyncIterator
from typing import Literal

from app.config import Settings, settings
from app.services.deepseek_client import (
    ChatCompletionResult,
    ChatCompletionStreamChunk,
    DeepSeekClient,
)
from app.services.runtime_settings import (
    EffectiveDeepSeekSettings,
    ModelSlot,
    get_effective_deepseek_settings,
)


class ModelRouter:
    def __init__(
        self,
        client: DeepSeekClient | None = None,
        app_settings: Settings = settings,
    ) -> None:
        self.settings = app_settings
        self.client = client or DeepSeekClient(app_settings)

    async def use_flash(
        self,
        task_type: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = True,
        max_tokens: int | None = 4096,
    ) -> ChatCompletionResult:
        effective_settings = get_effective_deepseek_settings(self.settings)
        return await self.client.chat_completion(
            model=self._select_model(effective_settings, task_type, "flash"),
            messages=messages,
            json_mode=json_mode,
            thinking="enabled",
            reasoning_effort="high",
            max_tokens=max_tokens,
        )

    async def use_flash_stream(
        self,
        task_type: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = True,
        max_tokens: int | None = 4096,
    ) -> AsyncIterator[ChatCompletionStreamChunk]:
        effective_settings = get_effective_deepseek_settings(self.settings)
        async for chunk in self.client.chat_completion_stream(
            model=self._select_model(effective_settings, task_type, "flash"),
            messages=messages,
            json_mode=json_mode,
            thinking="enabled",
            reasoning_effort="high",
            max_tokens=max_tokens,
        ):
            yield chunk

    async def use_pro(
        self,
        task_type: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = True,
        max_tokens: int | None = 12000,
        reasoning_effort: Literal["high", "max"] | None = "high",
    ) -> ChatCompletionResult:
        effective_settings = get_effective_deepseek_settings(self.settings)
        return await self.client.chat_completion(
            model=self._select_model(effective_settings, task_type, "pro"),
            messages=messages,
            json_mode=json_mode,
            thinking="enabled",
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
        )

    async def use_pro_stream(
        self,
        task_type: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = True,
        max_tokens: int | None = 12000,
        reasoning_effort: Literal["high", "max"] | None = "high",
    ) -> AsyncIterator[ChatCompletionStreamChunk]:
        effective_settings = get_effective_deepseek_settings(self.settings)
        async for chunk in self.client.chat_completion_stream(
            model=self._select_model(effective_settings, task_type, "pro"),
            messages=messages,
            json_mode=json_mode,
            thinking="enabled",
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
        ):
            yield chunk

    @staticmethod
    def _select_model(
        effective_settings: EffectiveDeepSeekSettings,
        task_type: str,
        fallback_slot: ModelSlot,
    ) -> str:
        slot = effective_settings.task_model_routes.get(task_type, fallback_slot)
        return (
            effective_settings.pro_model
            if slot == "pro"
            else effective_settings.flash_model
        )
