"""Read-only OpenAI-compatible model discovery without chat calls or credential echoes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.services.runtime_settings import EffectiveDeepSeekSettings

DEFAULT_BASE_URL = "https://api.deepseek.com"
MODEL_DISCOVERY_TIMEOUT_SECONDS = 12.0
MAX_MODEL_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_MODEL_ID_LENGTH = 128
_FAST_MODEL = re.compile(
    r"(?:^|[/_.-])(?:flash|mini|nano|lite|haiku|fast|small|instant)(?:$|[/_.-])", re.I
)
_PRO_MODEL = re.compile(
    r"(?:^|[/_.-])(?:pro|reasoner|reasoning|thinking|opus|sonnet|large|plus)(?:$|[/_.-])", re.I
)
_NON_CHAT_ID = re.compile(
    r"(?:^|[/_-])(?:embeddings?|embed|rerank(?:er)?|tts|whisper|transcrib(?:e|ing|er)|"
    r"text-to-speech|text-to-image|image-generation|video-generation)(?:$|[/_.-])"
    r"|(?:^|/)(?:dall-e|gpt-image|stable-diffusion|flux[-/]|imagen[-/])",
    re.IGNORECASE,
)


class ModelDiscoveryError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class DiscoveredModels:
    models: list[str]
    flash_model: str | None
    pro_model: str | None


def normalize_model_base_url(value: str | None) -> str:
    cleaned = (value or "").strip() or DEFAULT_BASE_URL
    try:
        parsed = urlsplit(cleaned)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or "?" in cleaned
            or "#" in cleaned
            or any(ord(char) < 32 or ord(char) == 127 for char in cleaned)
            or "\\" in cleaned
        ):
            raise ValueError
        # Force validation of invalid/non-numeric ports before creating a request.
        _ = parsed.port
        normalized = re.sub(r"/chat/completions/?$", "", cleaned, flags=re.IGNORECASE)
        url = httpx.URL(normalized.rstrip("/"))
        if not url.host or url.scheme not in {"http", "https"}:
            raise ValueError
        return str(url).rstrip("/")
    except (ValueError, httpx.InvalidURL):
        raise ModelDiscoveryError(
            400, "Base URL 必须是有效的 HTTP(S) 地址，不能包含账号、密码、查询参数或片段。"
        ) from None


def model_origin(value: str | None) -> tuple[str, bytes, int]:
    url = httpx.URL(normalize_model_base_url(value))
    return url.scheme, url.raw_host.lower(), url.port or (443 if url.scheme == "https" else 80)


def resolve_model_credentials(
    current: EffectiveDeepSeekSettings, *, base_url: str | None, api_key: str | None,
) -> tuple[str, str]:
    target = normalize_model_base_url(base_url if (base_url or "").strip() else current.base_url)
    supplied_key = (api_key or "").strip()
    key = supplied_key or current.api_key.strip()
    if not key:
        raise ModelDiscoveryError(400, "请先输入 API Key，或保存一个可用的 API Key。")
    if not key.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in key):
        raise ModelDiscoveryError(400, "API Key 格式无效，不能包含换行或控制字符。")
    if not supplied_key and model_origin(target) != model_origin(current.base_url):
        raise ModelDiscoveryError(400, "服务地址已更换，请重新输入 API Key 后再探测模型。")
    return target, key


def _chat_capable(record: dict[str, Any], model_id: str) -> bool:
    modalities = record.get("output_modalities")
    if isinstance(modalities, list) and modalities:
        if "text" not in {str(item).lower() for item in modalities}:
            return False
    capabilities = record.get("capabilities")
    if isinstance(capabilities, dict) and any(
        capabilities.get(key) is True for key in ("chat", "chat_completion", "chat_completions")
    ):
        return True
    kind = str(record.get("type") or record.get("task") or "").lower().replace("-", "_")
    if kind in {
        "embedding", "embeddings", "rerank", "reranker", "audio", "transcription",
        "speech", "tts", "image", "image_generation", "video", "video_generation",
    }:
        return False
    return _NON_CHAT_ID.search(model_id) is None


def _model_ids(payload: Any, api_key: str) -> list[str]:
    if not isinstance(payload, dict):
        raise ModelDiscoveryError(502, "模型列表响应格式不正确，请检查服务是否兼容。")
    entries = payload.get("data", payload.get("models"))
    if not isinstance(entries, list):
        raise ModelDiscoveryError(502, "模型列表响应格式不正确，请检查服务是否兼容。")
    ids: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        record = entry if isinstance(entry, dict) else {"id": entry}
        value = record.get("id")
        if not isinstance(value, str):
            continue
        model_id = value.strip()
        if (
            not model_id or model_id in seen or len(model_id) > MAX_MODEL_ID_LENGTH
            or any(ord(char) < 32 or ord(char) == 127 for char in model_id)
            or model_id == api_key or (len(api_key) >= 8 and api_key in model_id)
            or not _chat_capable(record, model_id)
        ):
            continue
        seen.add(model_id)
        ids.append(model_id)
    if not ids:
        raise ModelDiscoveryError(400, "未发现可用于对话的模型，请检查服务地址和当前 Key 的权限。")
    return ids


def recommend_model_slots(
    ids: list[str], *, current_flash: str, current_pro: str,
) -> tuple[str | None, str | None]:
    if not ids:
        return None, None
    if len(ids) == 1:
        return ids[0], ids[0]

    def fast_score(model: str) -> int:
        return int(_FAST_MODEL.search(model) is not None)

    def pro_score(model: str) -> int:
        if _PRO_MODEL.search(model):
            return 2
        return 0 if fast_score(model) else 1

    flash = current_flash if current_flash in ids else max(ids, key=fast_score)
    pro = current_pro if current_pro in ids else max(ids, key=pro_score)
    # DeepSeek's older standard chat model is the lightweight counterpart to reasoner.
    if current_flash not in ids and not fast_score(flash) and "deepseek-chat" in ids:
        flash = "deepseek-chat"
    if flash == pro and current_flash not in ids and _PRO_MODEL.search(pro):
        flash = next((model for model in ids if model != pro), flash)
    return flash, pro


async def discover_models(
    current: EffectiveDeepSeekSettings, *, base_url: str | None = None,
    api_key: str | None = None, transport: httpx.AsyncBaseTransport | None = None,
) -> DiscoveredModels:
    base, key = resolve_model_credentials(current, base_url=base_url, api_key=api_key)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(MODEL_DISCOVERY_TIMEOUT_SECONDS, connect=5.0),
            follow_redirects=False,
        ) as client:
            async with client.stream(
                "GET", f"{base}/models", headers={"Authorization": f"Bearer {key}"}
            ) as response:
                _check_response_status(response.status_code)
                content_length = response.headers.get("content-length", "")
                if content_length.isdecimal() and int(content_length) > MAX_MODEL_RESPONSE_BYTES:
                    raise ModelDiscoveryError(502, "模型列表响应过大，请更换服务地址后重试。")
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                    if len(body) + len(chunk) > MAX_MODEL_RESPONSE_BYTES:
                        raise ModelDiscoveryError(502, "模型列表响应过大，请更换服务地址后重试。")
                    body.extend(chunk)
    except httpx.TimeoutException:
        raise ModelDiscoveryError(504, "读取模型列表超时，请稍后重试。") from None
    except httpx.RequestError:
        raise ModelDiscoveryError(502, "无法连接模型服务，请检查 Base URL 和网络。") from None

    try:
        payload = json.loads(body)
    except ValueError:
        raise ModelDiscoveryError(502, "模型列表不是有效 JSON，请检查服务是否兼容。") from None
    ids = _model_ids(payload, key)
    flash, pro = recommend_model_slots(
        ids, current_flash=current.flash_model, current_pro=current.pro_model
    )
    return DiscoveredModels(ids, flash, pro)


def _check_response_status(status_code: int) -> None:
    if status_code in {401, 403, 404}:
        messages = {
            401: "API Key 无效或已过期，请重新输入。",
            403: "当前 API Key 无权读取模型列表。",
            404: "该服务未提供模型列表接口，请检查 Base URL。",
        }
        raise ModelDiscoveryError(status_code, messages[status_code])
    if 300 <= status_code < 400:
        raise ModelDiscoveryError(502, "模型列表接口发生重定向，请直接填写最终服务地址。")
    if status_code == 429:
        raise ModelDiscoveryError(429, "模型服务请求过于频繁，请稍后重试。")
    if not 200 <= status_code < 300:
        raise ModelDiscoveryError(502, "模型服务暂时不可用，请稍后重试。")
