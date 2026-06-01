import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.config import Settings, settings
from app.services.runtime_settings import get_effective_deepseek_settings


class DeepSeekError(RuntimeError):
    pass


class DeepSeekConfigurationError(DeepSeekError):
    pass


class DeepSeekAPIError(DeepSeekError):
    pass


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    model: str
    raw: dict[str, Any]
    reasoning_content: str = ""


@dataclass(frozen=True)
class ChatCompletionStreamChunk:
    content_delta: str = ""
    reasoning_delta: str = ""
    model: str | None = None
    # include_usage 开启后，末尾 usage chunk 带完整 usage（含 prefix cache 命中）。
    usage: dict[str, Any] | None = None


class DeepSeekClient:
    def __init__(self, app_settings: Settings = settings) -> None:
        self.settings = app_settings

    async def chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool = False,
        thinking: Literal["enabled", "disabled"] = "disabled",
        reasoning_effort: Literal["high", "max"] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> ChatCompletionResult:
        effective_settings = self._effective_settings_or_raise()
        payload = self._build_payload(
            model=model,
            messages=messages,
            stream=False,
            json_mode=json_mode,
            thinking=thinking,
            reasoning_effort=reasoning_effort,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        endpoint = self._chat_completions_endpoint(effective_settings.base_url)

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {effective_settings.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:1000]
            raise DeepSeekAPIError(
                f"DeepSeek API 请求失败：HTTP {exc.response.status_code} {body}"
            ) from exc
        except httpx.HTTPError as exc:
            raise DeepSeekAPIError(f"DeepSeek API 网络请求失败：{exc}") from exc

        data = response.json()
        try:
            message = data["choices"][0]["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekAPIError("DeepSeek API 返回结构不符合预期。") from exc

        if not isinstance(content, str) or not content.strip():
            raise DeepSeekAPIError("DeepSeek API 返回了空内容。")

        return ChatCompletionResult(
            content=content,
            model=str(data.get("model") or model),
            raw=data,
            reasoning_content=str(message.get("reasoning_content") or ""),
        )

    async def chat_completion_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        json_mode: bool = False,
        thinking: Literal["enabled", "disabled"] = "enabled",
        reasoning_effort: Literal["high", "max"] | None = "high",
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[ChatCompletionStreamChunk]:
        effective_settings = self._effective_settings_or_raise()
        payload = self._build_payload(
            model=model,
            messages=messages,
            stream=True,
            json_mode=json_mode,
            thinking=thinking,
            reasoning_effort=reasoning_effort,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        endpoint = self._chat_completions_endpoint(effective_settings.base_url)

        timeout = httpx.Timeout(connect=20, read=300, write=20, pool=20)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {effective_settings.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                ) as response:
                    if response.is_error:
                        body = (await response.aread()).decode(
                            "utf-8",
                            errors="replace",
                        )[:1000]
                        raise DeepSeekAPIError(
                            f"DeepSeek API 请求失败：HTTP {response.status_code} {body}"
                        )
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data_line = line.removeprefix("data:").strip()
                        if not data_line or data_line == "[DONE]":
                            continue
                        try:
                            event = json.loads(data_line)
                        except json.JSONDecodeError as exc:
                            raise DeepSeekAPIError("DeepSeek API 流式返回结构不符合预期。") from exc
                        usage = event.get("usage")
                        usage = usage if isinstance(usage, dict) else None
                        choices = event.get("choices") or []
                        if not choices:
                            # include_usage 的末尾 chunk：choices 为空，只带 usage。
                            if usage is not None:
                                yield ChatCompletionStreamChunk(
                                    model=str(event.get("model") or model),
                                    usage=usage,
                                )
                            continue
                        first = choices[0] if isinstance(choices[0], dict) else {}
                        delta = first.get("delta") or {}
                        yield ChatCompletionStreamChunk(
                            content_delta=str(delta.get("content") or ""),
                            reasoning_delta=str(delta.get("reasoning_content") or ""),
                            model=str(event.get("model") or model),
                            usage=usage,
                        )
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:1000]
            raise DeepSeekAPIError(
                f"DeepSeek API 请求失败：HTTP {exc.response.status_code} {body}"
            ) from exc
        except httpx.HTTPError as exc:
            raise DeepSeekAPIError(f"DeepSeek API 网络请求失败：{exc}") from exc

    def _effective_settings_or_raise(self):
        effective_settings = get_effective_deepseek_settings(self.settings)
        if not effective_settings.api_key:
            raise DeepSeekConfigurationError(
                "DeepSeek API 未配置：请在设置页保存 API Key，或在 .env 中设置 DEEPSEEK_API_KEY。"
            )
        return effective_settings

    @staticmethod
    def _build_payload(
        *,
        model: str,
        messages: list[dict[str, str]],
        stream: bool,
        json_mode: bool,
        thinking: Literal["enabled", "disabled"],
        reasoning_effort: Literal["high", "max"] | None,
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "thinking": {"type": thinking},
        }
        if stream:
            # 让流式也返回 usage（含 prefix cache 命中），用于 telemetry 观测。
            payload["stream_options"] = {"include_usage": True}
        if thinking == "disabled":
            payload["temperature"] = temperature
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if reasoning_effort:
            payload["reasoning_effort"] = reasoning_effort
        if max_tokens:
            payload["max_tokens"] = max_tokens
        return payload

    @staticmethod
    def _chat_completions_endpoint(base_url: str) -> str:
        normalized = (base_url or "https://api.deepseek.com").rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized
        return f"{normalized}/chat/completions"
