"""Normalize legacy string act transitions.

Revision ID: 20260520_0022
Revises: 20260520_0021
Create Date: 2026-05-20 19:45:00.000000
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20260520_0022"
down_revision = "20260520_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, script_outline FROM game_configs")).mappings()
    for row in rows:
        script_outline = row["script_outline"]
        if isinstance(script_outline, str):
            script_outline = json.loads(script_outline)
        if not isinstance(script_outline, dict):
            continue
        normalized, changed = _normalize_act_transitions(script_outline)
        if not changed:
            continue
        connection.execute(
            sa.text(
                """
                UPDATE game_configs
                SET script_outline = CAST(:script_outline AS JSONB)
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "script_outline": json.dumps(normalized, ensure_ascii=False),
            },
        )


def downgrade() -> None:
    # Lossless downgrade is not possible: legacy string transitions are expanded into objects.
    pass


def _normalize_act_transitions(script_outline: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    script = dict(script_outline)
    acts = script.get("acts")
    if not isinstance(acts, list):
        return script, False

    changed = False
    normalized_acts: list[Any] = []
    for index, act_item in enumerate(acts):
        if not isinstance(act_item, dict):
            normalized_acts.append(act_item)
            continue
        act = dict(act_item)
        if "transition_to_next_act" not in act:
            normalized_acts.append(act)
            continue
        default_target = _act_identity(acts[index + 1]) if index + 1 < len(acts) else ""
        normalized_transition = _normalize_transition(
            act.get("transition_to_next_act"),
            default_target,
        )
        if normalized_transition != act.get("transition_to_next_act"):
            changed = True
        if normalized_transition:
            act["transition_to_next_act"] = normalized_transition
        normalized_acts.append(act)

    if changed:
        script["acts"] = normalized_acts
    return script, changed


def _normalize_transition(value: Any, default_target: str) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        transition = dict(value)
        if not _text(transition.get("target_act") or transition.get("act")) and default_target:
            transition["target_act"] = default_target
        if not _text(transition.get("allowed_when")):
            transition["allowed_when"] = "required_anchors_completed"
        return transition

    text = _text(value)
    if not text:
        return {}
    return {
        "target_act": default_target,
        "allowed_when": "required_anchors_completed",
        "transition_style": text,
    }


def _act_identity(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return _text(value.get("id") or value.get("key") or value.get("name") or value.get("title"))


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is not None and not isinstance(value, (dict, list)):
        return str(value).strip()
    return ""
