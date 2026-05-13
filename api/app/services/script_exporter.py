from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.models.character import Character
from app.models.game import Game, GameConfig
from app.models.lore import LoreEntry
from app.models.mode import Mode


def script_export_filename(title: str) -> str:
    safe_title = re.sub(r"[\\/:*?\"<>|\r\n]+", "-", title).strip(" .-")
    return f"RPGForge-{safe_title or 'script'}-剧本.md"


def export_game_script_markdown(game: Game) -> str:
    config = game.config
    worldview = _record(config.worldview if config else {})
    script_outline = _record(config.script_outline if config else {})
    lore_entries = sorted(
        list(game.lore_entries),
        key=lambda entry: (
            not bool(entry.is_active),
            _priority_order(entry.priority),
            entry.title,
        ),
    )
    modes = sorted(
        list(game.modes),
        key=lambda mode: (not mode.enabled, _priority_order(mode.priority), mode.name),
    )
    characters = sorted(
        list(game.characters),
        key=lambda character: (_character_role_order(character.role), character.name),
    )

    lines: list[str] = [
        f"# {_text(game.title)}",
        "",
        (
            "> RPGForge 剧本导出。本文只包含故事框架、世界设定、角色档案、"
            "世界资料和模式规则，不包含已游玩回合、玩家行动历史、状态结算、"
            "记忆摘要或 AI 思考过程。"
        ),
        "",
        f"- 导出时间：{datetime.now(UTC).isoformat()}",
        f"- 游戏 ID：{game.id}",
        "- 导出范围：故事框架，不含故事进程",
        "",
    ]

    _append_basic_info(lines, game)
    _append_worldview(lines, worldview)
    _append_story_blueprint(lines, script_outline)
    _append_script_contracts(lines, script_outline)
    _append_act_structure(lines, script_outline)
    _append_characters(lines, characters)
    _append_lore(lines, lore_entries)
    _append_modes(lines, modes)
    _append_advanced(lines, config)

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


def _append_worldview(lines: list[str], worldview: dict[str, Any]) -> None:
    lines.extend(["## 世界观", ""])
    if not worldview:
        lines.extend(["未记录。", ""])
        return
    lines.extend(_render_mapping(worldview))
    lines.append("")


def _append_story_blueprint(lines: list[str], script_outline: dict[str, Any]) -> None:
    user_brief = _record(script_outline.get("user_brief"))
    truth_map = script_outline.get("truth_map")
    clue_ladder = script_outline.get("clue_ladder")
    pressure_clock = script_outline.get("pressure_clock")
    if not user_brief and not truth_map and not clue_ladder and not pressure_clock:
        return

    lines.extend(["## 创作简报与编剧蓝图", ""])
    if user_brief:
        lines.extend(["### 用户创作简报", ""])
        lines.extend(_render_mapping(user_brief))
        lines.append("")
    if truth_map:
        lines.extend(["### 真相地图", ""])
        lines.extend(_render_list(_as_list(truth_map), indent=0))
        lines.append("")
    if clue_ladder:
        lines.extend(["### 线索阶梯", ""])
        lines.extend(_render_list(_as_list(clue_ladder), indent=0))
        lines.append("")
    if pressure_clock:
        lines.extend(["### 压力时钟", ""])
        lines.extend(_render_list(_as_list(pressure_clock), indent=0))
        lines.append("")


def _append_script_contracts(lines: list[str], script_outline: dict[str, Any]) -> None:
    lines.extend(["## 核心设定与剧本契约", ""])
    contracts = [
        ("campaign_contract", "战役契约"),
        ("director_contract", "剧情导演契约"),
        ("story_contract", "叙事契约"),
    ]
    found = False
    for key, label in contracts:
        contract = _record(script_outline.get(key))
        lines.extend([f"### {label}", ""])
        if contract:
            found = True
            lines.extend(_render_mapping(contract))
        else:
            lines.append("未记录。")
        lines.append("")

    extras = {
        key: value
        for key, value in script_outline.items()
        if key not in {
            "acts",
            "campaign_contract",
            "director_contract",
            "story_contract",
            "user_brief",
            "truth_map",
            "clue_ladder",
            "pressure_clock",
            "_character_profiles",
        }
    }
    if extras:
        found = True
        lines.extend(["### 其他剧本设定", ""])
        lines.extend(_render_mapping(extras))
        lines.append("")

    if not found:
        lines.extend(["当前没有结构化剧本契约。", ""])


def _append_act_structure(lines: list[str], script_outline: dict[str, Any]) -> None:
    lines.extend(["## 幕结构与主线框架", ""])
    acts = script_outline.get("acts")
    if not isinstance(acts, list) or not acts:
        lines.extend(["未记录。", ""])
        return

    for index, act in enumerate(acts, start=1):
        act_record = _record(act)
        title = _first_text(act_record, ("title", "name", "id", "key")) or f"第 {index} 幕"
        lines.extend([f"### {title}", ""])
        if act_record:
            lines.extend(_render_mapping(act_record))
        else:
            lines.append(_text(act))
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


def _append_lore(lines: list[str], entries: list[LoreEntry]) -> None:
    active_entries = [entry for entry in entries if entry.is_active]
    archived_entries = [entry for entry in entries if not entry.is_active]

    lines.extend(["## 世界资料 / 世界书", ""])
    if not active_entries:
        lines.extend(["暂无启用世界资料。", ""])
    for entry in active_entries:
        _append_lore_entry(lines, entry)

    if archived_entries:
        lines.extend(["### 已归档世界资料（不进入当前 GM 上下文）", ""])
        for entry in archived_entries:
            lines.extend([f"- {_text(entry.title)}（{_text(entry.type)}）"])
        lines.append("")


def _append_lore_entry(lines: list[str], entry: LoreEntry) -> None:
    lines.extend(
        [
            f"### {_text(entry.title)}",
            "",
            f"- 类型：{_text(entry.type)}",
            f"- 优先级：{_text(entry.priority)}",
            f"- 可见性：{_text(entry.visibility)}",
            f"- 常驻注入：{'是' if entry.always_on else '否'}",
            f"- 关键词：{_list_inline(entry.keywords)}",
            f"- 触发词：{_list_inline(entry.trigger_words)}",
            "",
            "**公开信息**",
            "",
            _text(entry.public_info),
            "",
            "**GM 秘密**",
            "",
            _text(entry.gm_secret),
            "",
            "**完整内容**",
            "",
            _text(entry.content),
            "",
            "**使用说明**",
            "",
            _text(entry.usage_note),
            "",
        ]
    )


def _append_modes(lines: list[str], modes: list[Mode]) -> None:
    lines.extend(["## 模式注入 / 机制规则", ""])
    if not modes:
        lines.extend(["未记录。", ""])
        return

    for mode in modes:
        lines.extend(
            [
                f"### {_text(mode.name)}",
                "",
                f"- 状态：{'启用' if mode.enabled else '停用'}",
                f"- 优先级：{_text(mode.priority)}",
                f"- 触发词：{_list_inline(mode.triggers)}",
                "",
                "**注入内容**",
                "",
                _text(mode.injection),
                "",
            ]
        )


def _append_advanced(lines: list[str], config: GameConfig | None) -> None:
    lines.extend(["## 附录：高级 GM 指令", ""])
    if not config:
        lines.extend(["未记录。", ""])
        return

    lines.extend(
        [
            "### System Prompt",
            "",
            _text(config.system_prompt),
            "",
            "### 生成备注",
            "",
            _text(config.generation_notes),
            "",
        ]
    )


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
