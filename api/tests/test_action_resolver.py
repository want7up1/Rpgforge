"""A1 判定层 + A2 数值反哺 的回归测试（纯函数、可注入种子 rng）。"""

from __future__ import annotations

import random

from app.services.action_resolver import (
    build_outcome_instruction,
    resolve_action_check,
)


class _FixedRoll(random.Random):
    """固定 d20 掷骰，便于断言 outcome 分支。"""

    def __init__(self, value: int) -> None:
        super().__init__()
        self._value = value

    def randint(self, a: int, b: int) -> int:  # noqa: ARG002
        return self._value


def _state(level: int = 1, skills=None, attributes=None, tracks=None) -> dict:
    return {
        "protagonist_sheet": {"level": level, "attributes": attributes or {}},
        "skills": skills or [],
        "relationship_tracks": tracks or [],
    }


def test_no_check_when_difficulty_missing() -> None:
    assert resolve_action_check({}, _state()) is None
    assert resolve_action_check({"action": "闲聊"}, _state()) is None
    assert resolve_action_check("not a dict", _state()) is None


def test_natural_one_is_failure_even_with_high_modifier() -> None:
    state = _state(level=50, skills=[{"name": "撬锁", "level": 9, "mastery": 99}])
    result = resolve_action_check(
        {"action": "撬锁", "difficulty": "easy", "skill": "撬锁"}, state, rng=_FixedRoll(1)
    )
    assert result is not None
    assert result["outcome"] == "failure"


def test_natural_twenty_is_critical_even_on_hard() -> None:
    result = resolve_action_check(
        {"action": "搏斗", "difficulty": "extreme"}, _state(), rng=_FixedRoll(20)
    )
    assert result["outcome"] == "critical"


def test_low_roll_fails_normal_check() -> None:
    # roll 3 + 修正 0 = 3 vs DC 12 → failure（差距 >5）。
    result = resolve_action_check(
        {"action": "撬锁", "difficulty": "normal"}, _state(), rng=_FixedRoll(3)
    )
    assert result["outcome"] == "failure"


def test_partial_band() -> None:
    # roll 9 vs DC 12：9 >= 12-5=7 且 <12 → partial。
    result = resolve_action_check(
        {"action": "撬锁", "difficulty": "normal"}, _state(), rng=_FixedRoll(9)
    )
    assert result["outcome"] == "partial"


def test_skill_modifier_lifts_outcome() -> None:
    # 同样 roll 9，但有高技能 → 修正抬高到成功档。
    state = _state(skills=[{"name": "撬锁", "level": 5, "mastery": 80}])
    result = resolve_action_check(
        {"action": "撬锁", "difficulty": "normal", "skill": "撬锁"}, state, rng=_FixedRoll(9)
    )
    assert result["modifier"] >= 5
    assert result["outcome"] in {"success", "critical"}


def test_relationship_modifier_for_social_check() -> None:
    tracks = [{"npc": "阿樱", "trust": 90, "affection": 80}]
    high = resolve_action_check(
        {"action": "说服", "difficulty": "normal", "target_npc": "阿樱"},
        _state(tracks=tracks),
        rng=_FixedRoll(10),
    )
    low_tracks = [{"npc": "阿樱", "trust": 10, "affection": 10}]
    low = resolve_action_check(
        {"action": "说服", "difficulty": "normal", "target_npc": "阿樱"},
        _state(tracks=low_tracks),
        rng=_FixedRoll(10),
    )
    assert high["breakdown"]["relationship"] > low["breakdown"]["relationship"]


def test_attribute_modifier_dnd_style() -> None:
    state = _state(attributes={"力量": 16})
    result = resolve_action_check(
        {"action": "破门", "difficulty": "normal", "attribute": "力量"}, state, rng=_FixedRoll(10)
    )
    # (16-10)//2 = 3
    assert result["breakdown"]["attribute"] == 3


def test_outcome_instruction_mentions_failure_consequence() -> None:
    result = resolve_action_check(
        {"action": "撬锁", "difficulty": "normal"}, _state(), rng=_FixedRoll(2)
    )
    text = build_outcome_instruction(result)
    assert "失败" in text
    assert "硬约束" in text


def test_default_attributes_injected_for_empty_protagonist() -> None:
    """老存档/未生成属性：state_v2 投影懒注入中性默认六维，让判定层有可读数值（调整值 0）。"""
    from app.services.state_v2 import DEFAULT_PROTAGONIST_ATTRIBUTES, state_v2_view

    view = state_v2_view({"protagonist": {"name": "无名"}})
    assert view["protagonist_sheet"]["attributes"] == DEFAULT_PROTAGONIST_ATTRIBUTES
    result = resolve_action_check(
        {"action": "搜查", "difficulty": "normal", "attribute": "感知"},
        view,
        rng=_FixedRoll(10),
    )
    assert result["breakdown"]["attribute"] == 0


def test_real_attributes_preserved_over_default() -> None:
    """已有真实属性时不被默认六维覆盖（投影原样带出，build 真正生效）。"""
    from app.services.state_v2 import state_v2_view

    view = state_v2_view({"protagonist": {"attributes": {"力量": 16}}})
    assert view["protagonist_sheet"]["attributes"] == {"力量": 16}


def test_game_creator_fills_default_attributes_when_empty() -> None:
    """game_creator：AI 未生成/手动建档时填默认六维（即使无 configured 主角也执行）。"""
    from app.services.game_creator import _fill_protagonist_from_story_settings
    from app.services.state_v2 import DEFAULT_PROTAGONIST_ATTRIBUTES

    initial_state: dict = {"protagonist": {"name": "阿强", "attributes": {}}}
    _fill_protagonist_from_story_settings(initial_state, {})
    assert initial_state["protagonist"]["attributes"] == DEFAULT_PROTAGONIST_ATTRIBUTES


def test_game_creator_keeps_generated_attributes() -> None:
    """game_creator：生成器已产出属性时不覆盖。"""
    from app.services.game_creator import _fill_protagonist_from_story_settings

    initial_state: dict = {"protagonist": {"attributes": {"力量": 15, "敏捷": 9}}}
    _fill_protagonist_from_story_settings(initial_state, {})
    assert initial_state["protagonist"]["attributes"] == {"力量": 15, "敏捷": 9}
