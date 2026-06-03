"""B1 结局闭环：剧本打通后一次性生成尾声（epilogue）。

设计要点：
- 复用 Pro 模型写一段收束性的终章正文（自由文本，非 JSON）。
- 独立 timeout + fallback：失败/超时返回空串，调用方据此仅置 game.status，不阻断闭环。
- 只在末幕 required 锚点全完成、且 game.status 尚未 completed 时由 maintenance 触发一次。
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

EPILOGUE_TIMEOUT_SECONDS = 180.0


class EpilogueGenerator:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    async def generate(self, payload: dict[str, Any]) -> str:
        """生成尾声正文；失败或超时返回空串（调用方走 fallback）。"""
        messages = [
            {"role": "system", "content": load_prompt_template("generate_epilogue.md")},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]
        try:
            result = await asyncio.wait_for(
                self.router.use_pro(
                    "epilogue",
                    messages,
                    json_mode=False,
                    max_tokens=4000,
                    reasoning_effort=None,
                ),
                timeout=EPILOGUE_TIMEOUT_SECONDS,
            )
        except (TimeoutError, DeepSeekError) as exc:
            logger.warning("Epilogue generation failed: %s", exc)
            return ""
        except Exception:
            logger.exception("Unexpected epilogue generation failure")
            return ""

        return (result.content or "").strip()
