from __future__ import annotations

from typing import Any

from app.models.game import GameConfig

LIST_LIMIT = 8
ANCHOR_LIMIT = 12


def build_story_blueprint(
    config: GameConfig | None,
    state_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if config is None:
        return {}

    script = config.script_outline if isinstance(config.script_outline, dict) else {}
    worldview = config.worldview if isinstance(config.worldview, dict) else {}
    campaign = _record(script.get("campaign_contract"))
    acts = _list(script.get("acts"))
    configured_current_act = _text(campaign.get("current_act")) or "act_1"
    story_progress = story_progress_from_state(state_json)
    current_act_id = _runtime_current_act_id(
        acts,
        story_progress.get("current_act"),
        configured_current_act,
    )
    current_act = _current_act(acts, current_act_id)
    next_act = _next_act(acts, current_act)

    return {
        "user_brief": _record(script.get("user_brief")),
        "central_question": _text(campaign.get("central_question")),
        "main_goal": _text(campaign.get("main_goal") or campaign.get("premise")),
        "current_act": _act_payload(current_act),
        "next_act": _act_payload(next_act),
        "story_progress": {
            "current_act": _text(_act_identity(current_act) or current_act_id),
            "configured_start_act": configured_current_act,
            "completed_acts": story_progress.get("completed_acts", []),
            "completed_anchors": story_progress.get("completed_anchors", []),
            "ready_for_next_act": story_progress.get("ready_for_next_act", False),
            "last_advance_turn": story_progress.get("last_advance_turn"),
            "last_advance_reason": story_progress.get("last_advance_reason", ""),
            "last_anchor_update_turn": story_progress.get("last_anchor_update_turn"),
        },
        "truth_map": _bounded_list(script.get("truth_map")),
        "clue_ladder": _bounded_list(script.get("clue_ladder")),
        "pressure_clock": _bounded_list(script.get("pressure_clock")),
        "mechanics_contract": _bounded_list(
            script.get("mechanics_contract")
            or campaign.get("mechanics_contract")
        ),
        "worldview": {
            "summary": _text(worldview.get("summary") or worldview.get("setting")),
            "tone": _text(worldview.get("tone")),
            "core_conflicts": _bounded_list(worldview.get("core_conflicts")),
        },
        "forbidden_public_spoilers": _bounded_list(script.get("forbidden_public_spoilers")),
    }


def initial_story_progress(config: GameConfig | None) -> dict[str, Any]:
    if config is None:
        return {
            "current_act": "",
            "completed_acts": [],
            "completed_anchors": [],
            "ready_for_next_act": False,
            "last_advance_turn": None,
            "last_advance_reason": "",
            "last_anchor_update_turn": None,
            "act_history": [],
            "anchor_history": [],
        }

    script = config.script_outline if isinstance(config.script_outline, dict) else {}
    campaign = _record(script.get("campaign_contract"))
    acts = _list(script.get("acts"))
    configured_current_act = _text(campaign.get("current_act")) or "act_1"
    current_act = _current_act(acts, configured_current_act)
    current_act_id = _text(_act_identity(current_act) or configured_current_act)
    return {
        "current_act": current_act_id,
        "completed_acts": [],
        "completed_anchors": [],
        "ready_for_next_act": False,
        "last_advance_turn": None,
        "last_advance_reason": "",
        "last_anchor_update_turn": None,
        "act_history": [],
        "anchor_history": [],
    }


def story_progress_from_state(state_json: dict[str, Any] | None) -> dict[str, Any]:
    state = _record(state_json)
    progress = _record(state.get("story_progress"))
    if not progress:
        progress = _record(_record(state.get("v2")).get("story_progress"))
    return {
        "current_act": _text(progress.get("current_act") or progress.get("act")),
        "completed_acts": _unique(_strings(progress.get("completed_acts"))),
        "completed_anchors": _unique(_strings(progress.get("completed_anchors"))),
        "ready_for_next_act": _bool(progress.get("ready_for_next_act"), False),
        "last_advance_turn": progress.get("last_advance_turn"),
        "last_advance_reason": _text(progress.get("last_advance_reason")),
        "last_anchor_update_turn": progress.get("last_anchor_update_turn"),
    }


def completion_anchor_ids_for_act(
    config: GameConfig | None,
    act_id: str,
    *,
    required_only: bool = True,
) -> list[str]:
    act = _act_for_config(config, act_id)
    anchors = _completion_anchors(act)
    ids: list[str] = []
    for anchor in anchors:
        if required_only and not _bool(anchor.get("required"), True):
            continue
        anchor_id = _text(anchor.get("id"))
        if anchor_id and anchor_id not in ids:
            ids.append(anchor_id)
    return ids


def transition_target_for_act(config: GameConfig | None, act_id: str) -> str:
    act = _act_for_config(config, act_id)
    transition = _transition_payload(_record(act.get("transition_to_next_act")))
    return _text(transition.get("target_act"))


def build_campaign_contract_payload(config: GameConfig | None) -> dict[str, Any]:
    if config is None:
        return {}

    script = config.script_outline if isinstance(config.script_outline, dict) else {}
    worldview = config.worldview if isinstance(config.worldview, dict) else {}
    campaign = _record(script.get("campaign_contract"))
    director = _record(script.get("director_contract"))
    story = _record(script.get("story_contract"))

    if campaign:
        payload = dict(campaign)
        _merge_missing(payload, director)
        _merge_missing(payload, story)
        if director:
            payload["director_contract"] = director
        if story:
            payload["story_contract"] = story
    else:
        acts = _list(script.get("acts"))
        premise = (
            _text(script.get("title"))
            or _text(worldview.get("summary"))
            or _text(worldview.get("setting"))
        )
        payload = {
            "source": "derived_from_script_outline",
            "premise": premise,
            "tone": _text(worldview.get("tone")),
            "act_plan": acts,
            "anchor_rules": [
                "优先保持原始剧本骨架、世界观和玩家创意意图。",
                "除非玩家明确选择偏离，不要用新设定覆盖既有主线目标。",
                "新的重要势力、地点、Boss 或终局真相必须服务当前幕目标，并先给出铺垫。",
            ],
        }

    mechanics_contract = script.get("mechanics_contract")
    if isinstance(mechanics_contract, list) and mechanics_contract:
        payload["mechanics_contract"] = mechanics_contract
    return payload


def protect_user_brief_contract(script_outline: dict[str, Any]) -> dict[str, Any]:
    script = dict(script_outline)
    user_brief = _record(script.get("user_brief"))
    campaign = dict(_record(script.get("campaign_contract")))
    if not user_brief:
        script["campaign_contract"] = campaign
        return script

    must_include = _unique([
        *_strings(campaign.get("must_preserve")),
        *_strings(user_brief.get("must_include")),
    ])
    forbidden = _unique([
        *_strings(campaign.get("must_not_become")),
        *_strings(user_brief.get("forbidden_content")),
    ])
    forbidden_drift = _unique([
        *_strings(campaign.get("forbidden_drift")),
        *forbidden,
    ])
    campaign["must_preserve"] = must_include
    campaign["must_not_become"] = forbidden
    campaign["forbidden_drift"] = forbidden_drift
    script["campaign_contract"] = campaign
    return script


def merge_required_script_fields(
    candidate: dict[str, Any],
    existing: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(candidate)
    existing_user_brief = _record(existing.get("user_brief"))
    candidate_user_brief = _record(merged.get("user_brief"))
    if existing_user_brief:
        if candidate_user_brief:
            user_brief = dict(candidate_user_brief)
            _merge_missing(user_brief, existing_user_brief)
            merged["user_brief"] = user_brief
        else:
            merged["user_brief"] = existing_user_brief
    character_profiles_missing = (
        "_character_profiles" not in merged
        or merged.get("_character_profiles") in (None, "", [], {})
    )
    if character_profiles_missing and "_character_profiles" in existing:
        merged["_character_profiles"] = existing["_character_profiles"]
    existing_campaign = _record(existing.get("campaign_contract"))
    candidate_campaign = _record(merged.get("campaign_contract"))
    if existing_campaign:
        if candidate_campaign:
            campaign = dict(candidate_campaign)
            _merge_missing(campaign, existing_campaign)
            merged["campaign_contract"] = campaign
        else:
            merged["campaign_contract"] = existing_campaign
    return protect_user_brief_contract(merged)


def story_blueprint_search_fragments(
    config: GameConfig | None,
    state_json: dict[str, Any] | None = None,
) -> list[str]:
    blueprint = build_story_blueprint(config, state_json)
    fragments: list[str] = []
    fragments.extend(_strings(blueprint.get("central_question")))
    fragments.extend(_strings(blueprint.get("main_goal")))
    fragments.extend(_strings(_record(blueprint.get("current_act")).get("objective")))
    fragments.extend(_strings(_record(blueprint.get("current_act")).get("dramatic_question")))
    fragments.extend(_strings(_record(blueprint.get("current_act")).get("pressure")))
    fragments.extend(_strings(_record(blueprint.get("current_act")).get("must_hit_beats")))
    fragments.extend(_strings(_record(blueprint.get("current_act")).get("allowed_reveals")))
    fragments.extend(_strings(_record(blueprint.get("current_act")).get("completion_anchors")))
    fragments.extend(_strings(_record(blueprint.get("next_act")).get("objective")))
    fragments.extend(_strings(_record(blueprint.get("next_act")).get("dramatic_question")))
    fragments.extend(_strings(blueprint.get("clue_ladder")))
    fragments.extend(_strings(blueprint.get("pressure_clock")))
    fragments.extend(_strings(blueprint.get("mechanics_contract")))
    return _unique(fragments)


def _act_payload(act: dict[str, Any]) -> dict[str, Any]:
    if not act:
        return {}
    return {
        "id": _text(act.get("id") or act.get("key")),
        "name": _text(act.get("name") or act.get("title")),
        "objective": _text(act.get("objective") or act.get("goal")),
        "dramatic_question": _text(act.get("dramatic_question")),
        "pressure": _text(act.get("pressure")),
        "must_hit_beats": _bounded_list(act.get("must_hit_beats")),
        "allowed_reveals": _bounded_list(act.get("allowed_reveals")),
        "forbidden_reveals": _bounded_list(act.get("forbidden_reveals")),
        "relationship_turn": _text(act.get("relationship_turn")),
        "escalation_limit": _text(act.get("escalation_limit")),
        "completion_signal": _text(act.get("completion_signal")),
        "completion_anchors": [
            _anchor_payload(anchor)
            for anchor in _completion_anchors(act)[:ANCHOR_LIMIT]
        ],
        "transition_to_next_act": _transition_payload(
            _record(act.get("transition_to_next_act"))
        ),
    }


def _anchor_payload(anchor: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _text(anchor.get("id") or anchor.get("key")),
        "title": _text(anchor.get("title") or anchor.get("name")),
        "required": _bool(anchor.get("required"), True),
        "completion_signal": _text(anchor.get("completion_signal") or anchor.get("signal")),
        "story_effect": _text(anchor.get("story_effect") or anchor.get("effect")),
        "allowed_reveals": _bounded_list(anchor.get("allowed_reveals")),
        "forbidden_reveals": _bounded_list(anchor.get("forbidden_reveals")),
    }


def _transition_payload(transition: dict[str, Any]) -> dict[str, Any]:
    if not transition:
        return {}
    return {
        "target_act": _text(transition.get("target_act") or transition.get("act")),
        "allowed_when": _text(transition.get("allowed_when")) or "required_anchors_completed",
        "transition_style": _text(transition.get("transition_style") or transition.get("style")),
    }


def _completion_anchors(act: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        anchor
        for item in _list(act.get("completion_anchors"))
        if (anchor := _record(item))
    ]


def _act_for_config(config: GameConfig | None, act_id: str) -> dict[str, Any]:
    if config is None:
        return {}
    script = config.script_outline if isinstance(config.script_outline, dict) else {}
    return _current_act(_list(script.get("acts")), act_id)


def _runtime_current_act_id(
    acts: list[Any],
    state_current_act: Any,
    configured_current_act: str,
) -> str:
    candidate = _text(state_current_act)
    if candidate and (not acts or _act_exists(acts, candidate)):
        return candidate
    return configured_current_act


def _act_exists(acts: list[Any], act_id: str) -> bool:
    for item in acts:
        act = _record(item)
        if act_id and act_id in _act_identifiers(act):
            return True
    return False


def _act_identifiers(act: dict[str, Any]) -> list[str]:
    return [
        _text(act.get("id")),
        _text(act.get("key")),
        _text(act.get("name")),
        _text(act.get("title")),
    ]


def _current_act(acts: list[Any], current_act_id: str) -> dict[str, Any]:
    fallback = _record(acts[0]) if acts else {}
    for item in acts:
        act = _record(item)
        if not act:
            continue
        if current_act_id and current_act_id in _act_identifiers(act):
            return act
    return fallback


def _next_act(acts: list[Any], current_act: dict[str, Any]) -> dict[str, Any]:
    current_identity = _act_identity(current_act)
    if not current_identity:
        return {}
    for index, item in enumerate(acts):
        act = _record(item)
        if not act:
            continue
        if _act_identity(act) != current_identity:
            continue
        for next_item in acts[index + 1:]:
            next_act = _record(next_item)
            if next_act:
                return next_act
        return {}
    return {}


def _act_identity(act: dict[str, Any]) -> str:
    return _text(
        act.get("id")
        or act.get("key")
        or act.get("name")
        or act.get("title")
    )


def _merge_missing(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if value in (None, "", [], {}):
            continue
        if key not in target or target[key] in (None, "", [], {}):
            target[key] = value


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, "", {}):
        return []
    return [value]


def _bounded_list(value: Any) -> list[Any]:
    return _list(value)[:LIST_LIMIT]


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


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


def _strings(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [
            text
            for item in value
            for text in _strings(item)
        ]
    if isinstance(value, dict):
        return [
            text
            for item in value.values()
            for text in _strings(item)
        ]
    text = str(value).strip()
    return [text] if text else []


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
