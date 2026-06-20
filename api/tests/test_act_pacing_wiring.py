"""act_pacing 信号注入导演与 GM payload 的接线测试。

确保确定性算出的「本幕节奏压力」真的进了两处 LLM 输入——否则规则再写也无信号可依。
"""

from __future__ import annotations

import json

from app.services.game_creator import create_game_from_config
from app.services.prompt_builder import PromptBuilder
from app.services.story_director import StoryDirector
from tests.story_settings_fixtures import build_generated_config


def _bump_to_high_pressure(game) -> None:
    # 停留 10 回合、从未推进锚点 → turns_since_anchor=10 ≥ HIGH(8) → high。
    state = dict(game.state.state_json)
    state["current_turn"] = 10
    game.state.state_json = state


def test_director_payload_includes_act_pacing(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    _bump_to_high_pressure(game)

    payload = StoryDirector()._payload(
        game=game,
        player_input="我继续在原地休整。",
        selected_action_style=None,
        recent_turns=[],
        related_materials=[],
        summaries={},
    )

    assert "act_pacing" in payload
    pacing = payload["act_pacing"]
    assert pacing["pressure"] == "high"
    # act_1 第一条未完成 required 锚点。
    assert pacing["next_required_anchor"]["id"] == "act_1_find_mud"


def test_gm_payload_includes_act_pacing(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    _bump_to_high_pressure(game)

    messages = PromptBuilder().build_runtime_messages(
        game=game,
        player_input="我继续在原地休整。",
        selected_action_style=None,
        recent_turns=[],
    )
    runtime_payload = json.loads(messages[1]["content"])

    assert "act_pacing" in runtime_payload
    assert runtime_payload["act_pacing"]["pressure"] == "high"
    assert runtime_payload["act_pacing"]["next_required_anchor"]["id"] == "act_1_find_mud"
