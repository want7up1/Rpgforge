from copy import deepcopy
from typing import Any

from app.models.state import GameState
from app.models.turn import Turn
from app.services.quantified_state import apply_quantified_state_events
from app.services.state_v2 import normalize_state_v2


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
