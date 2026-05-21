"""Normalize legacy string completion anchors.

Revision ID: 20260520_0021
Revises: 20260520_0020
Create Date: 2026-05-20 19:20:00.000000
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20260520_0021"
down_revision = "20260520_0020"
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
        normalized, changed = _normalize_script_completion_anchors(script_outline)
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
    # Lossless downgrade is not possible: legacy string anchors are expanded into objects.
    pass


def _normalize_script_completion_anchors(
    script_outline: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    script = dict(script_outline)
    acts = script.get("acts")
    if not isinstance(acts, list):
        return script, False

    changed = False
    normalized_acts: list[Any] = []
    for act_item in acts:
        if not isinstance(act_item, dict):
            normalized_acts.append(act_item)
            continue
        act = dict(act_item)
        anchors = act.get("completion_anchors")
        if not isinstance(anchors, list):
            normalized_acts.append(act)
            continue
        normalized_anchors = []
        for index, anchor_item in enumerate(anchors, start=1):
            anchor = _normalize_anchor(anchor_item, act, index)
            if anchor:
                normalized_anchors.append(anchor)
        if normalized_anchors != anchors:
            changed = True
            act["completion_anchors"] = normalized_anchors
        normalized_acts.append(act)

    if changed:
        script["acts"] = normalized_acts
    return script, changed


def _normalize_anchor(item: Any, act: dict[str, Any], index: int) -> dict[str, Any]:
    generated_id = _generated_anchor_id(act, index)
    if isinstance(item, dict):
        anchor = dict(item)
        if not _text(anchor.get("id") or anchor.get("key")):
            anchor["id"] = generated_id
        if not _text(anchor.get("title") or anchor.get("name")):
            fallback_title = _text(
                anchor.get("completion_signal")
                or anchor.get("signal")
                or anchor.get("story_effect")
                or anchor.get("effect")
            )
            if fallback_title:
                anchor["title"] = fallback_title
        if not _text(anchor.get("completion_signal") or anchor.get("signal")):
            title = _text(anchor.get("title") or anchor.get("name"))
            if title:
                anchor["completion_signal"] = title
        return anchor

    text = _text(item)
    if not text:
        return {}
    return {
        "id": generated_id,
        "title": text,
        "required": True,
        "completion_signal": text,
        "story_effect": "",
    }


def _generated_anchor_id(act: dict[str, Any], index: int) -> str:
    prefix = _text(act.get("id") or act.get("key") or act.get("name") or act.get("title"))
    if not prefix:
        prefix = "act"
    return f"{_safe_identifier_prefix(prefix)}_anchor_{index}"


def _safe_identifier_prefix(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized or "act"


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is not None and not isinstance(value, (dict, list)):
        return str(value).strip()
    return ""
