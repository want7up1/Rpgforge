from copy import deepcopy
from types import SimpleNamespace

from app.services import story_settings
from app.services.act_pacing import compute_act_pacing
from app.services.state_applier import apply_state_delta
from app.services.state_v2 import state_v2_view
from app.services.story_settings import build_runtime_story, progress_rules_from_config


def _anchor(name, *, required=True, group=""):
    return {
        "id": name, "title": name, "completion_signal": f"Complete {name}",
        "required": required, "alternative_group": group,
    }


def _config(anchors):
    return SimpleNamespace(story_settings={
        "game_profile": {"title": "Rules fixture"},
        "story_core": {"current_act": "act_1"},
        "act_plan": [{"id": "act_1", "completion_anchors": anchors}],
    })


def _state(config):
    return SimpleNamespace(
        state_json={"current_turn": 12, "story_progress": {
            "current_act": "act_1", "last_advance_turn": 0,
            "last_anchor_update_turn": 0, "completed_anchors": [],
        }}, game=SimpleNamespace(config=config, title="Rules fixture", description=""),
    )


def test_runtime_budget_never_hides_required_anchors_after_optional_material():
    config = _config([_anchor(f"side_{n}", required=False) for n in range(16)]
                     + [_anchor("mandatory")])
    state = _state(config).state_json
    runtime = build_runtime_story(config, state)
    anchors = runtime["current_act"]["completion_anchors"]
    assert "mandatory" in {a["id"] for a in anchors}
    assert len(anchors) == 16
    pacing = compute_act_pacing(state_v2_view(state), runtime)
    assert pacing["pressure"] == "high"
    assert pacing["open_required_count"] == 1


def test_runtime_keeps_every_mandatory_route_even_when_over_budget():
    config = _config([_anchor(f"required_{n}") for n in range(18)])
    runtime = build_runtime_story(config, _state(config).state_json)
    assert len(runtime["current_act"]["completion_anchors"]) == 18


def test_optional_completion_does_not_reset_main_requirement_stall():
    config = _config([_anchor("main"), _anchor("side", required=False)])
    state = _state(config)
    original = deepcopy(state.state_json)
    after = apply_state_delta(state, SimpleNamespace(turn_number=12), {
        "story_progress_update": {"completed_anchors": ["side"]},
    })
    assert state.state_json == original
    assert after["story_progress"]["last_anchor_update_turn"] == 0
    assert after["story_progress"]["anchor_history"][-1]["anchor_id"] == "side"
    assert compute_act_pacing(
        state_v2_view(after), build_runtime_story(config, after)
    )["pressure"] == "high"


def test_alternative_routes_share_one_requirement_and_remain_available():
    config = _config([_anchor("sneak", group="entry"), _anchor("talk", group="entry")])
    rules = progress_rules_from_config(config)
    assert rules.progress("act_1", []) == {"done": 0, "total": 1}
    assert rules.progress("act_1", ["talk"]) == {"done": 1, "total": 1}
    pacing = compute_act_pacing(
        state_v2_view(_state(config).state_json),
        build_runtime_story(config, _state(config).state_json),
    )
    assert [a["id"] for a in pacing["next_required_anchors"]] == ["sneak", "talk"]


def test_rules_are_normalized_once_per_replay_and_not_cached_across_revisions(monkeypatch):
    config = _config([_anchor("main")])
    calls = 0
    original = story_settings.normalize_story_settings

    def counted(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(story_settings, "normalize_story_settings", counted)
    rules = progress_rules_from_config(config)
    state = _state(config)
    for number in range(1, 11):
        state.state_json = apply_state_delta(
            state, SimpleNamespace(turn_number=number), {}, rules=rules
        )
    assert calls == 1
    config.story_settings["act_plan"][0]["completion_anchors"].append(_anchor("new_main"))
    assert progress_rules_from_config(config).progress("act_1", ["main"])["total"] == 2
    assert rules.progress("act_1", ["main"])["total"] == 1


def test_pacing_baseline_never_predates_entering_current_act():
    state = {"current_turn": 13, "story_progress": {
        "last_anchor_update_turn": 1, "last_advance_turn": 12,
    }}
    runtime = {"current_act": {"completion_anchors": [_anchor("new_main")]}}
    pacing = compute_act_pacing(state, runtime)
    assert pacing["turns_since_anchor"] == 1
    assert pacing["pressure"] == "low"
