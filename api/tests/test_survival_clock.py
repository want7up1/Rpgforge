"""B3 压力时钟 + A3 危机条 的回归测试（确定性、纯函数）。"""

from __future__ import annotations

from app.services.survival_clock import (
    CALM_REGEN,
    CRISIS_MAX,
    FAILURE_CRISIS_COST,
    PRESSURE_CRISIS_COST,
    apply_survival_clocks,
)


def _state(**kwargs) -> dict:
    base = {
        "current_turn": 1,
        "crisis": {"value": CRISIS_MAX, "max": CRISIS_MAX},
        "pressure_clock": {"value": 0, "threshold": 10, "triggers": 0},
        "conditions": [],
        "story_progress": {},
    }
    base.update(kwargs)
    return base


def test_pressure_ticks_each_turn() -> None:
    state = _state()
    apply_survival_clocks(state, {})
    assert state["pressure_clock"]["value"] == 1


def test_pressure_triggers_at_threshold_and_erodes_crisis() -> None:
    state = _state(pressure_clock={"value": 9, "threshold": 10, "triggers": 0})
    apply_survival_clocks(state, {})
    # 触发后归零、触发次数+1，危机条受压力代价侵蚀（净 = regen - 压力代价）。
    assert state["pressure_clock"]["value"] == 0
    assert state["pressure_clock"]["triggers"] == 1
    assert state["crisis"]["value"] == CRISIS_MAX + CALM_REGEN - PRESSURE_CRISIS_COST


def test_calm_turn_regenerates_crisis() -> None:
    state = _state(crisis={"value": 50, "max": CRISIS_MAX})
    apply_survival_clocks(state, {})
    assert state["crisis"]["value"] == 50 + CALM_REGEN


def test_failed_action_erodes_crisis() -> None:
    state = _state(crisis={"value": 50, "max": CRISIS_MAX})
    apply_survival_clocks(state, {"action_outcome": {"outcome": "failure"}})
    assert state["crisis"]["value"] == 50 + CALM_REGEN - FAILURE_CRISIS_COST


def test_active_high_condition_drains_over_time() -> None:
    state = _state(
        crisis={"value": 50, "max": CRISIS_MAX},
        conditions=[{"name": "重伤", "severity": "high", "status": "active"}],
    )
    apply_survival_clocks(state, {})
    # high 严重度 drain 6 > regen 4 → 净下降。
    assert state["crisis"]["value"] < 50


def test_resolved_condition_does_not_drain() -> None:
    state = _state(
        crisis={"value": 50, "max": CRISIS_MAX},
        conditions=[{"name": "中毒", "severity": "high", "status": "resolved"}],
    )
    apply_survival_clocks(state, {})
    assert state["crisis"]["value"] == 50 + CALM_REGEN


def test_crisis_zero_sets_defeat_flag() -> None:
    state = _state(crisis={"value": 5, "max": CRISIS_MAX})
    apply_survival_clocks(state, {"action_outcome": {"outcome": "failure"}})
    assert state["crisis"]["value"] == 0
    assert state["story_progress"]["defeat"] is True


def test_victory_not_overwritten_by_defeat() -> None:
    state = _state(
        crisis={"value": 1, "max": CRISIS_MAX},
        story_progress={"campaign_complete": True},
    )
    apply_survival_clocks(state, {"action_outcome": {"outcome": "failure"}})
    # 已通关：不写 defeat 标记。
    assert "defeat" not in state["story_progress"] or state["story_progress"]["defeat"] is not True


def test_crisis_clamped_to_max() -> None:
    state = _state(crisis={"value": 99, "max": CRISIS_MAX})
    apply_survival_clocks(state, {})
    assert state["crisis"]["value"] == CRISIS_MAX
