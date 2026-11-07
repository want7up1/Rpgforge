"""Request-scoped story indexes and the shared AND/OR completion contract.

This module has no ORM, model calls or global cache. Rebuild an index when the
effective story changes; historical deltas intentionally use today's settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def identity(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("id") or value.get("key") or value.get("name") or value.get("title")
    return str(value).strip() if value is not None else ""


def required(anchor: dict[str, Any]) -> bool:
    value = anchor.get("required")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", ""}
    return True if value is None else bool(value)


def alternative_group(anchor: dict[str, Any]) -> str:
    return identity(
        anchor.get("alternative_group") or anchor.get("alt_group")
        or anchor.get("alternativeGroup")
    )


def required_anchor_groups(anchors: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """AND across requirements, OR within one alternative_group; keep author order."""
    groups: list[list[dict[str, Any]]] = []
    alternatives: dict[str, list[dict[str, Any]]] = {}
    for anchor in anchors:
        if not required(anchor) or not identity(anchor):
            continue
        group_id = alternative_group(anchor)
        if not group_id:
            groups.append([anchor])
        elif group_id in alternatives:
            alternatives[group_id].append(anchor)
        else:
            alternatives[group_id] = [anchor]
            groups.append(alternatives[group_id])
    return groups


def open_completion_anchors(
    anchors: list[dict[str, Any]], completed: set[str],
) -> list[dict[str, Any]]:
    satisfied = {
        alternative_group(anchor) for anchor in anchors
        if required(anchor) and alternative_group(anchor) and identity(anchor) in completed
    }
    return [
        anchor for anchor in anchors
        if identity(anchor) not in completed
        and not (required(anchor) and alternative_group(anchor) in satisfied)
    ]


def budget_completion_anchors(
    anchors: list[dict[str, Any]], limit: int,
) -> list[dict[str, Any]]:
    """Budget optional material only: mandatory completion gates must stay visible."""
    optional_budget = max(0, limit - sum(required(anchor) for anchor in anchors))
    result = []
    for anchor in anchors:
        if required(anchor):
            result.append(anchor)
        elif optional_budget:
            result.append(anchor)
            optional_budget -= 1
    return result


@dataclass
class ProgressRules:
    story_settings: dict[str, Any]
    acts: list[dict[str, Any]] = field(init=False)
    act_by_identifier: dict[str, dict[str, Any]] = field(init=False, default_factory=dict)
    act_index: dict[str, int] = field(init=False, default_factory=dict)
    anchor_act_index: dict[str, int] = field(init=False, default_factory=dict)
    anchors_by_act: dict[str, list[dict[str, Any]]] = field(init=False, default_factory=dict)
    requirements_by_act: dict[str, list[list[str]]] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self.acts = [a for a in self.story_settings.get("act_plan", []) if isinstance(a, dict)]
        for index, act in enumerate(self.acts):
            anchors = [a for a in act.get("completion_anchors", []) if isinstance(a, dict)]
            requirements = [[identity(a) for a in g] for g in required_anchor_groups(anchors)]
            for key in identifiers(act):
                self.act_by_identifier.setdefault(key, act)
                self.act_index.setdefault(key, index)
                self.anchors_by_act.setdefault(key, anchors)
                self.requirements_by_act.setdefault(key, requirements)
            for anchor in anchors:
                for key in identifiers(anchor):
                    self.anchor_act_index.setdefault(key, index)

    def anchors(self, act_id: str, *, required_only: bool = False) -> list[dict[str, Any]]:
        anchors = self.anchors_by_act.get(act_id, [])
        return [a for a in anchors if required(a)] if required_only else anchors

    def requirements(self, act_id: str) -> list[list[str]]:
        return self.requirements_by_act.get(act_id, [])

    def progress(self, act_id: str, completed: list[Any] | set[str]) -> dict[str, int]:
        completed_ids = {identity(a) for a in completed}
        requirements = self.requirements(act_id)
        return {
            "done": sum(any(a in completed_ids for a in group) for group in requirements),
            "total": len(requirements),
        }

    def ready(self, act_id: str, completed: list[Any]) -> bool | None:
        progress = self.progress(act_id, completed)
        return progress["done"] == progress["total"] if progress["total"] else None

    def adjacent(self, act_id: str) -> str:
        index = self.act_index.get(act_id)
        if index is None or index + 1 >= len(self.acts):
            return ""
        return identity(self.acts[index + 1])

    def transition_target(self, act_id: str) -> str:
        act = self.act_by_identifier.get(act_id, {})
        transition = act.get("transition_to_next_act")
        transition = transition if isinstance(transition, dict) else {}
        return identity(
            transition.get("target_act") or transition.get("to_act")
            or transition.get("act_id") or transition.get("id")
        ) or self.adjacent(act_id)


def identifiers(record: dict[str, Any]) -> list[str]:
    return [identity(record.get(k)) for k in ("id", "key", "name", "title") if record.get(k)]
