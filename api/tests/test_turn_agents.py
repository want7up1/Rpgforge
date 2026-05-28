"""DriftValidator / StoryDirector 测试（fake router，不发真实 LLM）。"""

import json

import anyio

from app.schemas.turn import GMRuntimeOutput
from app.services.deepseek_client import ChatCompletionResult, DeepSeekAPIError
from app.services.drift_validator import DriftValidator
from app.services.game_creator import create_game_from_config
from app.services.model_router import ModelRouter
from app.services.story_director import StoryDirector, StoryDirectorDecision
from tests.story_settings_fixtures import build_generated_config


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def chat_completion(self, **kwargs):
        return ChatCompletionResult(
            content=json.dumps(self._payload, ensure_ascii=False),
            model=kwargs["model"],
            raw={},
        )


class _ErrorClient:
    async def chat_completion(self, **kwargs):
        raise DeepSeekAPIError("boom")


def _gm_output() -> GMRuntimeOutput:
    return GMRuntimeOutput(
        narrative="门槛内侧有新鲜泥痕。",
        visible_clues=["泥痕"],
        action_options=[
            {"key": "A", "label": "追查泥痕"},
            {"key": "B", "label": "询问邻居"},
            {"key": "C", "label": "检查门锁"},
            {"key": "D", "label": "暂时离开"},
        ],
    )


# ---------- DriftValidator ----------

def test_drift_approved_does_not_rewrite(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    validator = DriftValidator(
        router=ModelRouter(
            client=_FakeClient({"approved": True, "severity": "none"})
        )
    )
    result = anyio.run(
        lambda: validator.validate(
            game=game,
            player_input="我调查泥痕",
            recent_turns=[],
            director_decision=StoryDirectorDecision(),
            runtime_output=_gm_output(),
        )
    )
    assert result.approved is True
    assert validator.should_rewrite(result) is False


def test_drift_major_triggers_rewrite(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    validator = DriftValidator(
        router=ModelRouter(
            client=_FakeClient(
                {
                    "approved": False,
                    "severity": "major",
                    "issues": ["提前揭露真凶"],
                    "rewrite_instruction": "不要揭露真凶身份",
                }
            )
        )
    )
    result = anyio.run(
        lambda: validator.validate(
            game=game,
            player_input="我调查泥痕",
            recent_turns=[],
            director_decision=StoryDirectorDecision(),
            runtime_output=_gm_output(),
        )
    )
    assert validator.should_rewrite(result) is True
    assert validator.rewrite_instruction(result) == "不要揭露真凶身份"


def test_drift_llm_failure_falls_back_not_rewrite(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    validator = DriftValidator(router=ModelRouter(client=_ErrorClient()))
    result = anyio.run(
        lambda: validator.validate(
            game=game,
            player_input="我调查泥痕",
            recent_turns=[],
            director_decision=StoryDirectorDecision(),
            runtime_output=_gm_output(),
        )
    )
    # fallback：approved=False + severity=unknown，但 unknown 不触发重写
    assert result.approved is False
    assert result.severity == "unknown"
    assert validator.should_rewrite(result) is False


# ---------- StoryDirector ----------

def test_director_parses_decision(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    director = StoryDirector(
        router=ModelRouter(
            client=_FakeClient(
                {
                    "player_intent": "调查泥痕",
                    "scene_objective": "发现线索",
                    "forbidden_reveals": ["真凶身份"],
                    "gm_instruction": "给线索不给答案",
                }
            )
        )
    )
    decision = anyio.run(
        lambda: director.plan(
            game=game,
            player_input="我调查泥痕",
            selected_action_style=None,
            recent_turns=[],
            related_materials=[],
            summaries={},
        )
    )
    assert decision.used_fallback is False
    assert decision.player_intent == "调查泥痕"
    assert "真凶身份" in decision.forbidden_reveals


def test_director_falls_back_on_llm_failure(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    director = StoryDirector(router=ModelRouter(client=_ErrorClient()))
    decision = anyio.run(
        lambda: director.plan(
            game=game,
            player_input="我调查泥痕",
            selected_action_style=None,
            recent_turns=[],
            related_materials=[],
            summaries={},
        )
    )
    assert decision.used_fallback is True
    # fallback 仍给出可用的 player_intent（回退为玩家输入）
    assert decision.player_intent == "我调查泥痕"
