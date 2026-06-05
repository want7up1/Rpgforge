"""新增设定项 AI 补全：用户给标题/名称，按精简剧本大纲补全其余字段。

独立 timeout + fallback：失败/超时/解析失败/结构漂移 → 返回空 dict（前端提示手动填）。
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

SUGGEST_ITEM_TIMEOUT_SECONDS = 40.0

# 各数组的身份字段（用户必填，AI 不覆盖）。
IDENTITY_FIELD: dict[str, str] = {
    "core_characters": "name",
    "act_plan": "title",
    "main_quest_path": "title",
    "core_mechanics": "name",
    "action_style_rules": "name",
    "story_material_library": "title",
}

# 各数组的待补字段 → 中文说明（不含 id / 身份字段 / act_id）。
SUGGEST_FIELDS: dict[str, dict[str, str]] = {
    "core_characters": {
        "role": "定位：protagonist/npc/companion/other",
        "identity": "身份背景",
        "aliases": "别名（字符串数组）",
        "description": "人物描述",
        "appearance": "外貌",
        "desire": "欲望/目标",
        "fear": "恐惧",
        "leverage": "把柄/弱点",
        "relationship_arc": "与主角的关系弧",
        "dramatic_function": "戏剧功能",
        "public_limit": "公开限度",
        "portrait_prompt": "立绘提示词",
        "visibility": "可见性",
    },
    "act_plan": {
        "objective": "本幕目标",
        "dramatic_question": "本幕戏剧问题",
        "must_hit_beats": "必经节点（字符串数组）",
        "allowed_reveals": "允许揭示（字符串数组）",
        "forbidden_reveals": "禁止揭示（字符串数组）",
        "completion_anchors": "完成锚点（对象数组，可留空[]）",
        "transition_to_next_act": "转场到下一幕的条件（对象，可留空{}）",
    },
    "main_quest_path": {
        "objective": "节点目标",
        "player_visible": "玩家是否可见",
        "completion_signal": "完成信号",
        "optional": "是否可选（布尔）",
    },
    "core_mechanics": {
        "rule": "机制规则说明",
        "visibility": "可见性",
    },
    "action_style_rules": {
        "triggers": "触发词（字符串数组）",
        "rule": "行文风格规则",
        "priority": "优先级",
        "enabled": "是否启用（布尔）",
    },
    "story_material_library": {
        "type": "素材类型",
        "keywords": "关键词（字符串数组）",
        "triggers": "触发词（字符串数组）",
        "priority": "优先级",
        "always_on": "是否常驻（布尔）",
        "visibility": "可见性",
        "public_info": "公开信息",
        "gm_secret": "GM 秘密",
        "content": "素材内容",
        "usage": "用法",
        "enabled": "是否启用（布尔）",
    },
}


def build_outline(story_settings: dict[str, Any]) -> str:
    """拼装精简剧本大纲（控制 token）：只取 profile + story_core + worldview 概要。"""
    profile = story_settings.get("game_profile") or {}
    core = story_settings.get("story_core") or {}
    worldview = story_settings.get("worldview") or {}
    parts: list[str] = []
    for key, lbl in (("title", "作品"), ("genre", "类型"), ("tone", "基调")):
        v = str(profile.get(key) or "").strip()
        if v:
            parts.append(f"{lbl}：{v}")
    for key, lbl in (
        ("premise", "前提"),
        ("central_mystery", "核心悬念"),
        ("main_goal", "主目标"),
        ("emotional_arc", "情感弧"),
        ("narrative_style", "叙事风格"),
    ):
        v = str(core.get(key) or "").strip()
        if v:
            parts.append(f"{lbl}：{v}")
    summary = str(worldview.get("summary") or "").strip()
    if summary:
        parts.append(f"世界观：{summary[:120]}")
    return "\n".join(parts)


class ItemSuggester:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    async def suggest(
        self, array_key: str, draft: dict[str, Any], story_settings: dict[str, Any]
    ) -> dict[str, Any]:
        """返回补全字段 dict；任何异常/漂移回退空 dict。"""
        fields = SUGGEST_FIELDS.get(array_key)
        if not fields:
            return {}
        identity_key = IDENTITY_FIELD.get(array_key, "title")
        title = str((draft or {}).get(identity_key) or "")
        messages = [
            {"role": "system", "content": load_prompt_template("suggest_item.md")},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "outline": build_outline(story_settings or {}),
                        "item_type": array_key,
                        "title": title,
                        "fields_to_fill": fields,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            },
        ]
        try:
            result = await asyncio.wait_for(
                self.router.use_flash(
                    "suggest_item", messages, json_mode=True,
                    max_tokens=1500, reasoning_effort=None,
                ),
                timeout=SUGGEST_ITEM_TIMEOUT_SECONDS,
            )
            parsed = parse_json_object(result.content)
        except (TimeoutError, DeepSeekError, ValueError) as exc:
            logger.warning("Item suggest failed, fallback to empty: %s", exc)
            return {}
        except Exception:
            logger.exception("Unexpected item suggest failure")
            return {}
        if not isinstance(parsed, dict):
            return {}
        # 过滤：只保留待补字段，剔除身份字段，防越界/覆盖
        allowed = set(fields.keys())
        return {k: v for k, v in parsed.items() if k in allowed and k != identity_key}
