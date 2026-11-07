"""Player-visible receipts from applied state, independent of model requests and IO."""

from __future__ import annotations

from typing import Any

from app.services.state_v2 import (
    _player_visible,
    _thread_log,
    hidden_npc_references,
    inherit_npc_visibility,
    state_v2_view,
)


def build_settlement_receipt(
    before_state: dict[str, Any],
    after_state: dict[str, Any],
    delta: dict[str, Any],
    *,
    turn_number: int,
    status: str = "confirmed",
    message: str = "",
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "version": 1,
        "status": status,
        "turn_number": turn_number,
        "sections": [],
    }
    if message:
        receipt["message"] = message
    if status != "confirmed":
        return receipt

    before = _view(before_state)
    after = _view(after_state)
    sections = receipt["sections"]
    _append(sections, "progress", "主线进展", _progress_changes(before, after, turn_number))
    for key, label, identity in (
        ("conditions", "处境", "name"),
        ("relationship_tracks", "人物关系", "npc"),
        ("inventory", "随身物品", "name"),
    ):
        _append(
            sections, key, label, _collection_changes(before.get(key), after.get(key), identity)
        )

    for key, label, buckets in (
        ("quest_log", "任务", ("active", "completed", "failed", "hidden")),
        ("open_threads", "线索", ("active", "resolved")),
    ):
        old = _flatten(before.get(key), buckets)
        new = _flatten(after.get(key), buckets)
        _append(sections, key, label, _collection_changes(old, new, "id"))

    scene_changes = []
    old_scene, new_scene = before.get("active_scene", {}), after.get("active_scene", {})
    for key, label in (("location", "地点"), ("time", "时间"), ("pressure", "局面")):
        old, new = _text(old_scene.get(key)), _text(new_scene.get(key))
        if old != new:
            scene_changes.append(_change(label, old, new))
    _append(sections, "scene", "当前局面", scene_changes)
    old_facts = {_text(fact) for fact in before_state.get("known_facts", []) or []}
    facts = [
        _change("已知事实", "", _text(fact))
        for fact in after_state.get("known_facts", []) or []
        if _text(fact) and _text(fact) not in old_facts and _player_visible(fact)
    ]
    _append(sections, "facts", "新发现", facts)
    return receipt


def _view(state: dict[str, Any]) -> dict[str, Any]:
    v2 = state.get("v2")
    if not isinstance(v2, dict) or "inventory" not in v2:
        v2 = state_v2_view(state)
    # Canonical NPCs also protect legacy v2 records that lost visibility/aliases.
    npcs = state.get("npcs")
    if not isinstance(npcs, list):
        npcs = v2.get("npc_registry")
    # UI budgets must never turn a still-existing fact into an apparent removal.
    return {
        **v2,
        "relationship_tracks": inherit_npc_visibility(
            v2.get("relationship_tracks"), hidden_npc_references(npcs)
        ),
        "open_threads": _thread_log(state.get("open_threads"), limit=None),
    }


def _collection_changes(old: Any, new: Any, identity: str) -> list[dict[str, str]]:
    previous = {_key(item, identity): item for item in old or [] if isinstance(item, dict)}
    current = {_key(item, identity): item for item in new or [] if isinstance(item, dict)}
    changes = []
    for key in dict.fromkeys([*previous, *current]):
        if not key:
            continue
        a, b = previous.get(key, {}), current.get(key, {})
        if (b and not _player_visible(b)) or (not b and not _player_visible(a)):
            continue
        visible_before = bool(a) and _player_visible(a)
        before, after = _description(a), _description(b)
        if before != after or bool(a) != bool(b):
            subject = _text(
                (b or a).get("npc") or (b or a).get("name") or (b or a).get("title") or key
            )
            changes.append(
                _change(
                    subject,
                    before if visible_before else "未记录",
                    after if b else "已解除/失去",
                    _text(b.get("note") or b.get("source")),
                )
            )
    return changes


def _key(item: dict[str, Any], identity: str) -> str:
    name = _text(item.get(identity) or item.get("name") or item.get("title"))
    return name + (f"/{item['unit']}" if item.get("unit") else "")


def _description(item: dict[str, Any]) -> str:
    parts = [_text(item.get(key)) for key in ("status", "note", "objective", "description")]
    if "quantity" in item:
        parts.append(f"数量 {item['quantity']}{item.get('unit', '')}")
    return " · ".join(dict.fromkeys(part for part in parts if part)) or ("持有" if item else "")


def _flatten(value: Any, buckets: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    return [
        dict(item, status=item.get("status") or bucket)
        for bucket in buckets
        for item in value.get(bucket, [])
        if isinstance(item, dict)
    ]


def _progress_changes(before: dict, after: dict, turn_number: int) -> list[dict[str, str]]:
    old, new = before.get("story_progress", {}), after.get("story_progress", {})
    changes = []
    added = set(new.get("completed_anchors", [])) - set(old.get("completed_anchors", []))
    if added:
        reasons = [
            item.get("reason", "")
            for item in new.get("anchor_history", [])
            if item.get("anchor_id") in added and item.get("turn") == turn_number
        ]
        changes.append(
            _change(
                "目标推进",
                "",
                f"确认完成 {len(added)} 项剧情条件",
                "；".join(dict.fromkeys(filter(None, reasons))),
            )
        )
    if old.get("current_act") != new.get("current_act"):
        changes.append(
            _change(
                "当前幕",
                _text(old.get("current_act_title") or old.get("current_act")),
                _text(new.get("current_act_title") or new.get("current_act")),
                _text(new.get("last_advance_reason")),
            )
        )
    for key, label in (("campaign_complete", "主线完成"), ("defeat", "旅程终止")):
        if new.get(key) and not old.get(key):
            changes.append(_change(label, "进行中", "已达成"))
    return changes


def _append(sections: list, key: str, label: str, changes: list) -> None:
    if changes:
        sections.append({"key": key, "label": label, "changes": changes})


def _change(subject: str, before: str, after: str, reason: str = "") -> dict[str, str]:
    return {"subject": subject, "before": before, "after": after, "reason": reason}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
