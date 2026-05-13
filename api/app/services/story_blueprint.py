from __future__ import annotations

from typing import Any

from app.models.game import GameConfig

LIST_LIMIT = 8


def build_story_blueprint(config: GameConfig | None) -> dict[str, Any]:
    if config is None:
        return {}

    script = config.script_outline if isinstance(config.script_outline, dict) else {}
    worldview = config.worldview if isinstance(config.worldview, dict) else {}
    campaign = _record(script.get("campaign_contract"))
    acts = _list(script.get("acts"))
    current_act = _current_act(acts, _text(campaign.get("current_act")) or "act_1")

    return {
        "user_brief": _record(script.get("user_brief")),
        "central_question": _text(campaign.get("central_question")),
        "main_goal": _text(campaign.get("main_goal") or campaign.get("premise")),
        "current_act": _act_payload(current_act),
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


def story_blueprint_search_fragments(config: GameConfig | None) -> list[str]:
    blueprint = build_story_blueprint(config)
    fragments: list[str] = []
    fragments.extend(_strings(blueprint.get("central_question")))
    fragments.extend(_strings(blueprint.get("main_goal")))
    fragments.extend(_strings(_record(blueprint.get("current_act")).get("objective")))
    fragments.extend(_strings(_record(blueprint.get("current_act")).get("dramatic_question")))
    fragments.extend(_strings(_record(blueprint.get("current_act")).get("pressure")))
    fragments.extend(_strings(_record(blueprint.get("current_act")).get("must_hit_beats")))
    fragments.extend(_strings(_record(blueprint.get("current_act")).get("allowed_reveals")))
    fragments.extend(_strings(blueprint.get("clue_ladder")))
    fragments.extend(_strings(blueprint.get("pressure_clock")))
    fragments.extend(_strings(blueprint.get("mechanics_contract")))
    return _unique(fragments)


def _act_payload(act: dict[str, Any]) -> dict[str, Any]:
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
    }


def _current_act(acts: list[Any], current_act_id: str) -> dict[str, Any]:
    fallback = _record(acts[0]) if acts else {}
    for item in acts:
        act = _record(item)
        if not act:
            continue
        identifiers = [
            _text(act.get("id")),
            _text(act.get("key")),
            _text(act.get("name")),
            _text(act.get("title")),
        ]
        if current_act_id and current_act_id in identifiers:
            return act
    return fallback


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
