"""C1 开局序章：建好游戏后一次性生成开场白，写入 turn 0，消除「空白输入框冷启动」。

设计要点：
- 复用 Pro 模型写一段开场正文（自由文本，非 JSON）。
- 独立 timeout + fallback：失败/超时返回空串，调用方据此跳过 turn 0，保持原空开局行为。
- 仅 AI 生成流程触发；序章是 turn 0（display-only，state_delta 为空，不参与 rebuild 重放）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.services.deepseek_client import DeepSeekError
from app.services.model_router import ModelRouter
from app.services.prompt_loader import load_prompt_template

logger = logging.getLogger(__name__)

OPENING_TIMEOUT_SECONDS = 150.0


class OpeningSceneGenerator:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    async def generate(self, payload: dict[str, Any]) -> str:
        """生成开场序章正文；失败或超时返回空串（调用方走 fallback）。"""
        messages = [
            {"role": "system", "content": load_prompt_template("generate_opening.md")},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]
        try:
            result = await asyncio.wait_for(
                self.router.use_pro(
                    "opening",
                    messages,
                    json_mode=False,
                    max_tokens=2500,
                    reasoning_effort=None,
                ),
                timeout=OPENING_TIMEOUT_SECONDS,
            )
        except (TimeoutError, DeepSeekError) as exc:
            logger.warning("Opening scene generation failed: %s", exc)
            return ""
        except Exception:
            logger.exception("Unexpected opening scene generation failure")
            return ""

        return (result.content or "").strip()
