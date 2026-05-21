from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.models.character import Character
from app.models.game import Game
from app.services.story_settings import story_settings_from_config


def script_export_filename(title: str) -> str:
    safe_title = re.sub(r"[\\/:*?\"<>|\r\n]+", "-", title).strip(" .-")
    return f"RPGForge-{safe_title or 'script'}-剧本.md"


def export_game_script_markdown(game: Game) -> str:
    story_settings = story_settings_from_config(game.config)
    characters = sorted(
        list(game.characters),
        key=lambda character: (_character_role_order(character.role), character.name),
    )

    lines: list[str] = [
        f"# {_text(game.title)}",
        "",
        (
            "> RPGForge story_settings v2 剧本导出。本文只包含故事设定源，"
            "不包含已游玩回合、玩家行动历史、状态结算、"
            "记忆摘要或 AI 思考过程。"
        ),
        "",
        f"- 导出时间：{datetime.now(UTC).isoformat()}",
        f"- 游戏 ID：{game.id}",
        "- 导出范围：故事框架，不含故事进程",
        "",
    ]

    _append_basic_info(lines, game)
    _append_section(lines, "世界观", story_settings.get("worldview"))
    _append_section(lines, "故事核心", story_settings.get("story_core"))
    _append_characters(lines, characters)
    _append_section(lines, "五幕主线", story_settings.get("act_plan"))
    _append_section(lines, "主线任务轨迹", story_settings.get("main_quest_path"))
    _append_section(lines, "核心机制", story_settings.get("core_mechanics"))
    _append_section(lines, "行动风格规则", story_settings.get("action_style_rules"))
    _append_section(lines, "剧本素材库", story_settings.get("story_material_library"))
    _append_section(lines, "[地点]", story_settings.get("home_base"))
    _append_section(lines, "强制规则", story_settings.get("hard_rules"))
    _append_section(lines, "生成参数", story_settings.get("generation_parameters"))

    return "\n".join(lines).rstrip() + "\n"


def _append_basic_info(lines: list[str], game: Game) -> None:
    lines.extend(
        [
            "## 基础信息",
            "",
            f"- 标题：{_text(game.title)}",
            f"- 题材：{_text(game.genre)}",
            f"- 简介：{_text(game.description)}",
            "",
        ]
    )


def _append_section(lines: list[str], title: str, value: Any) -> None:
    lines.extend([f"## {title}", ""])
    if isinstance(value, dict):
        lines.extend(_render_mapping(value) or ["未记录。"])
    elif isinstance(value, list):
        lines.extend(_render_list(value, indent=0) or ["未记录。"])
    else:
        lines.append(_text(value) or "未记录。")
    lines.append("")


def _append_characters(lines: list[str], characters: list[Character]) -> None:
    lines.extend(["## 角色档案", ""])
    if not characters:
        lines.extend(["未记录。", ""])
        return

    for character in characters:
        visibility = "可见" if character.is_visible else "隐藏"
        story_profile = _record(character.story_profile)
        lines.extend(
            [
                f"### {_text(character.name)}",
                "",
                f"- 角色类型：{_text(character.role)}",
                f"- 别名：{_list_inline(character.aliases)}",
                f"- 来源：{_text(character.source)}",
                f"- 身份介绍：{_text(character.identity)}",
                f"- 公开介绍：{_text(character.description)}",
                f"- 外貌描述：{_text(character.appearance)}",
                f"- 可见性：{visibility}",
                "",
            ]
        )
        if story_profile:
            lines.extend(["**编剧字段**", ""])
            lines.extend(_render_mapping(story_profile))
            lines.append("")


def _render_mapping(mapping: dict[str, Any], *, indent: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = "  " * indent
    for key, value in mapping.items():
        label = _label(key)
        if isinstance(value, dict):
            lines.append(f"{prefix}- {label}：")
            nested = _render_mapping(value, indent=indent + 1)
            lines.extend(nested or [f"{prefix}  - 未记录。"])
        elif isinstance(value, list):
            lines.append(f"{prefix}- {label}：")
            lines.extend(_render_list(value, indent=indent + 1))
        else:
            lines.append(f"{prefix}- {label}：{_text(value)}")
    return lines


def _render_list(values: list[Any], *, indent: int) -> list[str]:
    prefix = "  " * indent
    if not values:
        return [f"{prefix}- 未记录。"]

    lines: list[str] = []
    for item in values:
        if isinstance(item, dict):
            title = _first_text(item, ("title", "name", "id", "key")) or "条目"
            lines.append(f"{prefix}- {title}")
            for nested in _render_mapping(item, indent=indent + 1):
                lines.append(nested)
        elif isinstance(item, list):
            lines.append(f"{prefix}-")
            lines.extend(_render_list(item, indent=indent + 1))
        else:
            lines.append(f"{prefix}- {_text(item)}")
    return lines


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _first_text(mapping: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value not in (None, "", [], {}):
            return str(value)
    return ""


def _label(key: str) -> str:
    labels = {
        "title": "标题",
        "description": "简介",
        "summary": "摘要",
        "overview": "概览",
        "tone": "基调",
        "genre": "题材",
        "premise": "前提",
        "player_fantasy": "核心幻想",
        "central_question": "核心悬念",
        "emotional_arc": "情绪弧线",
        "must_preserve": "必须保留内容",
        "must_not_become": "禁止变成内容",
        "main_goal": "主线目标",
        "current_act": "当前幕",
        "narrative_style": "叙事风格",
        "key_npcs": "关键 NPC",
        "key_conflicts": "关键冲突",
        "forbidden_drift": "禁止偏离点",
        "forbidden_reveals": "禁止提前揭示",
        "guardrails": "护栏",
        "act_plan": "幕计划",
        "mechanics_contract": "机制契约",
        "user_brief": "用户创作简报",
        "story_background": "故事背景",
        "core_premise": "核心设定",
        "must_include": "必须出现",
        "forbidden_content": "禁止点",
        "playstyle_preferences": "玩法偏好",
        "tone_preferences": "风格偏好",
        "raw_user_input": "原始输入",
        "truth_map": "真相地图",
        "truth": "真相",
        "public_mask": "公开表象",
        "reveal_condition": "揭露条件",
        "clue_ladder": "线索阶梯",
        "clue": "线索",
        "points_to": "指向",
        "do_not_reveal": "不能揭露",
        "pressure_clock": "压力时钟",
        "tick_condition": "推进条件",
        "consequence": "后果",
        "dramatic_question": "戏剧问题",
        "pressure": "压力",
        "allowed_reveals": "允许揭露",
        "relationship_turn": "关系变化",
        "escalation_limit": "升级上限",
        "dramatic_function": "戏剧功能",
        "desire": "欲望",
        "fear": "恐惧",
        "leverage": "可被牵动点",
        "relationship_arc": "关系弧线",
        "public_limit": "公开边界",
    }
    return labels.get(key, key.replace("_", " "))


def _text(value: Any) -> str:
    if value is None:
        return "未记录"
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else "未记录"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def _list_inline(values: list[str] | None) -> str:
    cleaned = [value.strip() for value in values or [] if value and value.strip()]
    return "、".join(cleaned) if cleaned else "未记录"


def _priority_order(priority: str | None) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(priority or "", 4)


def _character_role_order(role: str | None) -> int:
    return {"protagonist": 0, "companion": 1, "npc": 2, "other": 3}.get(role or "", 4)
