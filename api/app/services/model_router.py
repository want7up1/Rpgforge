from collections.abc import AsyncIterator
from time import monotonic
from typing import Literal

from app.config import Settings, settings
from app.services.agent_traces import extract_usage, record_trace
from app.services.deepseek_client import (
    ChatCompletionResult,
    ChatCompletionStreamChunk,
    DeepSeekClient,
    DeepSeekError,
)
from app.services.runtime_settings import (
    EffectiveDeepSeekSettings,
    ModelSlot,
    get_effective_deepseek_settings,
)


class ModelRouter:
    """所有 LLM 调用的统一入口。

    包装了 trace 钩子：每次调用结束（成功/失败）都同步写一条 agent_traces 记录。
    Trace 写入失败被吞掉，不影响主流程；详见 `agent_traces.record_trace`。
    """

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
        reasoning_effort: Literal["high", "max"] | None = "high",
        respect_route: bool = True,
    ) -> ChatCompletionResult:
        effective_settings = get_effective_deepseek_settings(self.settings)
        model = self._select_model(
            effective_settings,
            task_type,
            "flash",
            respect_route=respect_route,
        )
        return await self._call_chat(
            task_type=task_type,
            model=model,
            messages=messages,
            json_mode=json_mode,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
            stream=False,
            extras={
                "slot": "flash",
                "respect_route": respect_route,
                "max_tokens": max_tokens,
                "reasoning_effort": reasoning_effort,
            },
        )

    async def use_flash_stream(
        self,
        task_type: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = True,
        max_tokens: int | None = 4096,
        reasoning_effort: Literal["high", "max"] | None = "high",
        respect_route: bool = True,
    ) -> AsyncIterator[ChatCompletionStreamChunk]:
        effective_settings = get_effective_deepseek_settings(self.settings)
        model = self._select_model(
            effective_settings,
            task_type,
            "flash",
            respect_route=respect_route,
        )
        async for chunk in self._stream_chat(
            task_type=task_type,
            model=model,
            messages=messages,
            json_mode=json_mode,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
            extras={
                "slot": "flash",
                "stream": True,
                "respect_route": respect_route,
                "max_tokens": max_tokens,
                "reasoning_effort": reasoning_effort,
            },
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
        model = self._select_model(effective_settings, task_type, "pro")
        return await self._call_chat(
            task_type=task_type,
            model=model,
            messages=messages,
            json_mode=json_mode,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
            stream=False,
            extras={
                "slot": "pro",
                "max_tokens": max_tokens,
                "reasoning_effort": reasoning_effort,
            },
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
        model = self._select_model(effective_settings, task_type, "pro")
        async for chunk in self._stream_chat(
            task_type=task_type,
            model=model,
            messages=messages,
            json_mode=json_mode,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
            extras={
                "slot": "pro",
                "stream": True,
                "max_tokens": max_tokens,
                "reasoning_effort": reasoning_effort,
            },
        ):
            yield chunk

    async def _call_chat(
        self,
        *,
        task_type: str,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        reasoning_effort: Literal["high", "max"] | None,
        max_tokens: int | None,
        stream: bool,
        extras: dict,
    ) -> ChatCompletionResult:
        start = monotonic()
        thinking = self._thinking_mode(reasoning_effort)
        trace_extras = {**extras, "thinking": thinking}
        try:
            result = await self.client.chat_completion(
                model=model,
                messages=messages,
                json_mode=json_mode,
                thinking=thinking,
                reasoning_effort=reasoning_effort,
                max_tokens=max_tokens,
            )
        except DeepSeekError as exc:
            record_trace(
                task_type=task_type,
                model=model,
                prompt_messages=messages,
                output_text=None,
                reasoning_text=None,
                latency_ms=int((monotonic() - start) * 1000),
                status="error",
                error_message=str(exc),
                extras=trace_extras,
            )
            raise
        tokens_in, tokens_out, tokens_reason = extract_usage(result.raw)
        record_trace(
            task_type=task_type,
            model=result.model,
            prompt_messages=messages,
            output_text=result.content,
            reasoning_text=result.reasoning_content or None,
            latency_ms=int((monotonic() - start) * 1000),
            status="success",
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            tokens_reasoning=tokens_reason,
            extras=trace_extras,
        )
        return result

    async def _stream_chat(
        self,
        *,
        task_type: str,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool,
        reasoning_effort: Literal["high", "max"] | None,
        max_tokens: int | None,
        extras: dict,
    ) -> AsyncIterator[ChatCompletionStreamChunk]:
        # 流式：在 generator 内部累积 content / reasoning，最后落 trace。
        # 注意 stream 接口 DeepSeek 不返回 usage（除非显式 include_usage），
        # 所以 tokens_* 字段会是 None；可以接受。
        start = monotonic()
        thinking = self._thinking_mode(reasoning_effort)
        trace_extras = {**extras, "thinking": thinking}
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        observed_model: str | None = None
        error: Exception | None = None
        try:
            async for chunk in self.client.chat_completion_stream(
                model=model,
                messages=messages,
                json_mode=json_mode,
                thinking=thinking,
                reasoning_effort=reasoning_effort,
                max_tokens=max_tokens,
            ):
                if chunk.model:
                    observed_model = chunk.model
                if chunk.content_delta:
                    content_parts.append(chunk.content_delta)
                if chunk.reasoning_delta:
                    reasoning_parts.append(chunk.reasoning_delta)
                yield chunk
        except DeepSeekError as exc:
            error = exc
            raise
        finally:
            content = "".join(content_parts)
            reasoning = "".join(reasoning_parts)
            if error is not None:
                status = "error"
                err_msg: str | None = str(error)
            elif not content.strip():
                status = "empty_content"
                err_msg = "DeepSeek 流式返回空内容"
            else:
                status = "success"
                err_msg = None
            record_trace(
                task_type=task_type,
                model=observed_model or model,
                prompt_messages=messages,
                output_text=content or None,
                reasoning_text=reasoning or None,
                latency_ms=int((monotonic() - start) * 1000),
                status=status,
                error_message=err_msg,
                extras=trace_extras,
            )

    @staticmethod
    def _thinking_mode(
        reasoning_effort: Literal["high", "max"] | None,
    ) -> Literal["enabled", "disabled"]:
        return "disabled" if reasoning_effort is None else "enabled"

    @staticmethod
    def _select_model(
        effective_settings: EffectiveDeepSeekSettings,
        task_type: str,
        fallback_slot: ModelSlot,
        *,
        respect_route: bool = True,
    ) -> str:
        slot = (
            effective_settings.task_model_routes.get(task_type, fallback_slot)
            if respect_route
            else fallback_slot
        )
        return (
            effective_settings.pro_model
            if slot == "pro"
            else effective_settings.flash_model
        )
