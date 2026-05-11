from __future__ import annotations

from typing import Any

RELATIONSHIP_AXES = {
    "trust": "trust",
    "信任": "trust",
    "affection": "affection",
    "亲密": "affection",
    "好感": "affection",
    "respect": "respect",
    "尊重": "respect",
    "fear": "fear",
    "畏惧": "fear",
    "loyalty": "loyalty",
    "忠诚": "loyalty",
    "conflict": "conflict",
    "冲突": "conflict",
}

XP_BASE_BY_CATEGORY = {
    "story": 30,
    "story_xp": 30,
    "main": 30,
    "主线": 30,
    "discovery": 18,
    "discovery_xp": 18,
    "探索": 18,
    "发现": 18,
    "survival": 20,
    "survival_xp": 20,
    "生存": 20,
    "social": 16,
    "social_xp": 16,
    "社交": 16,
    "combat": 20,
    "combat_xp": 20,
    "战斗": 20,
    "craft": 16,
    "building": 16,
    "建设": 16,
}

DIFFICULTY_MULTIPLIER = {
    "trivial": 0.25,
    "easy": 0.75,
    "normal": 1.0,
    "medium": 1.0,
    "hard": 1.5,
    "extreme": 2.0,
    "简单": 0.75,
    "普通": 1.0,
    "困难": 1.5,
    "极难": 2.0,
}

SIGNIFICANCE_MULTIPLIER = {
    "minor": 0.5,
    "standard": 1.0,
    "normal": 1.0,
    "major": 1.75,
    "critical": 2.25,
    "小": 0.5,
    "中": 1.0,
    "大": 1.75,
    "关键": 2.25,
}

OUTCOME_MULTIPLIER = {
    "failure": 0.45,
    "fail": 0.45,
    "partial": 0.75,
    "success": 1.0,
    "critical": 1.5,
    "失败": 0.45,
    "部分成功": 0.75,
    "成功": 1.0,
    "大成功": 1.5,
}

RELATIONSHIP_CHANGE_BY_INTENSITY = {
    "minor": 3,
    "standard": 6,
    "normal": 6,
    "major": 10,
    "critical": 15,
    "小": 3,
    "中": 6,
    "大": 10,
    "关键": 15,
}


def apply_quantified_state_events(state: dict[str, Any], delta: dict[str, Any]) -> None:
    _ensure_roots(state)

    for event in _as_list(delta.get("xp_events")):
        _apply_xp_event(state, event)
    for event in _as_list(delta.get("skill_events")):
        _apply_skill_event(state, event)
    for update in _as_list(delta.get("ability_updates")):
        _apply_ability_update(state, update)
    for update in _as_list(delta.get("condition_updates")):
        _apply_condition_update(state, update)
    for event in _as_list(delta.get("relationship_events")):
        _apply_relationship_event(state, event)


def _ensure_roots(state: dict[str, Any]) -> None:
    progression = state.setdefault("progression", {})
    if not isinstance(progression, dict):
        progression = {}
        state["progression"] = progression
    level = _positive_int(progression.get("level"), 1)
    progression["level"] = level
    progression["xp"] = max(0, _int(progression.get("xp"), 0))
    progression["total_xp"] = max(0, _int(progression.get("total_xp"), progression["xp"]))
    progression["next_level_xp"] = max(
        1,
        _int(progression.get("next_level_xp"), _next_level_xp(level)),
    )
    progression.setdefault("xp_log", [])

    for key in ("attributes", "skills", "abilities", "conditions", "relationships"):
        default = {} if key == "attributes" else []
        if not isinstance(state.get(key), type(default)):
            state[key] = default


def _apply_xp_event(state: dict[str, Any], event: Any) -> None:
    if not isinstance(event, dict):
        event = {"reason": _text(event)}
    reason = _text(event.get("reason") or event.get("description") or event.get("name"))
    if not reason:
        return

    category = _text(event.get("category") or event.get("type") or "story")
    difficulty = _text(event.get("difficulty") or "normal")
    significance = _text(event.get("significance") or event.get("impact") or "standard")
    base = XP_BASE_BY_CATEGORY.get(category, 16)
    amount = round(
        base
        * DIFFICULTY_MULTIPLIER.get(difficulty, 1.0)
        * SIGNIFICANCE_MULTIPLIER.get(significance, 1.0)
    )
    amount = _clamp(amount, 1, 90)

    progression = state["progression"]
    progression["xp"] += amount
    progression["total_xp"] += amount
    _append_log(
        progression["xp_log"],
        {
            "amount": amount,
            "category": category,
            "reason": reason,
        },
        limit=20,
    )
    _apply_level_ups(progression)


def _apply_skill_event(state: dict[str, Any], event: Any) -> None:
    if not isinstance(event, dict):
        event = {"name": _text(event)}
    name = _text(event.get("skill") or event.get("name"))
    if not name:
        return

    skill = _upsert_named(state["skills"], name)
    skill.setdefault("level", 1)
    skill.setdefault("xp", 0)
    skill.setdefault("next_level_xp", _next_skill_level_xp(_positive_int(skill.get("level"), 1)))
    skill.setdefault("visibility", "known")
    skill.setdefault("recent_events", [])

    difficulty = _text(event.get("difficulty") or "normal")
    outcome = _text(event.get("outcome") or "success")
    amount = round(
        10
        * DIFFICULTY_MULTIPLIER.get(difficulty, 1.0)
        * OUTCOME_MULTIPLIER.get(outcome, 1.0)
    )
    amount = _clamp(amount, 1, 35)

    skill["xp"] = max(0, _int(skill.get("xp"), 0)) + amount
    _append_log(
        skill["recent_events"],
        {
            "amount": amount,
            "difficulty": difficulty,
            "outcome": outcome,
            "reason": _text(event.get("reason") or event.get("description")),
        },
        limit=8,
    )
    _apply_skill_level_ups(skill)
    skill["mastery"] = _mastery(skill)


def _apply_ability_update(state: dict[str, Any], update: Any) -> None:
    if not isinstance(update, dict):
        update = {"name": _text(update)}
    name = _text(update.get("ability") or update.get("name"))
    if not name:
        return

    ability = _upsert_named(state["abilities"], name)
    for key in (
        "description",
        "status",
        "visibility",
        "resource_cost",
        "cooldown",
        "usage_note",
    ):
        value = update.get(key)
        if _has_value(value):
            ability[key] = value
    ability["level"] = _positive_int(update.get("level"), _positive_int(ability.get("level"), 1))
    ability.setdefault("visibility", "known")


def _apply_condition_update(state: dict[str, Any], update: Any) -> None:
    if not isinstance(update, dict):
        update = {"name": _text(update)}
    name = _text(update.get("condition") or update.get("name"))
    if not name:
        return
    status = _text(update.get("status") or update.get("state") or "active")
    if _is_resolved(status):
        state["conditions"] = [
            condition
            for condition in state["conditions"]
            if not isinstance(condition, dict) or _identity(condition) != name
        ]
        return

    condition = _upsert_named(state["conditions"], name)
    condition["status"] = status
    for key in ("severity", "duration", "source", "visibility"):
        value = update.get(key)
        if _has_value(value):
            condition[key] = value
    condition.setdefault("visibility", "known")


def _apply_relationship_event(state: dict[str, Any], event: Any) -> None:
    if not isinstance(event, dict):
        return
    npc_name = _text(event.get("npc") or event.get("name") or event.get("target"))
    if not npc_name:
        return

    axis = RELATIONSHIP_AXES.get(_text(event.get("axis") or event.get("type")), "trust")
    relation = _upsert_named(state["relationships"], npc_name, id_key="npc")
    relation.setdefault("npc", npc_name)
    relation.setdefault("recent_events", [])
    for key in ("trust", "affection", "respect", "fear", "loyalty", "conflict"):
        relation[key] = _clamp(_int(relation.get(key), 0), 0, 100)

    direction = _text(event.get("direction") or "increase")
    intensity = _text(event.get("intensity") or event.get("significance") or "standard")
    amount = RELATIONSHIP_CHANGE_BY_INTENSITY.get(intensity, 6)
    if direction in {"decrease", "down", "降低", "减少", "下降"}:
        amount = -amount

    relation[axis] = _clamp(relation[axis] + amount, 0, 100)
    relation["stage"] = _relationship_stage(relation)
    relation["visibility"] = _text(event.get("visibility") or relation.get("visibility") or "known")
    _append_log(
        relation["recent_events"],
        {
            "axis": axis,
            "change": amount,
            "reason": _text(event.get("reason") or event.get("description")),
        },
        limit=8,
    )


def _apply_level_ups(progression: dict[str, Any]) -> None:
    while progression["xp"] >= progression["next_level_xp"]:
        progression["xp"] -= progression["next_level_xp"]
        progression["level"] += 1
        progression["next_level_xp"] = _next_level_xp(progression["level"])


def _apply_skill_level_ups(skill: dict[str, Any]) -> None:
    skill["level"] = _positive_int(skill.get("level"), 1)
    skill["next_level_xp"] = _positive_int(
        skill.get("next_level_xp"),
        _next_skill_level_xp(skill["level"]),
    )
    while skill["xp"] >= skill["next_level_xp"]:
        skill["xp"] -= skill["next_level_xp"]
        skill["level"] += 1
        skill["next_level_xp"] = _next_skill_level_xp(skill["level"])


def _relationship_stage(relation: dict[str, Any]) -> str:
    if relation["conflict"] >= 70:
        return "冲突"
    if max(relation["trust"], relation["affection"], relation["loyalty"]) >= 80:
        return "羁绊"
    if relation["affection"] >= 65:
        return "亲密"
    if relation["trust"] >= 50:
        return "信任"
    if max(relation["trust"], relation["respect"], relation["affection"]) >= 25:
        return "合作"
    return "陌生"


def _next_level_xp(level: int) -> int:
    return 100 + max(0, level - 1) * 75


def _next_skill_level_xp(level: int) -> int:
    return 80 + max(0, level - 1) * 40


def _mastery(skill: dict[str, Any]) -> int:
    current_xp = _int(skill.get("xp"), 0)
    next_level_xp = _positive_int(skill.get("next_level_xp"), 1)
    return _clamp(round(current_xp / next_level_xp * 100), 0, 100)


def _upsert_named(collection: list[Any], name: str, id_key: str = "name") -> dict[str, Any]:
    for item in collection:
        if isinstance(item, dict) and _identity(item) == name:
            item.setdefault(id_key, name)
            return item
    item = {id_key: name}
    if id_key != "name":
        item["name"] = name
    collection.append(item)
    return item


def _append_log(target: list[Any], item: dict[str, Any], limit: int) -> None:
    target.append(item)
    del target[:-limit]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _identity(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("id") or value.get("name") or value.get("title") or value.get("npc"))
    return _text(value)


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _is_resolved(status: str) -> bool:
    return status in {"resolved", "removed", "cured", "已解决", "移除", "痊愈", "解除"}


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _positive_int(value: Any, default: int) -> int:
    return max(1, _int(value, default))


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
