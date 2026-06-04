"""炼金工坊并入引擎：把模块 payload（最小 story_settings 片段）深合并进目标 settings。

字符串桶静默去重；列表条目身份冲突按 resolution（rename 默认 / overwrite / skip）处理；
合并后过 validate_story_settings 保证 schema 合法（同名/同 id/同 anchor 唯一）。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from app.services.story_settings import normalize_story_settings, validate_story_settings

# 列表字段 → 身份键（按顺序取首个非空）
_LIST_IDENTITY: dict[str, tuple[str, ...]] = {
    "core_characters": ("name",),
    "core_mechanics": ("id", "name"),
    "action_style_rules": ("id", "name"),
    "story_material_library": ("id", "title"),
    "main_quest_path": ("id",),
    "act_plan": ("id",),
}
_STRING_BUCKETS: dict[str, tuple[str, ...]] = {
    "hard_rules": ("must_follow", "must_not", "reveal_rules", "continuity_rules"),
    "story_core": ("canon_terms", "forbidden_drift", "must_not_become", "must_preserve"),
    "worldview": ("public_facts", "hidden_facts"),
}


@dataclass
class MergeReport:
    entries: list[dict[str, Any]] = field(default_factory=list)  # 每模块一条
    deduped: int = 0


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) else ""


def _identity(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        t = _text(item.get(key))
        if t:
            return t
    return None


def _collect_anchor_ids(act_plan: list[Any]) -> set[str]:
    ids: set[str] = set()
    for act in act_plan:
        if isinstance(act, dict):
            for anchor in act.get("completion_anchors") or []:
                if isinstance(anchor, dict) and _text(anchor.get("id")):
                    ids.add(_text(anchor["id"]))
    return ids


def _unique_name(existing: set[str], base: str) -> str:
    if base not in existing:
        return base
    i = 2
    while f"{base} ({i})" in existing:
        i += 1
    return f"{base} ({i})"


def _reid_act(act: dict[str, Any], new_id: str) -> None:
    """act 改名后重写其 id 与全部 anchor id，保证全局唯一（title 不受唯一约束，保留原值）。"""
    act["id"] = new_id
    for index, anchor in enumerate(act.get("completion_anchors") or []):
        if isinstance(anchor, dict):
            anchor["id"] = f"{new_id}_anchor_{index + 1}"


def _merge_object(
    merged: dict[str, Any], key: str, incoming: dict[str, Any], report: MergeReport
) -> None:
    """将 incoming dict 深合并进 merged[key]：列表子键去重追加，标量/对象子键覆盖。"""
    target = merged.setdefault(key, {})
    if not isinstance(target, dict) or not isinstance(incoming, dict):
        return
    for subkey, subval in incoming.items():
        if isinstance(subval, list):
            existing = {_text(v) for v in target.get(subkey, []) if _text(v)}
            bucket = target.setdefault(subkey, [])
            if not isinstance(bucket, list):
                continue
            for v in subval:
                t = _text(v)
                if not t:
                    continue
                if t in existing:
                    report.deduped += 1
                else:
                    bucket.append(t)
                    existing.add(t)
        else:
            target[subkey] = subval  # 标量/对象覆盖


def _merge_list_item(
    merged: dict[str, Any], field_name: str, item: dict[str, Any],
    resolution: str, entry: dict[str, Any],
) -> None:
    keys = _LIST_IDENTITY[field_name]
    target = merged.setdefault(field_name, [])
    existing_ids = {
        ident for it in target if isinstance(it, dict) and (ident := _identity(it, keys))
    }
    ident = _identity(item, keys)
    new_item = copy.deepcopy(item)

    if ident and ident in existing_ids:
        entry["conflict"] = True
        if resolution == "skip":
            entry["action"] = "skipped"
            return
        if resolution == "overwrite":
            idx = next(i for i, it in enumerate(target)
                       if isinstance(it, dict) and _identity(it, keys) == ident)
            target[idx] = new_item
            entry["action"] = "overwritten"
            return
        # rename（默认）：先计算唯一 id，act_plan 额外处理 anchor 冲突
        id_key = next(k for k in keys if _text(item.get(k)))
        new_id = _unique_name(existing_ids, ident)
        if field_name == "act_plan":
            anchor_ids = _collect_anchor_ids(target)
            _reid_act(new_item, new_id)
            # 若 anchor 仍冲突，继续后缀
            while _collect_anchor_ids([new_item]) & anchor_ids:
                new_id = _unique_name(existing_ids | {new_id}, ident)
                _reid_act(new_item, new_id)
        else:
            new_item[id_key] = new_id
        target.append(new_item)
        entry["action"] = "renamed"
        entry["renamed_to"] = new_id
        return

    target.append(new_item)
    entry["action"] = "added"


def merge_modules_into_settings(
    target_settings: dict[str, Any],
    items: list[dict[str, Any]],
    resolutions: dict[str, str],
) -> tuple[dict[str, Any], MergeReport]:
    """items: [{"id": str, "payload": dict}]；resolutions: {module_id: rename|overwrite|skip}。"""
    merged = copy.deepcopy(normalize_story_settings(target_settings))
    report = MergeReport()
    for item in items:
        module_id = str(item.get("id"))
        payload = item.get("payload")
        entry: dict[str, Any] = {"module_id": module_id, "action": "added", "conflict": False}
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key in _LIST_IDENTITY and isinstance(value, list):
                    for sub in value:
                        if isinstance(sub, dict):
                            _merge_list_item(
                                merged, key, sub, resolutions.get(module_id, "rename"), entry
                            )
                elif isinstance(value, dict):
                    _merge_object(merged, key, value, report)
        report.entries.append(entry)
    settings = validate_story_settings(merged)
    return settings, report


def project_target_context(settings: dict[str, Any]) -> dict[str, Any]:
    """目标剧本投影，供 AI 适配参考（控 token）。"""
    s = normalize_story_settings(settings)
    core = s.get("story_core") or {}
    profile = s.get("game_profile") or {}
    world = s.get("worldview") or {}
    return {
        "genre": profile.get("genre"),
        "tone": profile.get("tone"),
        "premise": core.get("premise"),
        "central_mystery": core.get("central_mystery"),
        "canon_terms": core.get("canon_terms") or [],
        "worldview_summary": world.get("summary"),
        "characters": [
            {"name": c.get("name"), "role": c.get("role")}
            for c in (s.get("core_characters") or [])
            if isinstance(c, dict)
        ],
    }


async def preview_module_merge(
    target_settings: dict[str, Any],
    modules: list[dict[str, Any]],
    *,
    adapt: bool,
    resolutions: dict[str, str],
    adapter: Any,
) -> dict[str, Any]:
    """编排：可选 AI 适配每个模块 payload，再合并，返回预览（不落地）。

    modules: [{"id","name","module_type","payload"}]；adapter 需有 async adapt(payload, ctx)。
    """
    context = project_target_context(target_settings) if adapt else {}
    items: list[dict[str, Any]] = []
    adapted: list[dict[str, Any]] = []
    for module in modules:
        payload = module["payload"]
        if adapt:
            new_payload = await adapter.adapt(payload, context)
            if new_payload != payload:
                adapted.append({"module_id": module["id"], "before": payload, "after": new_payload})
            payload = new_payload
        items.append({"id": module["id"], "payload": payload})
    settings, report = merge_modules_into_settings(target_settings, items, resolutions)
    return {
        "merged_settings": settings,
        "report": {"entries": report.entries, "deduped": report.deduped},
        "adapted": adapted,
    }
