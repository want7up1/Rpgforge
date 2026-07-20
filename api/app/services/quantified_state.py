"""纯叙事状态：只维护 conditions / relationships 两个**文字化**结构，零数字。

纯叙事化改造（Round 53）后，等级/经验/属性/技能熟练度/关系打分全部删除——游戏不再有任何
玩家可见数值。本模块只把 extractor 产出的「文字事实」落进结构化容器，供长局一致性：

- conditions：主角的处境/异常（中毒、受伤、被通缉…），值是文字 status + note，无 severity 数字。
- relationships：NPC 对主角的态度，值是一句文字 status（"从猜忌转为并肩"），无 trust/好感分数。

结构化是为了 GM 长局不健忘/不自相矛盾；但所有值都是散文，玩家侧看不到任何数字。
"""

from __future__ import annotations

from typing import Any


def apply_quantified_state_events(state: dict[str, Any], delta: dict[str, Any]) -> None:
    _ensure_roots(state)

    for update in _as_list(delta.get("condition_updates")):
        _apply_condition_update(state, update)
    for event in _as_list(delta.get("relationship_events")):
        _apply_relationship_event(state, event)


def _ensure_roots(state: dict[str, Any]) -> None:
    for key in ("conditions", "relationships"):
        if not isinstance(state.get(key), list):
            state[key] = []


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
    # 文字描述 + 来源；不再有 severity/duration 数字。
    for key in ("note", "description", "source", "visibility"):
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
    relation = _upsert_named(state["relationships"], npc_name, id_key="npc")
    relation.setdefault("npc", npc_name)
    # 关系是一句文字描述，不是分数/阶段。
    status = _text(event.get("status") or event.get("state") or event.get("description"))
    if status:
        relation["status"] = status
    note = _text(event.get("note"))
    if note:
        relation["note"] = note
    relation["visibility"] = _text(event.get("visibility") or relation.get("visibility") or "known")


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
