from __future__ import annotations

from copy import deepcopy
from typing import Any

STATE_V2_VERSION = 1
ACTIVE_THREAD_LIMIT = 24


def normalize_state_v2(
    state_json: dict[str, Any] | None,
    current_turn: int | None = None,
) -> dict[str, Any]:
    state = deepcopy(state_json or {})
    if current_turn is not None:
        state["current_turn"] = max(int(state.get("current_turn") or 0), current_turn)

    time_state = _mapping(state.get("time"))
    location_state = _mapping(state.get("location"))
    npcs = _list(state.get("npcs"))
    quests = _list(state.get("quests"))

    location_name = _first_text(location_state.get("current"), location_state.get("name"))
    present_npcs = _present_npc_names(npcs, location_name)
    progression = _progression(state)
    skills = _skill_view(state.get("skills"))
    abilities = _ability_view(state.get("abilities"))
    conditions = _condition_view(state.get("conditions"))

    state["v2"] = {
        "version": STATE_V2_VERSION,
        "active_scene": {
            "turn": int(state.get("current_turn") or 0),
            "time": _first_text(time_state.get("current"), time_state.get("last_delta")),
            "location": location_name,
            "pressure": _first_text(
                location_state.get("pressure"),
                time_state.get("pressure"),
                state.get("pressure"),
            ),
            "present_npcs": present_npcs,
        },
        "protagonist_sheet": _protagonist_sheet(state, progression, abilities, conditions),
        "progression": progression,
        "skills": skills,
        "abilities": abilities,
        "conditions": conditions,
        "party": _party_names(state, npcs, present_npcs),
        "npc_registry": _npc_registry(npcs),
        "quest_log": _quest_log(quests),
        "open_threads": _thread_log(state.get("open_threads")),
        "relationship_tracks": _relationship_tracks(state.get("relationships"), npcs),
    }
    return state


def state_v2_view(state_json: dict[str, Any] | None) -> dict[str, Any]:
    state = normalize_state_v2(state_json)
    v2 = state.get("v2")
    return v2 if isinstance(v2, dict) else {}


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value).strip()
            if text:
                return text
    return ""


def _identity(value: Any) -> str:
    if isinstance(value, dict):
        return _first_text(value.get("id"), value.get("name"), value.get("title"))
    return _first_text(value)


def _present_npc_names(npcs: list[Any], current_location: str) -> list[str]:
    names: list[str] = []
    for npc in npcs:
        if not isinstance(npc, dict):
            continue
        name = _identity(npc)
        if not name:
            continue
        if _npc_is_present(npc, current_location):
            _append_unique(names, name)
    return names


def _npc_is_present(npc: dict[str, Any], current_location: str) -> bool:
    if npc.get("active") is True or npc.get("present") is True:
        return True

    haystack = "\n".join(
        _first_text(npc.get(key))
        for key in ("location", "current_location", "status", "state", "relationship", "attitude")
    )
    if current_location and current_location in haystack:
        return True
    return any(
        marker in haystack
        for marker in ("在场", "同行", "同伴", "队伍", "跟随", "陪同", "身边", "交谈", "保护")
    )


def _party_names(state: dict[str, Any], npcs: list[Any], present_npcs: list[str]) -> list[str]:
    party: list[str] = []
    for item in _list(state.get("party")):
        name = _identity(item)
        if name:
            _append_unique(party, name)

    for npc in npcs:
        if not isinstance(npc, dict):
            continue
        name = _identity(npc)
        if not name:
            continue
        relation_text = "\n".join(
            _first_text(npc.get(key)) for key in ("relationship", "attitude", "status", "state")
        )
        is_party_member = any(marker in relation_text for marker in ("同伴", "队友", "同行"))
        if name in present_npcs or is_party_member:
            _append_unique(party, name)
    return party


def _npc_registry(npcs: list[Any]) -> list[dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    for npc in npcs:
        if not isinstance(npc, dict):
            continue
        name = _identity(npc)
        if not name:
            continue
        existing = registry.setdefault(
            name,
            {
                "id": _first_text(npc.get("id"), name),
                "name": name,
                "identity": "",
                "status": "",
                "location": "",
                "relationship": "",
                "attitude": "",
            },
        )
        for key in ("identity", "status", "location", "relationship", "attitude"):
            value = _first_text(npc.get(key))
            if value:
                existing[key] = value
    return list(registry.values())


def _quest_log(quests: list[Any]) -> dict[str, list[dict[str, Any]]]:
    log = {"active": [], "completed": [], "failed": [], "hidden": []}
    seen: set[tuple[str, str]] = set()
    for quest in quests:
        if not isinstance(quest, dict):
            name = _identity(quest)
            if not name:
                continue
            item = {"name": name, "status": "active", "objective": ""}
        else:
            name = _identity(quest)
            if not name:
                continue
            status = _first_text(quest.get("status"), quest.get("state"), quest.get("new_status"))
            item = {
                "name": name,
                "status": status or "active",
                "objective": _first_text(
                    quest.get("objective"),
                    quest.get("current"),
                    quest.get("description"),
                ),
            }

        bucket = _quest_bucket(item["status"])
        marker = (bucket, item["name"])
        if marker in seen:
            continue
        seen.add(marker)
        log[bucket].append(item)
    return log


def _quest_bucket(status: str) -> str:
    if any(marker in status for marker in ("隐藏", "秘密", "unknown")):
        return "hidden"
    if any(marker in status for marker in ("完成", "解决", "closed", "complete")):
        return "completed"
    if any(marker in status for marker in ("失败", "放弃", "failed")):
        return "failed"
    return "active"


def _thread_log(open_threads: Any) -> dict[str, list[dict[str, Any]]]:
    log = {"active": [], "resolved": []}
    seen: set[tuple[str, str]] = set()
    for thread in _list(open_threads)[-ACTIVE_THREAD_LIMIT:]:
        item = _thread_item(thread)
        if not item["title"]:
            continue
        bucket = "resolved" if _thread_is_resolved(item) else "active"
        marker = (bucket, item["title"])
        if marker in seen:
            continue
        seen.add(marker)
        log[bucket].append(item)
    return log


def _thread_item(thread: Any) -> dict[str, Any]:
    if isinstance(thread, dict):
        title = _first_text(thread.get("title"), thread.get("name"), thread.get("description"))
        status = _first_text(thread.get("status"), thread.get("state"))
        return {
            "title": title,
            "status": status or "active",
            "source": _first_text(thread.get("source")),
        }
    return {"title": _first_text(thread), "status": "active", "source": ""}


def _thread_is_resolved(thread: dict[str, Any]) -> bool:
    text = "\n".join(_first_text(thread.get(key)) for key in ("title", "status"))
    return any(marker in text for marker in ("完成", "解决", "关闭", "resolved", "closed"))


def _progression(state: dict[str, Any]) -> dict[str, Any]:
    progression = _mapping(state.get("progression"))
    level = _positive_int(progression.get("level"), 1)
    xp = max(0, _int(progression.get("xp"), 0))
    next_level_xp = _positive_int(progression.get("next_level_xp"), 100 + (level - 1) * 75)
    total_xp = max(xp, _int(progression.get("total_xp"), xp))
    normalized = {
        "level": level,
        "xp": xp,
        "next_level_xp": next_level_xp,
        "total_xp": total_xp,
        "xp_log": _list(progression.get("xp_log"))[-20:],
    }
    state["progression"] = normalized
    return normalized


def _protagonist_sheet(
    state: dict[str, Any],
    progression: dict[str, Any],
    abilities: list[dict[str, Any]],
    conditions: list[dict[str, Any]],
) -> dict[str, Any]:
    protagonist = _mapping(state.get("protagonist"))
    attributes = _mapping(state.get("attributes"))
    if not attributes:
        attributes = _mapping(protagonist.get("attributes"))
    return {
        "name": _first_text(protagonist.get("name")),
        "identity": _first_text(protagonist.get("identity")),
        "level": progression["level"],
        "xp": progression["xp"],
        "next_level_xp": progression["next_level_xp"],
        "total_xp": progression["total_xp"],
        "attributes": attributes,
        "abilities": abilities,
        "conditions": conditions,
    }


def _skill_view(value: Any) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for item in _list(value):
        if not isinstance(item, dict):
            continue
        name = _identity(item)
        if not name:
            continue
        level = _positive_int(item.get("level"), 1)
        xp = max(0, _int(item.get("xp"), 0))
        next_level_xp = _positive_int(item.get("next_level_xp"), 80 + (level - 1) * 40)
        skills.append(
            {
                "name": name,
                "level": level,
                "xp": xp,
                "next_level_xp": next_level_xp,
                "mastery": _clamp(
                    _int(item.get("mastery"), round(xp / next_level_xp * 100)),
                    0,
                    100,
                ),
                "visibility": _first_text(item.get("visibility")) or "known",
                "recent_events": _list(item.get("recent_events"))[-8:],
            }
        )
    return skills


def _ability_view(value: Any) -> list[dict[str, Any]]:
    abilities: list[dict[str, Any]] = []
    for item in _list(value):
        if not isinstance(item, dict):
            continue
        name = _identity(item)
        if not name:
            continue
        abilities.append(
            {
                "name": name,
                "level": _positive_int(item.get("level"), 1),
                "visibility": _first_text(item.get("visibility")) or "known",
                "description": _first_text(item.get("description")),
                "status": _first_text(item.get("status")) or "active",
                "resource_cost": _first_text(item.get("resource_cost")),
                "cooldown": _first_text(item.get("cooldown")),
                "usage_note": _first_text(item.get("usage_note")),
            }
        )
    return abilities


def _condition_view(value: Any) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []
    for item in _list(value):
        if not isinstance(item, dict):
            continue
        name = _identity(item)
        if not name:
            continue
        status = _first_text(item.get("status")) or "active"
        if status in {"resolved", "removed", "cured", "已解决", "移除", "痊愈", "解除"}:
            continue
        conditions.append(
            {
                "name": name,
                "status": status,
                "severity": _first_text(item.get("severity")) or "medium",
                "duration": _first_text(item.get("duration")),
                "source": _first_text(item.get("source")),
                "visibility": _first_text(item.get("visibility")) or "known",
            }
        )
    return conditions


def _relationship_tracks(relationships: Any, npcs: list[Any]) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relation in _list(relationships):
        if not isinstance(relation, dict):
            continue
        name = _first_text(relation.get("npc"), relation.get("name"))
        if not name or name in seen:
            continue
        seen.add(name)
        tracks.append(
            {
                "npc": name,
                "stage": _first_text(relation.get("stage")) or _relationship_stage(relation),
                "trust": _clamp(_int(relation.get("trust"), 0), 0, 100),
                "affection": _clamp(_int(relation.get("affection"), 0), 0, 100),
                "respect": _clamp(_int(relation.get("respect"), 0), 0, 100),
                "fear": _clamp(_int(relation.get("fear"), 0), 0, 100),
                "loyalty": _clamp(_int(relation.get("loyalty"), 0), 0, 100),
                "conflict": _clamp(_int(relation.get("conflict"), 0), 0, 100),
                "visibility": _first_text(relation.get("visibility")) or "known",
                "recent_events": _list(relation.get("recent_events"))[-8:],
            }
        )

    for npc in npcs:
        if not isinstance(npc, dict):
            continue
        name = _identity(npc)
        if not name or name in seen:
            continue
        relationship = _first_text(npc.get("relationship"))
        attitude = _first_text(npc.get("attitude"))
        if not relationship and not attitude:
            continue
        seen.add(name)
        tracks.append(
            {
                "npc": name,
                "stage": "",
                "relationship": relationship,
                "attitude": attitude,
                "recent_interaction": _first_text(npc.get("recent_interaction"), npc.get("status")),
            }
        )
    return tracks


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _relationship_stage(relation: dict[str, Any]) -> str:
    if _int(relation.get("conflict"), 0) >= 70:
        return "冲突"
    if max(
        _int(relation.get("trust"), 0),
        _int(relation.get("affection"), 0),
        _int(relation.get("loyalty"), 0),
    ) >= 80:
        return "羁绊"
    if _int(relation.get("affection"), 0) >= 65:
        return "亲密"
    if _int(relation.get("trust"), 0) >= 50:
        return "信任"
    if max(
        _int(relation.get("trust"), 0),
        _int(relation.get("respect"), 0),
        _int(relation.get("affection"), 0),
    ) >= 25:
        return "合作"
    return "陌生"


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _positive_int(value: Any, default: int) -> int:
    return max(1, _int(value, default))


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
