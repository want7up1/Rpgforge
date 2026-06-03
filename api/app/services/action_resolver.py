"""A1 轻量判定层 + A2 数值反哺。

StoryDirector 为有不确定性的玩家行动标注 action_check（难度 + 相关属性/技能/社交对象），
本模块据「等级 + 技能 + 属性 + 关系」算修正值，roll d20 vs 难度 DC，产出 outcome。
outcome 由 gameplay 作为**硬约束**注入 gm_instruction，GM 只负责把既定结果叙事化。

设计要点：
- 让等级/技能/属性/关系真正进入判定（A2：此前它们是只写不读的装饰）。
- 失败/部分成功是真实可能的结果——没有失败就没有博弈。
- rng 可注入（测试用固定种子），默认用模块级 Random。
"""

from __future__ import annotations

import random
from typing import Any

# 难度 → 目标值 DC（roll d20 + 修正 ≥ DC 为成功）。
DIFFICULTY_DC: dict[str, int] = {
    "trivial": 5,
    "easy": 8,
    "normal": 12,
    "medium": 12,
    "hard": 16,
    "extreme": 20,
    "简单": 8,
    "普通": 12,
    "困难": 16,
    "极难": 20,
}

OUTCOME_LABELS: dict[str, str] = {
    "critical": "大成功",
    "success": "成功",
    "partial": "部分成功",
    "failure": "失败",
}

_DEFAULT_RNG = random.Random()


def resolve_action_check(
    check: Any,
    state_v2: dict[str, Any] | None,
    *,
    rng: random.Random | None = None,
) -> dict[str, Any] | None:
    """解析一次行动判定；无有效 check（无难度）时返回 None（纯对话/叙述无需判定）。"""
    if not isinstance(check, dict):
        return None
    difficulty = _text(check.get("difficulty")).lower()
    raw_difficulty = _text(check.get("difficulty"))
    if not raw_difficulty:
        return None
    dc = DIFFICULTY_DC.get(difficulty) or DIFFICULTY_DC.get(raw_difficulty)
    if dc is None:
        # 难度不可识别时按 normal 处理，避免 Director 写了非常规词就漏判。
        dc = DIFFICULTY_DC["normal"]

    view = state_v2 if isinstance(state_v2, dict) else {}
    modifier, breakdown = _compute_modifier(check, view)

    rng = rng or _DEFAULT_RNG
    roll = rng.randint(1, 20)
    total = roll + modifier

    outcome = _outcome_for(roll, total, dc)
    return {
        "action": _text(check.get("action") or check.get("description")),
        "difficulty": raw_difficulty,
        "dc": dc,
        "roll": roll,
        "modifier": modifier,
        "total": total,
        "outcome": outcome,
        "outcome_label": OUTCOME_LABELS[outcome],
        "breakdown": breakdown,
    }


def _outcome_for(roll: int, total: int, dc: int) -> str:
    # 自然 20 必大成功、自然 1 必失败（给运气一个明确的天花板与地板）。
    if roll == 20:
        return "critical"
    if roll == 1:
        return "failure"
    if total >= dc + 8:
        return "critical"
    if total >= dc:
        return "success"
    if total >= dc - 5:
        return "partial"
    return "failure"


def _compute_modifier(check: dict[str, Any], view: dict[str, Any]) -> tuple[int, dict[str, int]]:
    sheet = _mapping(view.get("protagonist_sheet"))
    level = _int(sheet.get("level"), 1)
    # 等级修正：温和缩放，让高等级稳定占优但不碾压随机性。
    level_bonus = min(max(level - 1, 0) // 3, 12)

    skill_bonus = _skill_bonus(_text(check.get("skill")), view.get("skills"))
    attribute_bonus = _attribute_bonus(_text(check.get("attribute")), sheet.get("attributes"))
    relationship_bonus = _relationship_bonus(
        _text(check.get("target_npc") or check.get("target")),
        view.get("relationship_tracks"),
    )

    breakdown = {
        "level": level_bonus,
        "skill": skill_bonus,
        "attribute": attribute_bonus,
        "relationship": relationship_bonus,
    }
    return level_bonus + skill_bonus + attribute_bonus + relationship_bonus, breakdown


def _skill_bonus(skill_name: str, skills: Any) -> int:
    if not skill_name or not isinstance(skills, list):
        return 0
    target = skill_name.strip().lower()
    for item in skills:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"))
        if name and (name.lower() == target or target in name.lower() or name.lower() in target):
            level = _int(item.get("level"), 1)
            mastery = _int(item.get("mastery"), 0)
            return min(level + mastery // 34, 10)
    return 0


def _attribute_bonus(attribute_name: str, attributes: Any) -> int:
    if not attribute_name or not isinstance(attributes, dict):
        return 0
    target = attribute_name.strip().lower()
    for key, value in attributes.items():
        key_text = _text(key)
        if key_text and (key_text.lower() == target or target in key_text.lower()):
            numeric = _optional_int(value)
            if numeric is None:
                return 0
            # D&D 式调整值：(属性-10)//2，clamp 防极端数据。
            return _clamp((numeric - 10) // 2, -3, 8)
    return 0


def _relationship_bonus(target_npc: str, tracks: Any) -> int:
    if not target_npc or not isinstance(tracks, list):
        return 0
    target = target_npc.strip().lower()
    for track in tracks:
        if not isinstance(track, dict):
            continue
        npc = _text(track.get("npc"))
        if npc and (npc.lower() == target or target in npc.lower() or npc.lower() in target):
            trust = _optional_int(track.get("trust"))
            affection = _optional_int(track.get("affection"))
            values = [v for v in (trust, affection) if v is not None]
            if not values:
                return 0
            # 社交基准 50：高于则加成、低于则减值（低关系说服更难，对应 A2 软门槛）。
            social = max(values)
            return _clamp((social - 50) // 10, -5, 5)
    return 0


def build_outcome_instruction(result: dict[str, Any]) -> str:
    """把判定结果转成给 GM 的硬约束句。"""
    action = result.get("action") or "本次行动"
    label = result.get("outcome_label")
    outcome = result.get("outcome")
    base = (
        f"【判定结果·硬约束】玩家「{action}」的判定为 **{label}**"
        f"（难度 {result.get('difficulty')}，掷骰 {result.get('roll')}"
        f"+修正 {result.get('modifier')}={result.get('total')} vs DC {result.get('dc')}）。"
    )
    if outcome == "failure":
        consequence = "必须写出这次行动**失败**：受阻、付出代价或引发并发症，不得改写成顺利成功。"
    elif outcome == "partial":
        consequence = "必须写成**部分成功**：达成部分目标，但伴随代价、暴露、延迟或新的麻烦。"
    elif outcome == "critical":
        consequence = "写成**额外出彩的成功**：达成目标并带来一个意外的有利结果。"
    else:
        consequence = "写成**成功**：达成目标，但仍可保留合理的紧张感。"
    return base + consequence


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _int(value: Any, default: int) -> int:
    parsed = _optional_int(value)
    return parsed if parsed is not None else default


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value.strip()))
        except ValueError:
            return None
    return None


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
