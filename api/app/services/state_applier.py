from copy import deepcopy
from typing import Any

from app.models.state import GameState
from app.models.turn import Turn
from app.services.quantified_state import apply_quantified_state_events
from app.services.state_v2 import normalize_state_v2
from app.services.story_settings import completion_anchor_ids_for_act, transition_target_for_act


def apply_state_delta(
    current_state: GameState,
    turn: Turn,
    delta: dict[str, Any],
) -> dict[str, Any]:
    state = deepcopy(current_state.state_json or {})
    state["current_turn"] = max(int(state.get("current_turn") or 0), turn.turn_number)

    _apply_time(state, delta)
    _apply_location(state, delta)
    _apply_inventory(state, delta)
    _apply_upserts(state, "npcs", delta.get("npc_updates", []))
    _apply_upserts(state, "quests", delta.get("quest_updates", []))
    _apply_upserts(state, "factions", delta.get("faction_updates", []))
    _merge_mapping(state, "protagonist", delta.get("protagonist_updates", {}))
    _merge_mapping(state, "variables", delta.get("variable_updates", {}))
    _append_unique(state, "known_facts", delta.get("new_known_facts", []))
    _append_unique(state, "hidden_facts", delta.get("new_hidden_facts", []))
    _append_unique(state, "open_threads", delta.get("open_thread_updates", []))
    config = getattr(getattr(current_state, "game", None), "config", None)
    _apply_story_progress(state, turn, delta.get("story_progress_update", {}), config)
    apply_quantified_state_events(state, delta)
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

    if isinstance(location_change, dict):
        current = location_change.get("current") or location_change.get("name")
        location_state.update(location_change)
    else:
        current = str(location_change)
        location_state["current"] = current

    known = location_state.setdefault("known_locations", [])
    if current and isinstance(known, list) and current not in known:
        known.append(current)


def _apply_inventory(state: dict[str, Any], delta: dict[str, Any]) -> None:
    inventory = state.setdefault("inventory", [])
    if not isinstance(inventory, list):
        inventory = []
        state["inventory"] = inventory

    for item in delta.get("inventory_add", []) or []:
        if item not in inventory:
            inventory.append(item)

    for item in delta.get("inventory_remove", []) or []:
        _remove_inventory_item(inventory, item)


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
        identifier = update.get("id") or update.get("name")
        if identifier is None:
            collection.append(update)
            continue
        existing = next(
            (
                item
                for item in collection
                if isinstance(item, dict)
                and (item.get("id") == identifier or item.get("name") == identifier)
            ),
            None,
        )
        if existing is None:
            collection.append(update)
        else:
            existing.update(update)


def _merge_mapping(state: dict[str, Any], key: str, updates: dict[str, Any]) -> None:
    if not updates:
        return
    target = state.setdefault(key, {})
    if not isinstance(target, dict):
        target = {}
        state[key] = target
    target.update(updates)


def _append_unique(state: dict[str, Any], key: str, values: list[Any]) -> None:
    target = state.setdefault(key, [])
    if not isinstance(target, list):
        target = []
        state[key] = target
    for value in values or []:
        if value not in target:
            target.append(value)


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
