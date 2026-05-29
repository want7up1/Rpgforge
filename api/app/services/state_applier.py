import re
from copy import deepcopy
from typing import Any

from app.models.state import GameState
from app.models.turn import Turn
from app.services.quantified_state import apply_quantified_state_events
from app.services.state_v2 import normalize_state_v2
from app.services.story_settings import (
    completion_anchor_ids_for_act,
    story_settings_from_config,
    transition_target_for_act,
)

PLACEHOLDER_TEXTS = {"", "未定", "未知", "无名", "待定", "未命名角色", "未命名锚点"}
ACTIVITY_MARKER_STOPWORDS = {
    "任务",
    "目标",
    "完成",
    "成功",
    "首次",
    "建立",
    "救援",
    "寻找",
    "追踪",
    "探索",
    "秘密",
    "可能",
    "需要",
    "关键",
}
THREAD_QUEST_TOPIC_PREFIXES = (
    "发现",
    "营救",
    "救援",
    "寻找",
    "追踪",
    "探索",
    "调查",
    "建立",
    "完成",
)
LOCATION_EVENT_FIELDS = {
    "current",
    "name",
    "from",
    "to",
    "destination",
    "npc",
    "character",
    "actor",
    "reason",
}
ANCHOR_ACTION_TERMS = (
    "追踪",
    "发现",
    "找到",
    "抵达",
    "进入",
    "获取",
    "取得",
    "获得",
    "读取",
    "解读",
    "确认",
    "锁定",
    "截获",
    "定位",
    "接触",
    "遇见",
    "击败",
    "瓦解",
    "营救",
    "救出",
    "觉醒",
    "释放",
    "震碎",
    "触发",
    "完成",
)
ANCHOR_ACTION_EQUIVALENTS = {
    "追踪": ("追踪", "跟踪", "追查", "锁定", "定位", "截获"),
    "发现": ("发现", "找到", "确认", "锁定", "定位", "截获", "接触", "遇见", "看见"),
    "找到": ("找到", "发现", "确认", "锁定", "定位", "接触", "遇见", "看见"),
    "抵达": ("抵达", "到达", "进入", "来到"),
    "进入": ("进入", "抵达", "到达", "来到", "深入"),
    "获取": ("获取", "取得", "获得", "拿到", "带回", "发现", "读取", "解读", "确认"),
    "取得": ("取得", "获取", "获得", "拿到", "带回", "发现", "读取", "解读", "确认"),
    "获得": ("获得", "获取", "取得", "拿到", "带回", "发现", "读取", "解读", "确认"),
    "读取": ("读取", "读出", "接入", "解读", "解析", "获取", "发现"),
    "解读": ("解读", "解析", "读取", "获取", "发现", "确认"),
    "确认": ("确认", "证实", "查明", "核实", "锁定", "定位", "识别"),
    "锁定": ("锁定", "定位", "确认", "截获"),
    "截获": ("截获", "接收", "收到", "监听", "锁定"),
    "定位": ("定位", "锁定", "确认"),
    "接触": ("接触", "遇见", "会合", "确认", "发现"),
    "遇见": ("遇见", "接触", "会合", "发现", "找到"),
    "击败": ("击败", "打败", "击退", "消灭", "制服"),
    "瓦解": ("瓦解", "摧毁", "解除", "破坏"),
    "营救": ("营救", "救出", "救下", "救援", "带离", "撤离"),
    "救出": ("救出", "营救", "救下", "带离", "撤离"),
    "觉醒": ("觉醒", "爆发", "显现", "失控"),
    "释放": ("释放", "爆发", "发动"),
    "震碎": ("震碎", "震裂", "碎裂", "破裂"),
    "触发": ("触发", "引发", "激活", "启动"),
    "完成": ("完成", "结束", "解决", "达成"),
}
ANCHOR_TERM_SPLIT_RE = re.compile(
    r"[\s,，、。；;：:（）()——\-]+"
    r"|正在|仍在|已经|成功|完成|首次|完全|正式|开始|进行|通过"
    r"|追踪|发现|找到|抵达|进入|深入|获取|取得|获得|读取|解读|确认|锁定|截获|定位|接触|遇见"
    r"|击败|瓦解|营救|救出|觉醒|释放|震碎|触发"
    r"|以|用|由|在|至|到|于|把|将|被|和|与|及|并|后|中|为|的|了|一人|独自"
)
ANCHOR_TERM_STOPWORDS = {
    "当前",
    "本幕",
    "任务",
    "目标",
    "线索",
    "剧情",
    "状态",
    "事件",
    "完成",
    "成功",
    "已经",
    "正在",
    "仍在",
    "正式",
    "首次",
    "完全",
    "未命名锚点",
}
DERIVED_QUEST_SOURCES = {"main_quest_path", "completion_anchor"}
STATE_EVIDENCE_EXCLUDED_KEYS = {
    "v2",
    "quests",
    "variables",
    "hidden_facts",
    "story_progress",
}


def apply_state_delta(
    current_state: GameState,
    turn: Turn,
    delta: dict[str, Any],
) -> dict[str, Any]:
    state = deepcopy(current_state.state_json or {})
    state["current_turn"] = max(int(state.get("current_turn") or 0), turn.turn_number)

    game = getattr(current_state, "game", None)
    config = getattr(game, "config", None)

    _apply_time(state, delta)
    _apply_location(state, delta)
    _apply_inventory(state, delta)
    _apply_upserts(state, "npcs", _npc_updates_with_scene_location(delta, state, turn))
    _apply_upserts(state, "quests", delta.get("quest_updates", []))
    _apply_upserts(state, "factions", delta.get("faction_updates", []))
    _merge_mapping(state, "protagonist", delta.get("protagonist_updates", {}))
    _fill_protagonist_from_config(state, config)
    _merge_mapping(state, "variables", delta.get("variable_updates", {}))
    _sync_source_variables(state, game)
    _append_unique(state, "known_facts", delta.get("new_known_facts", []))
    _append_unique(state, "hidden_facts", delta.get("new_hidden_facts", []))
    _apply_thread_updates(state, delta.get("open_thread_updates", []))
    _apply_story_progress(state, turn, delta.get("story_progress_update", {}), config)
    _sync_story_progress_and_quests(state, turn, config)
    _merge_relationship_aliases(state)
    apply_quantified_state_events(state, delta)
    _merge_relationship_aliases(state)
    return normalize_state_v2(state, turn.turn_number)


def _apply_time(state: dict[str, Any], delta: dict[str, Any]) -> None:
    time_state = state.setdefault("time", {})
    if not isinstance(time_state, dict):
        time_state = {}
        state["time"] = time_state
    if delta.get("time_delta"):
        time_state["last_delta"] = delta["time_delta"]
    if delta.get("time_current"):
        time_state["current"] = delta["time_current"]


def _apply_location(state: dict[str, Any], delta: dict[str, Any]) -> None:
    location_change = delta.get("location_change")
    if not location_change:
        return
    location_state = state.setdefault("location", {})
    if not isinstance(location_state, dict):
        location_state = {}
        state["location"] = location_state

    for key in LOCATION_EVENT_FIELDS:
        location_state.pop(key, None)

    if isinstance(location_change, dict):
        current = _text(
            location_change.get("current")
            or location_change.get("name")
            or location_change.get("to")
            or location_change.get("destination")
        )
        location_state.update(
            {
                key: value
                for key, value in location_change.items()
                if key not in LOCATION_EVENT_FIELDS
            }
        )
        if current:
            location_state["current"] = current
    else:
        current = _text(location_change)
        location_state["current"] = current

    known = location_state.setdefault("known_locations", [])
    if current and isinstance(known, list) and current not in known:
        known.append(current)


def _apply_inventory(state: dict[str, Any], delta: dict[str, Any]) -> None:
    inventory = state.setdefault("inventory", [])
    if not isinstance(inventory, list):
        inventory = []
    inventory = _normalized_inventory(inventory)
    state["inventory"] = inventory

    for item in delta.get("inventory_add", []) or []:
        _add_inventory_item(inventory, item)

    for item in delta.get("inventory_remove", []) or []:
        _remove_inventory_item(inventory, item)
    state["inventory"] = _normalized_inventory(inventory)


def _npc_updates_with_scene_location(
    delta: dict[str, Any],
    state: dict[str, Any],
    turn: Turn,
) -> list[Any]:
    updates = delta.get("npc_updates", [])
    if not isinstance(updates, list):
        updates = [updates]
    if not delta.get("location_change"):
        return updates

    location_state = state.get("location")
    current_location = (
        _text(location_state.get("current")) if isinstance(location_state, dict) else ""
    )
    if not current_location:
        return updates

    candidates: list[tuple[int, str]] = []
    for index, update in enumerate(updates):
        if not isinstance(update, dict):
            continue
        normalized = _normalized_upsert_update(update, collection_key="npcs")
        if _has_value(normalized.get("location") or normalized.get("current_location")):
            continue
        name = _text(
            normalized.get("name")
            or normalized.get("npc")
            or normalized.get("title")
            or normalized.get("id")
        )
        if not name or _is_placeholder(name):
            continue
        candidates.append((index, name))

    if len(candidates) != 1:
        return updates

    index, name = candidates[0]
    if not _narrative_places_npc_in_changed_scene(name, current_location, turn):
        return updates

    patched = [deepcopy(update) for update in updates]
    if isinstance(patched[index], dict):
        patched[index]["location"] = current_location
    return patched


def _narrative_places_npc_in_changed_scene(
    name: str,
    current_location: str,
    turn: Turn,
) -> bool:
    narrative = "\n".join(
        _text(value)
        for value in (
            getattr(turn, "player_input", ""),
            getattr(turn, "gm_output", ""),
            getattr(turn, "visible_summary", ""),
        )
    )
    compact = re.sub(r"\s+", "", narrative)
    name = _text(name)
    if not name or name not in compact:
        return False
    if current_location and current_location in compact:
        return True
    return any(
        marker in compact
        for marker in (
            f"带{name}到",
            f"带{name}去",
            f"将{name}带到",
            f"把{name}带到",
            f"{name}被带到",
            f"{name}来到",
            f"{name}进入",
            f"与{name}来到",
            f"和{name}来到",
        )
    )


def _remove_inventory_item(inventory: list[Any], item: Any) -> None:
    if item in inventory:
        inventory.remove(item)
        return
    name = item.get("name") if isinstance(item, dict) else str(item)
    for existing in list(inventory):
        if isinstance(existing, dict) and existing.get("name") == name:
            inventory.remove(existing)
            return
        if isinstance(existing, str) and existing == name:
            inventory.remove(existing)
            return


def _normalized_inventory(values: list[Any]) -> list[Any]:
    normalized: list[Any] = []
    for item in values:
        _add_inventory_item(normalized, item)
    return normalized


def _add_inventory_item(inventory: list[Any], item: Any) -> None:
    key = _inventory_key(item)
    if key is None:
        if item not in inventory:
            inventory.append(item)
        return

    existing = next((entry for entry in inventory if _inventory_key(entry) == key), None)
    if existing is None:
        inventory.append(deepcopy(item))
        return
    if isinstance(existing, dict) and isinstance(item, dict):
        _merge_inventory_record(existing, item)


def _inventory_key(item: Any) -> tuple[str, str, str] | None:
    if isinstance(item, dict):
        name = _text(item.get("item") or item.get("name") or item.get("title"))
        if not name:
            return None
        return ("dict", name, _text(item.get("unit")))
    if isinstance(item, str):
        text = _text(item)
        return ("str", text, "") if text else None
    return None


def _merge_inventory_record(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    existing_quantity = _numeric(existing.get("quantity"))
    incoming_quantity = _numeric(incoming.get("quantity"))
    if incoming_quantity is not None:
        total = (
            existing_quantity + incoming_quantity
            if existing_quantity is not None
            else incoming_quantity
        )
        existing["quantity"] = int(total) if float(total).is_integer() else total
    for key, value in incoming.items():
        if key == "quantity":
            continue
        if _has_value(value) and not _has_value(existing.get(key)):
            existing[key] = value


def _apply_upserts(state: dict[str, Any], key: str, updates: list[Any]) -> None:
    collection = state.setdefault(key, [])
    if not isinstance(collection, list):
        collection = []
        state[key] = collection

    for update in updates or []:
        if not isinstance(update, dict):
            if update not in collection:
                collection.append(update)
            continue
        update = _normalized_upsert_update(update, collection_key=key)
        identifiers = _identity_candidates(update)
        if not identifiers:
            collection.append(update)
            continue
        existing = _find_existing_by_identity(collection, identifiers)
        if existing is None:
            collection.append(update)
        else:
            _preserve_name_aliases(existing, update)
            existing.update(update)


def _normalized_upsert_update(
    update: dict[str, Any],
    *,
    collection_key: str = "",
) -> dict[str, Any]:
    normalized = {
        key: deepcopy(item)
        for key, item in update.items()
        if key not in {"fields", "changes"}
    }
    _merge_patch_fields(normalized, update.get("fields"))
    _merge_patch_fields(normalized, update.get("changes"))

    if collection_key == "npcs" and _has_value(normalized.get("condition")):
        normalized.setdefault("status", deepcopy(normalized["condition"]))
    if collection_key == "quests" and any(
        _has_value(normalized.get(key)) for key in ("status", "state", "new_status")
    ):
        normalized.setdefault("source", "explicit")

    field_name = _text(normalized.get("field"))
    has_new_value = _has_value(normalized.get("new_value"))
    has_value = _has_value(normalized.get("value"))
    if not field_name or (not has_new_value and not has_value):
        return normalized

    value = normalized.get("new_value") if has_new_value else normalized.get("value")
    normalized = {
        key: deepcopy(item)
        for key, item in normalized.items()
        if key not in {"field", "new_value", "value"}
    }
    normalized[field_name] = deepcopy(value)
    return normalized


def _merge_patch_fields(target: dict[str, Any], patch: Any) -> None:
    if not isinstance(patch, dict):
        return
    for key, value in patch.items():
        field_name = _text(key)
        if field_name and _has_value(value):
            target[field_name] = deepcopy(value)


def _merge_mapping(state: dict[str, Any], key: str, updates: dict[str, Any]) -> None:
    if not updates:
        return
    target = state.setdefault(key, {})
    if not isinstance(target, dict):
        target = {}
        state[key] = target
    target.update(updates)


def _fill_protagonist_from_config(state: dict[str, Any], config: Any) -> None:
    configured = _configured_protagonist(config)
    if not configured:
        return
    target = state.setdefault("protagonist", {})
    if not isinstance(target, dict):
        target = {}
        state["protagonist"] = target

    for key in ("name", "identity", "appearance"):
        incoming = _text(configured.get(key))
        if incoming and _is_placeholder(target.get(key)):
            target[key] = incoming


def _append_unique(state: dict[str, Any], key: str, values: list[Any]) -> None:
    target = state.setdefault(key, [])
    if not isinstance(target, list):
        target = []
        state[key] = target
    for value in values or []:
        if value not in target:
            target.append(value)


def _apply_thread_updates(state: dict[str, Any], updates: list[Any]) -> None:
    target = state.setdefault("open_threads", [])
    if not isinstance(target, list):
        target = []
    normalized: list[dict[str, Any]] = []
    for value in target:
        _action, record = _thread_update_record(value)
        if record:
            _upsert_thread(normalized, record, "")
    state["open_threads"] = normalized

    for value in updates or []:
        action, record = _thread_update_record(value)
        if record:
            _upsert_thread(normalized, record, action)


def _thread_update_record(value: Any) -> tuple[str, dict[str, Any]]:
    if isinstance(value, str):
        title = _text(value)
        return "", {"title": title, "status": "active"} if title else {}
    if not isinstance(value, dict):
        return "", {}

    action = _text(value.get("action")).lower()
    thread = value.get("thread")
    if isinstance(thread, dict):
        record = dict(thread)
        for key in ("id", "key", "title", "name", "status", "state", "source"):
            if _has_value(value.get(key)) and not _has_value(record.get(key)):
                record[key] = value[key]
        return action, _clean_thread_record(record)

    record = {
        key: thread_value
        for key, thread_value in value.items()
        if key not in {"action", "thread"}
    }
    return action, _clean_thread_record(record)


def _clean_thread_record(record: dict[str, Any]) -> dict[str, Any]:
    cleaned = {
        key: deepcopy(value)
        for key, value in record.items()
        if key not in {"action", "thread", "fields", "changes"} and _has_value(value)
    }
    _merge_patch_fields(cleaned, record.get("fields"))
    _merge_patch_fields(cleaned, record.get("changes"))
    if not _thread_key(cleaned) and not _thread_title(cleaned):
        return {}
    if not _text(cleaned.get("status") or cleaned.get("state")):
        cleaned["status"] = "active"
    return cleaned


def _upsert_thread(collection: list[dict[str, Any]], record: dict[str, Any], action: str) -> None:
    if _thread_action_resolves(action):
        record = {**record, "status": "resolved"}

    key = _thread_key(record)
    existing = _find_thread(collection, key, record)
    if existing is None:
        collection.append(record)
        return
    _merge_thread_record(existing, record)


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


def _thread_key(record: dict[str, Any]) -> tuple[str, str] | None:
    identifier = _text(record.get("id") or record.get("key"))
    if identifier:
        return ("id", identifier)
    title = _thread_title(record)
    if title:
        return ("title", title)
    return None


def _thread_title(record: dict[str, Any]) -> str:
    return _text(record.get("title") or record.get("name") or record.get("description"))


def _find_thread(
    collection: list[dict[str, Any]],
    key: tuple[str, str] | None,
    record: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if key is None:
        return None
    for item in collection:
        if _thread_key(item) == key:
            return item
    incoming_identities = set(_thread_identity_values(record or {}))
    if not incoming_identities:
        return None
    for item in collection:
        if incoming_identities.intersection(_thread_identity_values(item)):
            return item
    return None


def _thread_identity_values(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("id", "key", "title", "name"):
        text = _text(record.get(key))
        if text and text not in values:
            values.append(text)
    return values


def _merge_thread_record(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        if not _has_value(value):
            continue
        target[key] = value


def _sync_source_variables(state: dict[str, Any], game: Any) -> None:
    if game is None:
        return
    variables = state.setdefault("variables", {})
    if not isinstance(variables, dict):
        variables = {}
        state["variables"] = variables

    title = _text(getattr(game, "title", None))
    description = _text(getattr(game, "description", None))
    if title:
        variables["source_title"] = title
    variables["source_description"] = description


def _merge_relationship_aliases(state: dict[str, Any]) -> None:
    relationships = state.get("relationships")
    if not isinstance(relationships, list):
        return

    aliases: dict[str, str] = {}
    for npc in state.get("npcs", []) or []:
        if not isinstance(npc, dict):
            continue
        name = _text(npc.get("name"))
        if not name or _is_placeholder(name):
            continue
        for alias in _identity_candidates(npc):
            if alias != name:
                aliases[alias] = name

    if not aliases:
        return

    merged: dict[str, dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    passthrough: list[Any] = []
    for relation in relationships:
        if not isinstance(relation, dict):
            passthrough.append(relation)
            continue
        current_name = _text(relation.get("npc") or relation.get("name"))
        canonical = aliases.get(current_name, current_name)
        relation["npc"] = canonical
        relation["name"] = canonical
        existing = merged.get(canonical)
        if existing is None:
            merged[canonical] = relation
            ordered.append(relation)
            continue
        _merge_relationship_record(existing, relation)
    state["relationships"] = [*ordered, *passthrough]


def _identity_candidates(value: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for key in ("id", "name", "title", "npc", "key"):
        text = _text(value.get(key))
        if text and text not in candidates:
            candidates.append(text)
    for alias in value.get("aliases") or []:
        text = _text(alias)
        if text and text not in candidates:
            candidates.append(text)
    return candidates


def _find_existing_by_identity(
    collection: list[Any],
    identifiers: list[str],
) -> dict[str, Any] | None:
    identifier_set = set(identifiers)
    for item in collection:
        if not isinstance(item, dict):
            continue
        if identifier_set.intersection(_identity_candidates(item)):
            return item
    return None


def _preserve_name_aliases(existing: dict[str, Any], update: dict[str, Any]) -> None:
    old_name = _text(existing.get("name"))
    new_name = _text(update.get("name"))
    if not old_name or not new_name or old_name == new_name:
        return
    aliases = existing.setdefault("aliases", [])
    if not isinstance(aliases, list):
        aliases = []
        existing["aliases"] = aliases
    if old_name not in aliases:
        aliases.append(old_name)


def _merge_relationship_record(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key in ("trust", "affection", "respect", "fear", "loyalty", "conflict"):
        target_value = _numeric(target.get(key))
        incoming_value = _numeric(incoming.get(key))
        if incoming_value is None:
            continue
        if target_value is None or incoming_value > target_value:
            target[key] = int(incoming_value)

    for key, value in incoming.items():
        if key in {"trust", "affection", "respect", "fear", "loyalty", "conflict"}:
            continue
        if key == "recent_events":
            target[key] = _merge_recent_events(target.get(key), value)
            continue
        if _has_value(value) and not _has_value(target.get(key)):
            target[key] = value


def _merge_recent_events(left: Any, right: Any) -> list[Any]:
    merged: list[Any] = []
    for source in (left, right):
        if not isinstance(source, list):
            continue
        for item in source:
            if item not in merged:
                merged.append(item)
    return merged[-8:]


def _configured_protagonist(config: Any) -> dict[str, Any]:
    settings = story_settings_from_config(config)
    for item in settings.get("core_characters") or []:
        if not isinstance(item, dict):
            continue
        if _text(item.get("role")).lower() in {"protagonist", "主角", "pc", "player"}:
            return item
    return {}


def _is_placeholder(value: Any) -> bool:
    text = _text(value)
    return text in PLACEHOLDER_TEXTS


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _apply_story_progress(state: dict[str, Any], turn: Turn, update: Any, config: Any) -> None:
    if not isinstance(update, dict):
        return

    next_act = _text(
        update.get("current_act")
        or update.get("next_act")
        or update.get("to_act")
    )
    pending_completed_acts = _act_list(update.get("completed_acts"))
    completed_act = _text(
        update.get("completed_act")
        or update.get("from_act")
        or update.get("previous_act")
    )
    if completed_act:
        pending_completed_acts.append(completed_act)
    completed_anchors = _identity_list(
        update.get("completed_anchors")
        or update.get("completed_anchor_ids")
    )
    completed_anchor = _identity(
        update.get("completed_anchor")
        or update.get("completed_anchor_id")
        or update.get("anchor_id")
    )
    if completed_anchor:
        completed_anchors.append(completed_anchor)
    has_ready_update = "ready_for_next_act" in update
    if (
        not next_act
        and not pending_completed_acts
        and not completed_anchors
        and not has_ready_update
    ):
        return

    progress = state.setdefault("story_progress", {})
    if not isinstance(progress, dict):
        progress = {}
        state["story_progress"] = progress

    previous_act = _text(progress.get("current_act") or progress.get("act")) or (
        _configured_current_act(config)
    )
    if previous_act and not _text(progress.get("current_act") or progress.get("act")):
        progress["current_act"] = previous_act
    completed_target = progress.setdefault("completed_acts", [])
    if not isinstance(completed_target, list):
        completed_target = []
        progress["completed_acts"] = completed_target

    anchor_target = progress.setdefault("completed_anchors", [])
    if not isinstance(anchor_target, list):
        anchor_target = []
        progress["completed_anchors"] = anchor_target
    new_anchor_ids: list[str] = []
    for anchor_id in completed_anchors:
        if anchor_id and anchor_id not in anchor_target:
            anchor_target.append(anchor_id)
            new_anchor_ids.append(anchor_id)

    if new_anchor_ids:
        progress["last_anchor_update_turn"] = turn.turn_number
        anchor_history = progress.setdefault("anchor_history", [])
        if not isinstance(anchor_history, list):
            anchor_history = []
            progress["anchor_history"] = anchor_history
        reason = _text(update.get("anchor_reason") or update.get("reason"))
        for anchor_id in new_anchor_ids:
            anchor_history.append(
                {
                    "turn": turn.turn_number,
                    "act": previous_act,
                    "anchor_id": anchor_id,
                    "reason": reason,
                }
            )
        del anchor_history[:-30]

    advance_allowed = _can_advance_to_act(config, previous_act, next_act, anchor_target)
    if not next_act or next_act == previous_act or advance_allowed:
        for act in pending_completed_acts:
            if act and act not in completed_target:
                completed_target.append(act)

    if next_act and advance_allowed:
        progress["current_act"] = next_act
        progress["last_advance_turn"] = turn.turn_number
        reason = _text(update.get("advance_reason") or update.get("reason"))
        if reason:
            progress["last_advance_reason"] = reason

        history = progress.setdefault("act_history", [])
        if not isinstance(history, list):
            history = []
            progress["act_history"] = history
        if next_act != previous_act:
            history.append(
                {
                    "turn": turn.turn_number,
                    "from_act": previous_act,
                    "to_act": next_act,
                    "reason": reason,
                }
            )
            del history[:-20]

    current_act = _text(progress.get("current_act") or progress.get("act"))
    computed_ready = _computed_ready_for_next_act(config, current_act, anchor_target)
    if computed_ready is not None:
        progress["ready_for_next_act"] = computed_ready
        return

    default_ready = False if next_act and next_act != previous_act else _bool(
        progress.get("ready_for_next_act"),
        False,
    )
    progress["ready_for_next_act"] = _bool(update.get("ready_for_next_act"), default_ready)


def _sync_story_progress_and_quests(state: dict[str, Any], turn: Turn, config: Any) -> None:
    settings = story_settings_from_config(config)
    acts = _script_acts(config)
    if not acts:
        return

    progress = state.setdefault("story_progress", {})
    if not isinstance(progress, dict):
        progress = {}
        state["story_progress"] = progress

    current_act = _text(progress.get("current_act") or progress.get("act")) or (
        _configured_current_act(config)
    )
    if not current_act:
        current_act = _act_identity(acts[0])
    if current_act and not _text(progress.get("current_act")):
        progress["current_act"] = current_act

    anchor_target = progress.setdefault("completed_anchors", [])
    if not isinstance(anchor_target, list):
        anchor_target = []
        progress["completed_anchors"] = anchor_target

    current_act = _sync_current_act_from_completed_anchors(
        progress,
        config,
        anchor_target,
    )

    evidence_units = _state_evidence_units(state)
    evidence = "\n".join(evidence_units)
    activity_evidence = _state_activity_text(state)
    inferred = _inferred_completed_anchors(config, current_act, anchor_target, evidence_units)
    if inferred:
        progress["last_anchor_update_turn"] = turn.turn_number
        anchor_history = progress.setdefault("anchor_history", [])
        if not isinstance(anchor_history, list):
            anchor_history = []
            progress["anchor_history"] = anchor_history
        for anchor_id, reason in inferred:
            anchor_target.append(anchor_id)
            anchor_history.append(
                {
                    "turn": turn.turn_number,
                    "act": current_act,
                    "anchor_id": anchor_id,
                    "reason": reason,
                }
            )
        del anchor_history[:-30]

    computed_ready = _computed_ready_for_next_act(config, current_act, anchor_target)
    if computed_ready is not None:
        progress["ready_for_next_act"] = computed_ready

    _resolve_completed_anchor_threads(state, config, anchor_target)

    next_act = transition_target_for_act(config, current_act)
    if (
        next_act
        and (
            computed_ready is True
            or (
                _bool(progress.get("ready_for_next_act"), False)
                and _act_activity_evident(settings, next_act, activity_evidence)
            )
        )
    ):
        _advance_story_progress(progress, current_act, next_act, turn)
        current_act = next_act
        computed_ready = _computed_ready_for_next_act(config, current_act, anchor_target)
        progress["ready_for_next_act"] = (
            computed_ready if computed_ready is not None else False
        )

    _sync_main_quests(state, settings, config, current_act, evidence, activity_evidence)


def _advance_story_progress(
    progress: dict[str, Any],
    from_act: str,
    to_act: str,
    turn: Turn,
) -> None:
    if not from_act or not to_act or from_act == to_act:
        return

    completed_acts = progress.setdefault("completed_acts", [])
    if not isinstance(completed_acts, list):
        completed_acts = []
        progress["completed_acts"] = completed_acts
    if from_act not in completed_acts:
        completed_acts.append(from_act)

    progress["current_act"] = to_act
    progress["last_advance_turn"] = turn.turn_number
    progress["last_advance_reason"] = "根据当前地点、线索或任务线程进入下一幕。"

    history = progress.setdefault("act_history", [])
    if not isinstance(history, list):
        history = []
        progress["act_history"] = history
    last_transition = history[-1] if history else {}
    if (
        not history
        or last_transition.get("from_act") != from_act
        or last_transition.get("to_act") != to_act
    ):
        history.append(
            {
                "turn": turn.turn_number,
                "from_act": from_act,
                "to_act": to_act,
                "reason": progress["last_advance_reason"],
            }
        )
        del history[:-20]


def _sync_current_act_from_completed_anchors(
    progress: dict[str, Any],
    config: Any,
    completed_anchors: list[Any],
) -> str:
    acts = _script_acts(config)
    act_ids = [_act_identity(act) for act in acts]
    act_ids = [act_id for act_id in act_ids if act_id]
    if not act_ids:
        return _text(progress.get("current_act") or progress.get("act"))

    act_index_by_identifier: dict[str, int] = {}
    anchor_act_index: dict[str, int] = {}
    for index, act in enumerate(acts):
        for identifier in _act_identifiers(act):
            act_index_by_identifier.setdefault(identifier, index)
        for anchor in act.get("completion_anchors") or []:
            for identifier in _anchor_identifiers(anchor):
                anchor_act_index.setdefault(identifier, index)

    current_act = _text(progress.get("current_act") or progress.get("act")) or act_ids[0]
    current_index = act_index_by_identifier.get(current_act)
    furthest_index = current_index if current_index is not None else -1
    for anchor_id in completed_anchors:
        anchor_index = anchor_act_index.get(_identity(anchor_id))
        if anchor_index is not None and anchor_index > furthest_index:
            furthest_index = anchor_index

    if furthest_index < 0:
        progress["current_act"] = current_act
        return current_act

    if current_index is not None and furthest_index <= current_index:
        progress["current_act"] = current_act
        return current_act

    target_act = act_ids[furthest_index]
    completed_acts = progress.setdefault("completed_acts", [])
    if not isinstance(completed_acts, list):
        completed_acts = []
    normalized_completed = [_text(act_id) for act_id in completed_acts if _text(act_id)]
    for act_id in act_ids[:furthest_index]:
        if act_id not in normalized_completed:
            normalized_completed.append(act_id)
    progress["completed_acts"] = normalized_completed
    progress["current_act"] = target_act
    return target_act


def _inferred_completed_anchors(
    config: Any,
    current_act: str,
    completed_anchors: list[Any],
    evidence: Any,
) -> list[tuple[str, str]]:
    if not current_act:
        return []
    completed = {_identity(anchor_id) for anchor_id in completed_anchors if _identity(anchor_id)}
    inferred: list[tuple[str, str]] = []
    for anchor in _completion_anchor_records_for_act(config, current_act, required_only=True):
        anchor_id = _text(anchor.get("id"))
        if not anchor_id or anchor_id in completed:
            continue
        reason = _anchor_completion_reason(anchor, evidence)
        if reason:
            inferred.append((anchor_id, reason))
            completed.add(anchor_id)
    return inferred


def _completion_anchor_records_for_act(
    config: Any,
    act_id: str,
    *,
    required_only: bool,
) -> list[dict[str, Any]]:
    for act in _script_acts(config):
        if act_id not in _act_identifiers(act):
            continue
        anchors = []
        for anchor in act.get("completion_anchors") or []:
            if not isinstance(anchor, dict):
                continue
            if required_only and not _bool(anchor.get("required"), True):
                continue
            anchors.append(anchor)
        return anchors
    return []


def _anchor_completion_reason(anchor: dict[str, Any], evidence: Any) -> str:
    evidence_units = _evidence_units(evidence)
    if not evidence_units:
        return ""

    anchor_text = "\n".join(
        _text(anchor.get(key))
        for key in ("id", "title", "description", "completion_signal")
    )
    exact_matches = [
        _text(anchor.get("completion_signal")),
        _text(anchor.get("title")),
        _text(anchor.get("description")),
    ]
    for unit in evidence_units:
        for phrase in exact_matches:
            if len(phrase) >= 6 and phrase != "未命名锚点" and phrase in unit:
                return f"根据当前状态证据补全：{phrase}"

    phrases = _meaningful_phrases(anchor_text)
    for unit in evidence_units:
        matched = [phrase for phrase in phrases if phrase in unit]
        if len(matched) >= 2 and len(matched) >= max(2, len(phrases) // 2):
            return f"根据当前状态证据补全：{'；'.join(matched[:3])}"

    semantic_text = _text(anchor.get("completion_signal")) or "\n".join(
        _text(anchor.get(key)) for key in ("title", "description")
    )
    for unit in evidence_units:
        semantic_matches = _semantic_completion_matches(semantic_text, unit)
        if semantic_matches:
            return f"根据当前状态证据补全：{'；'.join(semantic_matches[:4])}"

    return ""


def _semantic_completion_matches(source_text: str, evidence: str) -> list[str]:
    evidence_text = _compact_text(evidence)
    if not source_text or not evidence_text:
        return []

    action_terms = _anchor_action_terms(source_text)
    if action_terms and not _anchor_action_evident(action_terms, evidence_text):
        return []

    terms = _anchor_key_terms(source_text)
    if len(terms) < 3:
        if action_terms and terms and all(
            _anchor_key_term_evident(term, evidence_text) for term in terms
        ):
            return terms
        return []

    matched = [term for term in terms if term in evidence_text]
    required = max(3, (len(terms) * 3 + 4) // 5)
    if len(matched) >= required:
        return matched

    ordered_match = _ordered_completion_match(source_text, evidence_text)
    if ordered_match:
        return matched + ordered_match

    if action_terms:
        fuzzy_matched = [
            term for term in terms if _anchor_key_term_evident(term, evidence_text)
        ]
        if len(fuzzy_matched) >= required:
            return fuzzy_matched
    return []


def _anchor_action_terms(value: str) -> list[str]:
    text = _compact_text(value)
    terms: list[str] = []
    for term in ANCHOR_ACTION_TERMS:
        if term in text and term not in terms:
            terms.append(term)
    return terms


def _anchor_action_evident(action_terms: list[str], evidence_text: str) -> bool:
    for term in action_terms:
        equivalents = ANCHOR_ACTION_EQUIVALENTS.get(term, (term,))
        if any(equivalent in evidence_text for equivalent in equivalents):
            return True
    return False


def _anchor_key_terms(value: str) -> list[str]:
    terms: list[str] = []

    def add(term: str) -> None:
        text = _compact_text(term)
        if len(text) < 2 or text in ANCHOR_TERM_STOPWORDS or text in terms:
            return
        if re.fullmatch(r"[A-Za-z0-9_./:]+", text):
            return
        if text in ANCHOR_ACTION_TERMS:
            return
        terms.append(text)

    for phrase in ANCHOR_TERM_SPLIT_RE.split(value):
        text = _compact_text(phrase)
        if not text:
            continue
        add(text)
        if len(text) > 8:
            for size in (4, 3):
                for index in range(0, len(text) - size + 1):
                    fragment = text[index : index + size]
                    if _useful_anchor_fragment(fragment):
                        add(fragment)
    return terms[:18]


def _anchor_key_term_evident(term: str, evidence_text: str) -> bool:
    text = _compact_text(term)
    if not text:
        return False
    if text in evidence_text:
        return True
    if len(text) < 5:
        return False

    unique_chars = list(dict.fromkeys(text))
    matched_chars = [char for char in unique_chars if char in evidence_text]
    required_chars = max(4, (len(unique_chars) * 3 + 3) // 4)
    if len(matched_chars) < required_chars:
        return False

    return any(
        fragment in evidence_text
        for size in (3, 2)
        for fragment in _term_fragments(text, size)
        if _useful_anchor_fragment(fragment) or size == 2
    )


def _term_fragments(text: str, size: int) -> list[str]:
    if len(text) < size:
        return []
    return [text[index : index + size] for index in range(0, len(text) - size + 1)]


def _ordered_completion_match(source_text: str, evidence_text: str) -> list[str]:
    source = _compact_text(source_text)
    if len(source) < 12:
        return []

    evidence_index = 0
    matched = 0
    for char in source:
        found_at = evidence_text.find(char, evidence_index)
        if found_at < 0:
            continue
        matched += 1
        evidence_index = found_at + 1

    required = max(10, (len(source) * 2 + 2) // 3)
    if matched < required:
        return []
    return [source[:20]]


def _useful_anchor_fragment(value: str) -> bool:
    if len(value) < 3 or value in ANCHOR_TERM_STOPWORDS:
        return False
    if value in ANCHOR_ACTION_TERMS:
        return False
    return not any(char.isascii() and char.isalnum() for char in value)


def _compact_text(value: Any) -> str:
    return re.sub(r"[\s,，、。；;：:（）()《》“”\"'——\-_/\\]+", "", _text(value))


def _meaningful_phrases(value: str) -> list[str]:
    phrases: list[str] = []
    for phrase in re.split(r"[\s,，、。；;：:（）()——\-]+", value):
        text = _text(phrase)
        if len(text) < 4 or text in {"未命名锚点", "completion", "signal"}:
            continue
        if text not in phrases:
            phrases.append(text)
    return phrases[:8]


def _sync_main_quests(
    state: dict[str, Any],
    settings: dict[str, Any],
    config: Any,
    current_act: str,
    evidence: str,
    activity_evidence: str,
) -> None:
    main_quests = [
        quest for quest in settings.get("main_quest_path") or [] if isinstance(quest, dict)
    ]
    if not main_quests:
        return

    progress = state.setdefault("story_progress", {})
    if not isinstance(progress, dict):
        progress = {}
        state["story_progress"] = progress

    completed_acts = {_text(act) for act in progress.get("completed_acts") or [] if _text(act)}
    completed_anchors = [
        _identity(anchor_id)
        for anchor_id in progress.get("completed_anchors") or []
        if _identity(anchor_id)
    ]
    completion_evidence = [
        *_evidence_units(evidence),
        *_completed_anchor_evidence_units(config, progress, completed_anchors),
    ]
    ready_for_next = _bool(progress.get("ready_for_next_act"), False)
    current_act_complete = _computed_ready_for_next_act(config, current_act, completed_anchors)
    next_act = transition_target_for_act(config, current_act) if ready_for_next else ""
    first_next_quest_id = _first_quest_id_for_act(main_quests, next_act)
    explicit_by_key = _existing_quest_statuses(state.get("quests"))
    active_quest_ids = _active_quest_ids_for_act(main_quests, current_act, activity_evidence)
    active_quest_ids = {
        quest_id
        for quest_id in active_quest_ids
        if not _quest_id_is_completed(
            main_quests,
            quest_id,
            current_act,
            completed_acts,
            bool(current_act_complete),
            explicit_by_key,
            completion_evidence,
        )
    }
    fallback_current_quest_id = (
        ""
        if active_quest_ids
        else _first_unfinished_quest_id_for_act(
            main_quests,
            current_act,
            current_act,
            completed_acts,
            bool(current_act_complete),
            explicit_by_key,
            completion_evidence,
        )
    )

    derived: list[dict[str, Any]] = []
    derived_keys: set[str] = set()
    for quest in main_quests[:16]:
        quest_id = _text(quest.get("id") or quest.get("key") or quest.get("title"))
        title = _text(quest.get("title") or quest.get("name")) or quest_id
        act_id = _text(quest.get("act_id") or quest.get("act"))
        status = _derived_quest_status(
            quest=quest,
            quest_id=quest_id,
            title=title,
            act_id=act_id,
            current_act=current_act,
            next_act=next_act,
            first_next_quest_id=first_next_quest_id,
            active_quest_ids=active_quest_ids,
            fallback_current_quest_id=fallback_current_quest_id,
            completed_acts=completed_acts,
            current_act_complete=bool(current_act_complete),
            explicit_by_key=explicit_by_key,
            evidence=completion_evidence,
        )
        derived.append(
            {
                "id": quest_id,
                "name": title,
                "title": title,
                "act_id": act_id,
                "status": status,
                "objective": _text(quest.get("objective")),
                "description": _text(quest.get("player_visible")),
                "completion_signal": _text(quest.get("completion_signal")),
                "optional": bool(quest.get("optional")),
                "source": "main_quest_path",
            }
        )
        for key in (quest_id, title):
            if key:
                derived_keys.add(key)
    if not any(item.get("status") == "active" for item in derived) and not bool(
        current_act_complete
    ):
        fallback_anchor_quest = _fallback_anchor_quest(
            config,
            current_act,
            completed_anchors,
        )
        if fallback_anchor_quest:
            derived.append(fallback_anchor_quest)
            for key in (
                fallback_anchor_quest.get("id"),
                fallback_anchor_quest.get("title"),
                fallback_anchor_quest.get("name"),
            ):
                text = _text(key)
                if text:
                    derived_keys.add(text)
    state["quests"] = [*derived, *_preserved_non_main_quests(state.get("quests"), derived_keys)]
    _resolve_completed_main_quest_threads(state)


def _completed_anchor_evidence(
    config: Any,
    progress: dict[str, Any],
    completed_anchors: list[str],
) -> str:
    return "\n".join(_completed_anchor_evidence_units(config, progress, completed_anchors))


def _completed_anchor_evidence_units(
    config: Any,
    progress: dict[str, Any],
    completed_anchors: list[str],
) -> list[str]:
    completed = {_identity(anchor_id) for anchor_id in completed_anchors if _identity(anchor_id)}
    if not completed:
        return []

    units: list[str] = []
    for act in _script_acts(config):
        for anchor in act.get("completion_anchors") or []:
            if not isinstance(anchor, dict):
                continue
            anchor_id = _text(anchor.get("id"))
            if anchor_id not in completed:
                continue
            parts: list[str] = []
            for key in ("id", "title", "description", "completion_signal"):
                value = _text(anchor.get(key))
                if value:
                    parts.append(value)
            _append_evidence_unit(units, "\n".join(parts))

    history = progress.get("anchor_history")
    if isinstance(history, list):
        for item in history:
            if not isinstance(item, dict):
                continue
            if _identity(item.get("anchor_id")) not in completed:
                continue
            parts = []
            for key in ("act", "anchor_id", "reason"):
                value = _text(item.get(key))
                if value:
                    parts.append(value)
            _append_evidence_unit(units, "\n".join(parts))
    return units


def _fallback_anchor_quest(
    config: Any,
    current_act: str,
    completed_anchors: list[str],
) -> dict[str, Any] | None:
    completed = {_identity(anchor_id) for anchor_id in completed_anchors if _identity(anchor_id)}
    for anchor in _completion_anchor_records_for_act(config, current_act, required_only=True):
        anchor_id = _text(anchor.get("id"))
        if not anchor_id or anchor_id in completed:
            continue
        title = _anchor_quest_title(anchor, anchor_id)
        completion_signal = _text(anchor.get("completion_signal"))
        return {
            "id": f"anchor_quest_{anchor_id}",
            "name": title,
            "title": title,
            "act_id": current_act,
            "status": "active",
            "objective": completion_signal or title,
            "description": "当前幕仍有必需剧情锚点未完成。",
            "completion_signal": completion_signal,
            "optional": False,
            "source": "completion_anchor",
            "anchor_id": anchor_id,
        }
    return None


def _anchor_quest_title(anchor: dict[str, Any], anchor_id: str) -> str:
    title = _text(anchor.get("title"))
    if title and title != "未命名锚点":
        return title
    signal = _text(anchor.get("completion_signal"))
    if signal:
        for separator in ("——", "。", "；", ";"):
            if separator in signal:
                signal = signal.split(separator, 1)[0]
                break
        signal = signal.strip(" ，,。；;")
        if signal:
            return signal
    return f"推进当前幕：{anchor_id}"


def _resolve_completed_anchor_threads(
    state: dict[str, Any],
    config: Any,
    completed_anchors: list[Any],
) -> None:
    anchors = _completed_anchor_thread_records(config, completed_anchors)
    if not anchors:
        return

    for thread in state.get("open_threads") or []:
        if not isinstance(thread, dict):
            continue
        status = _text(thread.get("status") or thread.get("state")).lower()
        if _thread_action_resolves(status) or status in {"resolved", "closed", "completed"}:
            continue
        if any(_thread_matches_completed_anchor(thread, anchor) for anchor in anchors):
            thread["status"] = "resolved"


def _completed_anchor_thread_records(
    config: Any,
    completed_anchors: list[Any],
) -> list[dict[str, Any]]:
    completed = {_identity(anchor_id) for anchor_id in completed_anchors if _identity(anchor_id)}
    if not completed:
        return []

    records: list[dict[str, Any]] = [{"id": anchor_id} for anchor_id in completed]
    for act in _script_acts(config):
        for anchor in act.get("completion_anchors") or []:
            if not isinstance(anchor, dict):
                continue
            anchor_id = _text(anchor.get("id"))
            if anchor_id not in completed:
                continue
            records.append(
                {
                    "id": anchor_id,
                    "title": anchor.get("title"),
                    "description": anchor.get("description"),
                    "completion_signal": anchor.get("completion_signal"),
                }
            )
    return records


def _thread_matches_completed_anchor(
    thread: dict[str, Any],
    anchor: dict[str, Any],
) -> bool:
    thread_values = {
        _identity(thread.get(key))
        for key in ("id", "key", "title", "name", "anchor_id")
        if _identity(thread.get(key))
    }
    anchor_values = {
        _identity(anchor.get(key))
        for key in ("id", "key", "title", "name", "anchor_id")
        if _identity(anchor.get(key)) and not _is_placeholder(anchor.get(key))
    }
    if thread_values.intersection(anchor_values):
        return True

    thread_topics = {
        topic
        for key in ("title", "name")
        if (topic := _quest_thread_topic(_text(thread.get(key))))
    }
    anchor_topics = {
        topic
        for key in ("title", "description", "completion_signal")
        if (topic := _quest_thread_topic(_text(anchor.get(key))))
    }
    return bool(thread_topics.intersection(anchor_topics))


def _resolve_completed_main_quest_threads(state: dict[str, Any]) -> None:
    quests = [
        quest
        for quest in state.get("quests") or []
        if isinstance(quest, dict)
        and quest.get("source") == "main_quest_path"
        and _quest_status_bucket(_text(quest.get("status"))) == "completed"
    ]
    if not quests:
        return
    for thread in state.get("open_threads") or []:
        if not isinstance(thread, dict):
            continue
        status = _text(thread.get("status") or thread.get("state")).lower()
        if _thread_action_resolves(status) or status in {"resolved", "closed", "completed"}:
            continue
        if any(_thread_matches_completed_quest(thread, quest) for quest in quests):
            thread["status"] = "resolved"


def _thread_matches_completed_quest(thread: dict[str, Any], quest: dict[str, Any]) -> bool:
    thread_values = {
        _text(thread.get(key))
        for key in ("id", "key", "title", "name")
        if _text(thread.get(key))
    }
    quest_values = {
        _text(quest.get(key))
        for key in ("id", "key", "title", "name")
        if _text(quest.get(key))
    }
    if thread_values.intersection(quest_values):
        return True

    thread_topics = {
        topic
        for key in ("title", "name")
        if (topic := _quest_thread_topic(_text(thread.get(key))))
    }
    quest_topics = {
        topic
        for key in ("title", "name")
        if (topic := _quest_thread_topic(_text(quest.get(key))))
    }
    return bool(thread_topics.intersection(quest_topics))


def _quest_thread_topic(value: str) -> str:
    topic = re.sub(r"[\s,，、。；;：:（）()——\-]+", "", _text(value))
    for prefix in THREAD_QUEST_TOPIC_PREFIXES:
        if topic.startswith(prefix):
            topic = topic[len(prefix) :]
            break
    for suffix in ("线索", "任务", "事件", "线", "发现", "完成"):
        if topic.endswith(suffix):
            topic = topic[: -len(suffix)]
            break
    return topic if 2 <= len(topic) <= 12 else ""


def _derived_quest_status(
    *,
    quest: dict[str, Any],
    quest_id: str,
    title: str,
    act_id: str,
    current_act: str,
    next_act: str,
    first_next_quest_id: str,
    active_quest_ids: set[str],
    fallback_current_quest_id: str,
    completed_acts: set[str],
    current_act_complete: bool,
    explicit_by_key: dict[str, str],
    evidence: str,
) -> str:
    explicit = explicit_by_key.get(quest_id) or explicit_by_key.get(title)
    explicit_bucket = _quest_status_bucket(explicit)
    if explicit_bucket == "failed":
        return "failed"
    if act_id in completed_acts:
        return "completed"
    can_complete_from_current_evidence = _quest_can_complete_from_current_evidence(
        quest_id=quest_id,
        act_id=act_id,
        current_act=current_act,
        next_act=next_act,
        first_next_quest_id=first_next_quest_id,
    )
    if explicit_bucket == "completed" and can_complete_from_current_evidence:
        return "completed"
    if can_complete_from_current_evidence and _quest_completion_evident(quest, evidence):
        return "completed"
    if act_id == current_act and current_act_complete:
        return "completed"
    if quest_id in active_quest_ids:
        return "active"
    if next_act and act_id == next_act and quest_id == first_next_quest_id:
        return "active"
    if act_id == current_act:
        return "active" if quest_id == fallback_current_quest_id else "hidden"
    return "hidden"


def _quest_can_complete_from_current_evidence(
    *,
    quest_id: str,
    act_id: str,
    current_act: str,
    next_act: str,
    first_next_quest_id: str,
) -> bool:
    if not act_id:
        return False
    if act_id == current_act:
        return True
    return bool(next_act and act_id == next_act and quest_id == first_next_quest_id)


def _act_activity_evident(
    settings: dict[str, Any],
    act_id: str,
    activity_evidence: str,
) -> bool:
    if not act_id or not activity_evidence:
        return False
    for quest in settings.get("main_quest_path") or []:
        if not isinstance(quest, dict):
            continue
        if _text(quest.get("act_id") or quest.get("act")) != act_id:
            continue
        if _quest_activity_evident(quest, activity_evidence):
            return True
    for act in settings.get("act_plan") or []:
        if not isinstance(act, dict) or act_id not in _act_identifiers(act):
            continue
        act_text = "\n".join(
            _text(act.get(key))
            for key in ("title", "objective", "dramatic_question", "pressure")
        )
        if _activity_text_matches(act_text, activity_evidence):
            return True
        for anchor in act.get("completion_anchors") or []:
            if isinstance(anchor, dict) and _activity_text_matches(
                "\n".join(
                    _text(anchor.get(key))
                    for key in ("title", "description", "completion_signal")
                ),
                activity_evidence,
            ):
                return True
    return False


def _active_quest_ids_for_act(
    quests: list[dict[str, Any]],
    act_id: str,
    activity_evidence: str,
) -> set[str]:
    active: set[str] = set()
    if not act_id:
        return active
    for quest in quests:
        if _text(quest.get("act_id") or quest.get("act")) != act_id:
            continue
        if _quest_activity_evident(quest, activity_evidence):
            quest_id = _text(quest.get("id") or quest.get("key") or quest.get("title"))
            if quest_id:
                active.add(quest_id)
    return active


def _quest_id_is_completed(
    quests: list[dict[str, Any]],
    quest_id: str,
    current_act: str,
    completed_acts: set[str],
    current_act_complete: bool,
    explicit_by_key: dict[str, str],
    evidence: Any,
) -> bool:
    for quest in quests:
        current_quest_id = _text(quest.get("id") or quest.get("key") or quest.get("title"))
        if current_quest_id != quest_id:
            continue
        title = _text(quest.get("title") or quest.get("name")) or current_quest_id
        act_id = _text(quest.get("act_id") or quest.get("act"))
        return _quest_is_completed(
            quest,
            current_quest_id,
            title,
            act_id,
            current_act,
            completed_acts,
            current_act_complete,
            explicit_by_key,
            evidence,
        )
    return False


def _first_unfinished_quest_id_for_act(
    quests: list[dict[str, Any]],
    act_id: str,
    current_act: str,
    completed_acts: set[str],
    current_act_complete: bool,
    explicit_by_key: dict[str, str],
    evidence: Any,
) -> str:
    if not act_id or current_act_complete:
        return ""
    for quest in quests:
        if _text(quest.get("act_id") or quest.get("act")) != act_id:
            continue
        quest_id = _text(quest.get("id") or quest.get("key") or quest.get("title"))
        if not quest_id:
            continue
        title = _text(quest.get("title") or quest.get("name")) or quest_id
        if not _quest_is_completed(
            quest,
            quest_id,
            title,
            act_id,
            current_act,
            completed_acts,
            current_act_complete,
            explicit_by_key,
            evidence,
        ):
            return quest_id
    return ""


def _quest_is_completed(
    quest: dict[str, Any],
    quest_id: str,
    title: str,
    act_id: str,
    current_act: str,
    completed_acts: set[str],
    current_act_complete: bool,
    explicit_by_key: dict[str, str],
    evidence: Any,
) -> bool:
    explicit = explicit_by_key.get(quest_id) or explicit_by_key.get(title)
    explicit_bucket = _quest_status_bucket(explicit)
    if explicit_bucket == "completed" and act_id == current_act:
        return True
    if act_id in completed_acts:
        return True
    if act_id == current_act and _quest_completion_evident(quest, evidence):
        return True
    return bool(current_act_complete and act_id == current_act)


def _quest_activity_evident(quest: dict[str, Any], activity_evidence: str) -> bool:
    quest_text = "\n".join(
        _text(quest.get(key))
        for key in ("title", "objective", "player_visible", "description", "completion_signal")
    )
    return _activity_text_matches(quest_text, activity_evidence)


def _activity_text_matches(source_text: str, activity_evidence: str) -> bool:
    if not source_text or not activity_evidence:
        return False

    for phrase in _meaningful_phrases(source_text):
        if len(phrase) >= 6 and phrase in activity_evidence:
            return True

    markers = _activity_markers(source_text)
    matched = [marker for marker in markers if marker in activity_evidence]
    return len(matched) >= 2


def _activity_markers(value: str) -> list[str]:
    markers: list[str] = []

    def add(marker: str) -> None:
        marker = _text(marker)
        if len(marker) < 2 or marker in ACTIVITY_MARKER_STOPWORDS or marker in markers:
            return
        markers.append(marker)

    def add_variants(text: str) -> None:
        add(text)
        for prefix in THREAD_QUEST_TOPIC_PREFIXES:
            if text.startswith(prefix):
                add(text[len(prefix) :])
                break
        if re.fullmatch(r"[\u4e00-\u9fff]{2,5}", text):
            add(text[-2:])
            add(text[-3:])

    for phrase in re.split(r"[\s,，、。；;：:（）()——\-及和与]+", value):
        text = _text(phrase)
        if not text:
            continue
        if 2 <= len(text) <= 8:
            add_variants(text)
        for prefix in THREAD_QUEST_TOPIC_PREFIXES:
            if not text.startswith(prefix):
                continue
            stripped = text[len(prefix) :]
            if 2 <= len(stripped) <= 8:
                add_variants(stripped)
            break

    return markers[:18]


def _quest_completion_evident(quest: dict[str, Any], evidence: Any) -> bool:
    phrase = _text(quest.get("completion_signal"))
    if len(phrase) < 6 or not evidence:
        return False
    evidence_units = _evidence_units(evidence)
    for unit in evidence_units:
        if phrase in unit:
            return True
        if any(len(item) >= 6 and item in unit for item in _meaningful_phrases(phrase)):
            return True
        if _semantic_completion_matches(phrase, unit):
            return True
    markers = _activity_markers(phrase)
    for unit in evidence_units:
        matched = [marker for marker in markers if marker in unit]
        if len(matched) >= max(3, min(4, len(markers))):
            return True
    return False


def _existing_quest_statuses(value: Any) -> dict[str, str]:
    statuses: dict[str, str] = {}
    if not isinstance(value, list):
        return statuses
    for item in value:
        if not isinstance(item, dict):
            continue
        if item.get("source") in DERIVED_QUEST_SOURCES:
            continue
        status = _text(item.get("status") or item.get("state") or item.get("new_status"))
        if not status:
            continue
        for key in ("id", "key", "title", "name"):
            identity = _text(item.get(key))
            if identity and identity not in statuses:
                statuses[identity] = status
    return statuses


def _preserved_non_main_quests(value: Any, main_quest_keys: set[str]) -> list[Any]:
    preserved: list[Any] = []
    if not isinstance(value, list):
        return preserved
    for item in value:
        if isinstance(item, dict):
            if item.get("source") in DERIVED_QUEST_SOURCES:
                continue
            identities = {
                _text(item.get(key))
                for key in ("id", "key", "title", "name")
                if _text(item.get(key))
            }
            if identities.intersection(main_quest_keys):
                continue
            preserved.append(deepcopy(item))
            continue
        identity = _identity(item)
        if identity and identity in main_quest_keys:
            continue
        preserved.append(deepcopy(item))
    return preserved


def _quest_status_bucket(status: str) -> str:
    text = _text(status).lower()
    if any(marker in text for marker in ("失败", "放弃", "failed")):
        return "failed"
    if any(marker in text for marker in ("完成", "解决", "closed", "complete", "done")):
        return "completed"
    return ""


def _first_quest_id_for_act(quests: list[dict[str, Any]], act_id: str) -> str:
    if not act_id:
        return ""
    for quest in quests:
        if _text(quest.get("act_id") or quest.get("act")) == act_id:
            return _text(quest.get("id") or quest.get("key") or quest.get("title"))
    return ""


def _state_evidence_text(state: dict[str, Any]) -> str:
    return "\n".join(_state_evidence_units(state))


def _state_evidence_units(state: dict[str, Any]) -> list[str]:
    units: list[str] = []
    if not isinstance(state, dict):
        return _evidence_units(state)
    for key, value in state.items():
        if key in STATE_EVIDENCE_EXCLUDED_KEYS:
            continue
        _collect_state_evidence_units(value, units, key=key)
    return units


def _collect_state_evidence_units(value: Any, units: list[str], *, key: str = "") -> None:
    if key in STATE_EVIDENCE_EXCLUDED_KEYS:
        return
    if isinstance(value, dict):
        parts: list[str] = []
        _collect_record_evidence_text(value, parts)
        _append_evidence_unit(units, "\n".join(parts))
        return
    if isinstance(value, list):
        for item in value:
            _collect_state_evidence_units(item, units, key=key)
        return
    _append_evidence_unit(units, value)


def _collect_record_evidence_text(value: Any, parts: list[str], *, key: str = "") -> None:
    if key in STATE_EVIDENCE_EXCLUDED_KEYS:
        return
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _collect_record_evidence_text(child_value, parts, key=str(child_key))
        return
    if isinstance(value, list):
        for item in value:
            _collect_record_evidence_text(item, parts, key=key)
        return
    text = _text(value)
    if text:
        parts.append(text)


def _evidence_units(value: Any) -> list[str]:
    if isinstance(value, list):
        units: list[str] = []
        for item in value:
            _append_evidence_unit(units, item)
        return units
    text = _text(value)
    if not text:
        return []
    return [_text(unit) for unit in text.splitlines() if _text(unit)]


def _append_evidence_unit(units: list[str], value: Any) -> None:
    text = _text(value)
    if not text:
        return
    for unit in text.splitlines():
        unit_text = _text(unit)
        if unit_text:
            units.append(unit_text)


def _state_activity_text(state: dict[str, Any]) -> str:
    parts: list[str] = []

    def add(value: Any) -> None:
        text = _text(value)
        if text:
            parts.append(text)

    location = state.get("location")
    if isinstance(location, dict):
        for key in ("current", "name", "to", "from"):
            add(location.get(key))
    else:
        add(location)

    for thread in state.get("open_threads") or []:
        if not isinstance(thread, dict):
            add(thread)
            continue
        status = _text(thread.get("status") or thread.get("state")).lower()
        if _thread_action_resolves(status) or status in {"resolved", "closed", "completed"}:
            continue
        for key in ("title", "name", "description", "status"):
            add(thread.get(key))

    known_facts = state.get("known_facts")
    if isinstance(known_facts, list):
        for fact in known_facts[-24:]:
            add(fact)

    for npc in state.get("npcs") or []:
        if not isinstance(npc, dict):
            continue
        for key in ("name", "location", "current_location", "status", "state", "attitude"):
            add(npc.get(key))

    return "\n".join(parts)


def _act_list(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _identity_list(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return [_identity(item) for item in value if _identity(item)]
    text = _identity(value)
    return [text] if text else []


def _identity(value: Any) -> str:
    if isinstance(value, dict):
        return _text(value.get("id") or value.get("key") or value.get("name") or value.get("title"))
    return _text(value)


def _computed_ready_for_next_act(
    config: Any,
    current_act: str,
    completed_anchors: list[Any],
) -> bool | None:
    required_anchor_ids = completion_anchor_ids_for_act(config, current_act, required_only=True)
    if not required_anchor_ids:
        return None
    completed = {_identity(anchor_id) for anchor_id in completed_anchors if _identity(anchor_id)}
    return all(anchor_id in completed for anchor_id in required_anchor_ids)


def _can_advance_to_act(
    config: Any,
    previous_act: str,
    next_act: str,
    completed_anchors: list[Any],
) -> bool:
    if not next_act:
        return False
    if next_act == previous_act:
        return True
    if not previous_act:
        return not _script_acts(config) or _act_exists(config, next_act)

    allowed_targets = _allowed_transition_targets(config, previous_act)
    if allowed_targets and next_act not in allowed_targets:
        return False
    if not allowed_targets and _act_exists(config, previous_act):
        return False

    required_anchor_ids = completion_anchor_ids_for_act(config, previous_act, required_only=True)
    completed = {_identity(anchor_id) for anchor_id in completed_anchors if _identity(anchor_id)}
    return all(anchor_id in completed for anchor_id in required_anchor_ids)


def _allowed_transition_targets(config: Any, current_act: str) -> set[str]:
    targets: set[str] = set()
    transition_target = transition_target_for_act(config, current_act)
    if transition_target:
        targets.add(transition_target)
    adjacent_next = _adjacent_next_act(config, current_act)
    if adjacent_next:
        targets.add(adjacent_next)
    return targets


def _adjacent_next_act(config: Any, current_act: str) -> str:
    acts = _script_acts(config)
    for index, act in enumerate(acts):
        if current_act not in _act_identifiers(act):
            continue
        for next_act in acts[index + 1:]:
            next_id = _act_identity(next_act)
            if next_id:
                return next_id
        return ""
    return ""


def _act_exists(config: Any, act_id: str) -> bool:
    return any(act_id in _act_identifiers(act) for act in _script_acts(config))


def _script_acts(config: Any) -> list[dict[str, Any]]:
    settings = getattr(config, "story_settings", None)
    if not isinstance(settings, dict):
        return []
    return [item for item in settings.get("act_plan") or [] if isinstance(item, dict)]


def _configured_current_act(config: Any) -> str:
    settings = getattr(config, "story_settings", None)
    if not isinstance(settings, dict):
        return ""
    core = settings.get("story_core")
    return _text(core.get("current_act")) if isinstance(core, dict) else ""


def _act_identity(act: dict[str, Any]) -> str:
    identifiers = _act_identifiers(act)
    return identifiers[0] if identifiers else ""


def _act_identifiers(act: dict[str, Any]) -> list[str]:
    identifiers = [
        _text(act.get("id")),
        _text(act.get("key")),
        _text(act.get("name")),
        _text(act.get("title")),
    ]
    return [identifier for identifier in identifiers if identifier]


def _anchor_identifiers(anchor: Any) -> list[str]:
    if not isinstance(anchor, dict):
        identifier = _identity(anchor)
        return [identifier] if identifier else []
    identifiers = [
        _text(anchor.get("id")),
        _text(anchor.get("key")),
        _text(anchor.get("name")),
        _text(anchor.get("title")),
    ]
    return [identifier for identifier in identifiers if identifier]


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is not None and not isinstance(value, (dict, list)):
        return str(value).strip()
    return ""


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
