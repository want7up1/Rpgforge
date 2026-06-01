from __future__ import annotations

import re
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
    story_progress = _story_progress(state.get("story_progress"))
    state["story_progress"] = story_progress

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
        "story_progress": story_progress,
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


def _named_identity(value: Any) -> str:
    if isinstance(value, dict):
        return _first_text(value.get("name"), value.get("title"), value.get("id"))
    return _first_text(value)


def _present_npc_names(npcs: list[Any], current_location: str) -> list[str]:
    names: list[str] = []
    for npc in npcs:
        if not isinstance(npc, dict):
            continue
        name = _named_identity(npc)
        if not name:
            continue
        if _npc_is_present(npc, current_location):
            _append_unique(names, name)
    return names


def _npc_is_present(npc: dict[str, Any], current_location: str) -> bool:
    if npc.get("active") is True or npc.get("present") is True:
        return True

    npc_location = _first_text(npc.get("location"), npc.get("current_location"))
    if _locations_overlap(current_location, npc_location):
        return True

    location_text = "\n".join(
        _first_text(npc.get(key)) for key in ("location", "current_location")
    )
    if current_location and current_location in location_text:
        return True

    context_text = "\n".join(
        _first_text(npc.get(key))
        for key in ("status", "state", "relationship", "attitude")
    )
    return any(
        marker in context_text
        for marker in ("在场", "同行", "同伴", "队伍", "跟随", "陪同", "身边", "交谈")
    )


def _locations_overlap(current_location: str, npc_location: str) -> bool:
    if not current_location or not npc_location:
        return False
    if current_location in npc_location or npc_location in current_location:
        return True
    current_fragments = _location_fragments(current_location)
    npc_fragments = _location_fragments(npc_location)
    return any(
        left in npc_location or right in current_location
        for left in current_fragments
        for right in npc_fragments
    )


def _location_fragments(value: str) -> list[str]:
    fragments: list[str] = []
    for part in re.split(r"[\s,，、。；;：:（）()及和与/\\-]+", value):
        text = _first_text(part)
        if len(text) >= 4 and text not in fragments:
            fragments.append(text)
    return fragments


def _party_names(state: dict[str, Any], npcs: list[Any], present_npcs: list[str]) -> list[str]:
    party: list[str] = []
    for item in _list(state.get("party")):
        name = _identity(item)
        if name:
            _append_unique(party, name)

    for npc in npcs:
        if not isinstance(npc, dict):
            continue
        name = _named_identity(npc)
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
        name = _named_identity(npc)
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
            quest_id = _first_text(quest.get("id"), quest.get("key"))
            name = _first_text(quest.get("title"), quest.get("name"), quest_id)
            if not name:
                continue
            status = _first_text(quest.get("status"), quest.get("state"), quest.get("new_status"))
            item = {
                "id": quest_id or name,
                "name": name,
                "title": name,
                "status": status or "active",
                "objective": _first_text(
                    quest.get("objective"),
                    quest.get("current"),
                    quest.get("description"),
                ),
                "act_id": _first_text(quest.get("act_id"), quest.get("act")),
            }

        bucket = _quest_bucket(item["status"])
        marker = (bucket, item.get("id") or item["name"])
        if marker in seen:
            continue
        seen.add(marker)
        log[bucket].append(item)
    return log


def _quest_bucket(status: str) -> str:
    text = status.lower()
    if any(marker in text for marker in ("隐藏", "秘密", "hidden", "secret", "unknown")):
        return "hidden"
    if any(marker in text for marker in ("完成", "解决", "closed", "complete")):
        return "completed"
    if any(marker in text for marker in ("失败", "放弃", "failed")):
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
        data = _thread_payload(thread)
        title = _first_text(data.get("title"), data.get("name"), data.get("description"))
        status = _first_text(data.get("status"), data.get("state"))
        if not status and _thread_action_resolves(_first_text(thread.get("action")).lower()):
            status = "resolved"
        return {
            "title": title,
            "status": status or "active",
            "source": _first_text(data.get("source")),
        }
    return {"title": _first_text(thread), "status": "active", "source": ""}


def _thread_is_resolved(thread: dict[str, Any]) -> bool:
    # 只看显式 status/state，不拿 title 做子串匹配——否则"调查未完成的仪式""解决粮食危机"
    # 这类含"完成/解决"字样的活跃线索会被误判已解决，从"未解线索"里消失。
    status = _first_text(thread.get("status"), thread.get("state")).lower()
    return any(
        marker in status
        for marker in ("完成", "解决", "关闭", "resolved", "closed", "complete", "done", "finished")
    )


def _thread_payload(thread: dict[str, Any]) -> dict[str, Any]:
    nested = thread.get("thread")
    if isinstance(nested, dict):
        payload = dict(nested)
        for key in ("id", "key", "title", "name", "status", "state", "source"):
            if not payload.get(key) and thread.get(key):
                payload[key] = thread[key]
        return payload
    return thread


def _thread_action_resolves(action: str) -> bool:
    return action in {
        "resolve",
        "resolved",
        "close",
        "closed",
        "complete",
        "completed",
        "done",
        "finish",
        "finished",
        "解决",
        "关闭",
        "完成",
    }


def _story_progress(value: Any) -> dict[str, Any]:
    progress = _mapping(value)
    return {
        "current_act": _first_text(progress.get("current_act"), progress.get("act")),
        "completed_acts": _unique_texts(progress.get("completed_acts")),
        "completed_anchors": _unique_texts(progress.get("completed_anchors")),
        "ready_for_next_act": _bool(progress.get("ready_for_next_act"), False),
        "last_advance_turn": _optional_nonnegative_int(progress.get("last_advance_turn")),
        "last_advance_reason": _first_text(progress.get("last_advance_reason")),
        "last_anchor_update_turn": _optional_nonnegative_int(
            progress.get("last_anchor_update_turn")
        ),
        "act_history": _act_history(progress.get("act_history")),
        "anchor_history": _anchor_history(progress.get("anchor_history")),
        "next_act": _first_text(progress.get("next_act")),
        "current_act_anchor_progress": _anchor_progress(
            progress.get("current_act_anchor_progress")
        ),
    }


def _anchor_progress(value: Any) -> dict[str, int]:
    """当前幕锚点进度 {done, total}，供前端展示"本幕 done/total"而非全局 completed 总数。"""
    data = _mapping(value)
    done = _optional_nonnegative_int(data.get("done")) or 0
    total = _optional_nonnegative_int(data.get("total")) or 0
    return {"done": done, "total": total}


def _act_history(value: Any) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for item in _list(value)[-20:]:
        if not isinstance(item, dict):
            continue
        record = {
            "turn": _optional_nonnegative_int(item.get("turn")),
            "from_act": _first_text(item.get("from_act")),
            "to_act": _first_text(item.get("to_act")),
            "reason": _first_text(item.get("reason")),
        }
        if record["from_act"] or record["to_act"] or record["reason"]:
            history.append(record)
    return history


def _anchor_history(value: Any) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for item in _list(value)[-30:]:
        if not isinstance(item, dict):
            continue
        record = {
            "turn": _optional_nonnegative_int(item.get("turn")),
            "act": _first_text(item.get("act")),
            "anchor_id": _first_text(item.get("anchor_id"), item.get("id")),
            "reason": _first_text(item.get("reason")),
        }
        if record["anchor_id"]:
            history.append(record)
    return history


def _unique_texts(value: Any) -> list[str]:
    texts: list[str] = []
    for item in _list(value):
        text = _identity(item)
        if text and text not in texts:
            texts.append(text)
    return texts


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
        name = _named_identity(npc)
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


def _optional_nonnegative_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return max(0, _int(value, 0))


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "y"}:
            return True
        if text in {"false", "0", "no", "n"}:
            return False
    return default


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def project_state_for_scene(state_v2: dict[str, Any] | None) -> dict[str, Any]:
    """GM 场景投影（Round 23）：只给 GM 写作用，砍掉用不到的历史/非在场噪声。

    保留当前场景写作所需（active_scene / protagonist_sheet / abilities / conditions /
    party / story_progress / skills / open_threads 全保留）；精简：
    - progression：砍 xp_log（XP 历史明细，GM 规则 20 不输出 XP）。
    - quest_log：active 全留；completed 压成 completed_titles（只留标题，知道做过什么）。
    - npc_registry：只留在场（present_npcs ∪ party）。
    - relationship_tracks：只留在场角色；recent_events 只留最近 1 条。

    **兜底**：present 名单为空时不过滤 npc_registry / relationship_tracks（避免砍光）。
    仅 GM 用此投影；DriftValidator / StateExtractor 仍用全量 state（判状态冲突 / 算 delta 需要全）。
    """
    if not isinstance(state_v2, dict):
        return state_v2
    projected = dict(state_v2)

    progression = state_v2.get("progression")
    if isinstance(progression, dict) and "xp_log" in progression:
        projected["progression"] = {k: v for k, v in progression.items() if k != "xp_log"}

    quest_log = state_v2.get("quest_log")
    if isinstance(quest_log, dict):
        completed = quest_log.get("completed") or []
        titles = [
            (q.get("title") or q.get("name"))
            for q in completed
            if isinstance(q, dict) and (q.get("title") or q.get("name"))
        ]
        # hidden 任务保留给 GM（用户决策 P3-12）：只给标题 + 目标，让 GM 提前埋线铺垫。
        # 但只投影"当前幕 + 下一幕"的隐藏目标——给近期铺垫空间，不把远期幕（act_4/5）的
        # 角色/剧情提前抛给 GM 造成剧透（修 bug：女主名字提前出现）。
        sp = state_v2.get("story_progress") or {}
        near_acts = {a for a in (sp.get("current_act"), sp.get("next_act")) if a}
        hidden = [
            {key: q.get(key) for key in ("title", "name", "objective") if q.get(key)}
            for q in (quest_log.get("hidden") or [])
            if isinstance(q, dict) and (not near_acts or q.get("act_id") in near_acts)
        ]
        projected["quest_log"] = {
            "active": quest_log.get("active") or [],
            "completed_titles": titles,
            "hidden": hidden,
        }

    active_scene = state_v2.get("active_scene") or {}
    present = set(active_scene.get("present_npcs") or []) | set(state_v2.get("party") or [])

    if present:
        npcs = state_v2.get("npc_registry")
        if isinstance(npcs, list):
            projected["npc_registry"] = [
                n for n in npcs if isinstance(n, dict) and n.get("name") in present
            ]
        rels = state_v2.get("relationship_tracks")
        if isinstance(rels, list):
            slim: list[dict[str, Any]] = []
            for relation in rels:
                if not isinstance(relation, dict) or relation.get("npc") not in present:
                    continue
                trimmed = dict(relation)
                events = trimmed.get("recent_events")
                if isinstance(events, list) and len(events) > 1:
                    trimmed["recent_events"] = events[-1:]
                slim.append(trimmed)
            projected["relationship_tracks"] = slim

    return projected
