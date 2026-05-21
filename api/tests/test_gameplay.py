import json

import anyio

from app.models.turn import Turn
from app.services.deepseek_client import ChatCompletionResult
from app.services.game_creator import create_game_from_config
from app.services.prompt_builder import PromptBuilder
from app.services.state_applier import apply_state_delta
from app.services.state_extractor import StateExtractor
from app.services.story_director import StoryDirector
from app.services.story_settings import (
    build_runtime_story,
    completion_anchor_ids_for_act,
    retrieve_story_materials,
    select_action_style,
)
from tests.story_settings_fixtures import build_generated_config, build_two_act_config


def test_prompt_injects_story_settings_runtime_view_and_materials(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    db_session.add(
        Turn(
            game_id=game.id,
            turn_number=1,
            player_input="我检查门槛。",
            gm_output="门槛内侧有新鲜泥痕。" * 80,
            visible_summary="发现义庄泥痕。",
            hidden_summary=None,
            state_delta_json={},
            action_options_json=[{"key": "A", "label": "继续调查泥痕"}],
            model_used="deepseek-v4-pro-test",
        )
    )
    db_session.commit()
    db_session.refresh(game)

    selected_style = select_action_style(game.config, "我调查义庄门槛的新鲜泥痕。")
    materials = retrieve_story_materials(
        game.config,
        player_input="我调查义庄门槛的新鲜泥痕。",
        selected_action_style=selected_style,
        state_json=game.state.state_json,
        recent_turns=list(game.turns),
    )

    messages = PromptBuilder().build_runtime_messages(
        game=game,
        player_input="我调查义庄门槛的新鲜泥痕。",
        selected_action_style=selected_style,
        recent_turns=list(game.turns),
        related_materials=materials,
        summaries={"long_term": "长期记忆：义庄旧案仍未结。"},
    )
    runtime_payload = json.loads(messages[1]["content"])

    assert "runtime_story" in runtime_payload
    assert "script_outline" not in runtime_payload
    assert "campaign_contract" not in runtime_payload
    assert "related_lore" not in runtime_payload
    assert runtime_payload["runtime_story"]["story_core"]["main_goal"] == "查清义庄旧案。"
    assert runtime_payload["runtime_story"]["current_act"]["id"] == "act_1"
    assert runtime_payload["selected_action_style"]["id"] == "investigation"
    assert [item["title"] for item in runtime_payload["related_story_materials"]][0] == "雁回镇义庄"
    assert runtime_payload["generation_parameters"]["recent_turn_excerpt_chars"] == 420
    assert runtime_payload["recent_turns"][0]["gm_output_excerpt"].endswith("...")


def test_action_style_and_material_retrieval_use_story_settings(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())

    selected = select_action_style(game.config, "我检查黑伞客留下的伞骨划痕。")
    results = retrieve_story_materials(
        game.config,
        player_input="我检查黑伞客留下的伞骨划痕。",
        selected_action_style=selected,
        state_json=game.state.state_json,
        recent_turns=[],
    )

    assert selected["name"] == "调查行动"
    titles = [result.material["title"] for result in results]
    assert "雁回镇义庄" in titles
    assert "黑伞客陆沉舟" in titles


def test_runtime_story_only_exposes_current_act_open_anchors(db_session) -> None:
    game = create_game_from_config(db_session, build_two_act_config())
    runtime_story = build_runtime_story(game.config, game.state.state_json)

    assert completion_anchor_ids_for_act(game.config, "act_1") == [
        "act_1_find_mud",
        "act_1_identify_black_umbrella",
    ]
    assert runtime_story["current_act"]["id"] == "act_1"
    assert [anchor["id"] for anchor in runtime_story["current_act"]["completion_anchors"]] == [
        "act_1_find_mud",
        "act_1_identify_black_umbrella",
    ]
    assert runtime_story["next_act"]["id"] == "act_2"

    state = dict(game.state.state_json)
    state["story_progress"] = {
        **state["story_progress"],
        "completed_anchors": ["act_1_find_mud"],
    }
    runtime_story = build_runtime_story(game.config, state)

    assert [anchor["id"] for anchor in runtime_story["current_act"]["completion_anchors"]] == [
        "act_1_identify_black_umbrella"
    ]


def test_state_delta_advances_act_only_after_required_anchors(db_session) -> None:
    game = create_game_from_config(db_session, build_two_act_config())
    state = game.state

    first_turn = Turn(game_id=game.id, turn_number=1, player_input="", gm_output="")
    first_state = apply_state_delta(
        state,
        first_turn,
        {
            "story_progress_update": {
                "completed_anchor": "act_1_find_mud",
                "completed_act": "act_1",
                "next_act": "act_2",
                "reason": "发现门槛泥痕。",
            }
        },
    )
    assert first_state["story_progress"]["current_act"] == "act_1"
    assert first_state["story_progress"]["ready_for_next_act"] is False
    assert first_state["story_progress"]["completed_acts"] == []

    state.state_json = first_state
    second_turn = Turn(game_id=game.id, turn_number=2, player_input="", gm_output="")
    second_state = apply_state_delta(
        state,
        second_turn,
        {
            "story_progress_update": {
                "completed_anchor": "act_1_identify_black_umbrella",
                "completed_act": "act_1",
                "next_act": "act_2",
                "advance_reason": "确认黑伞客踪迹。",
            }
        },
    )

    assert second_state["story_progress"]["current_act"] == "act_2"
    assert second_state["story_progress"]["completed_acts"] == ["act_1"]
    assert second_state["story_progress"]["last_advance_turn"] == 2


def test_story_director_fallback_reads_runtime_story_current_act(db_session) -> None:
    class FailingRouter:
        async def use_flash(self, *args, **kwargs):
            raise ValueError("invalid model output")

    game = create_game_from_config(db_session, build_generated_config())
    director = StoryDirector(router=FailingRouter())

    async def run_plan():
        return await director.plan(
            game=game,
            player_input="我继续检查义庄。",
            selected_action_style=select_action_style(game.config, "我继续检查义庄。"),
            recent_turns=[],
            related_materials=[],
            summaries={},
        )

    decision = anyio.run(run_plan)

    assert decision.current_act == "act_1"
    assert decision.scene_objective == "找到旧案第一条线索。"
    assert decision.forbidden_reveals == ["账册真凶"]
    assert decision.gm_instruction


def test_state_extractor_payload_uses_runtime_story_not_legacy_contracts(db_session) -> None:
    calls: list[dict[str, object]] = []

    class FakeRouter:
        async def use_flash(self, task_type, messages, **kwargs):
            calls.append({"task_type": task_type, "messages": messages, **kwargs})
            return ChatCompletionResult(content="{}", model="deepseek-flash-test", raw={})

    game = create_game_from_config(db_session, build_generated_config())
    turn = Turn(
        game_id=game.id,
        turn_number=1,
        player_input="我检查门槛泥痕。",
        gm_output="门槛内侧有新鲜泥痕。",
        visible_summary="发现门槛泥痕。",
        hidden_summary=None,
        state_delta_json={},
        action_options_json=[],
        model_used="deepseek-v4-pro-test",
    )

    anyio.run(StateExtractor(router=FakeRouter()).extract, game, turn)
    payload = json.loads(calls[0]["messages"][1]["content"])

    assert calls[0]["task_type"] == "state_delta_extract"
    assert payload["runtime_story"]["current_act"]["id"] == "act_1"
    assert "script_outline" not in payload
    assert "campaign_contract" not in payload
