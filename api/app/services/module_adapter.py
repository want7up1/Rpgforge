"""AI 本地优化：把模块 payload 改写得贴合目标剧本。

独立 timeout + fallback：失败/超时/解析失败/结构漂移 → 返回原 payload（退化为直接并入）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.services.deepseek_client import DeepSeekError
from app.services.json_utils import parse_json_object
from app.services.model_router import ModelRouter
from app.services.prompt_loader import load_prompt_template

logger = logging.getLogger(__name__)

MODULE_ADAPT_TIMEOUT_SECONDS = 120.0


class ModuleAdapter:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    async def adapt(self, payload: dict[str, Any], target_context: dict[str, Any]) -> dict[str, Any]:
        """返回改写后的 payload；任何异常/结构漂移回退原 payload。"""
        if not isinstance(payload, dict) or not payload:
            return payload
        messages = [
            {"role": "system", "content": load_prompt_template("adapt_module.md")},
            {
                "role": "user",
                "content": json.dumps(
                    {"module_payload": payload, "target_context": target_context},
                    ensure_ascii=False, default=str,
                ),
            },
        ]
        try:
            result = await asyncio.wait_for(
                self.router.use_pro("module_adapt", messages, json_mode=True,
                                    max_tokens=4000, reasoning_effort=None),
                timeout=MODULE_ADAPT_TIMEOUT_SECONDS,
            )
            adapted = parse_json_object(result.content)
        except (TimeoutError, DeepSeekError, ValueError) as exc:
            logger.warning("Module adapt failed, fallback to original: %s", exc)
            return payload
        except Exception:
            logger.exception("Unexpected module adapt failure")
            return payload
        # 结构护栏：顶层键集合必须一致，否则回退
        if not isinstance(adapted, dict) or set(adapted.keys()) != set(payload.keys()):
            logger.warning("Module adapt shape drift, fallback to original")
            return payload
        return adapted
