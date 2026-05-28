"""TurnJudge / evaluate_turn 测试（fake router，不发真实 LLM）。"""

import json

import anyio

from app.models.turn import Turn
from app.services.deepseek_client import ChatCompletionResult, DeepSeekAPIError
from app.services.game_creator import create_game_from_config
from app.services.model_router import ModelRouter
from app.services.turn_judge import TurnJudge, evaluate_turn
from tests.story_settings_fixtures import build_generated_config


class _FakeClient:
    """返回固定 JSON 的假 DeepSeek client。"""

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


def _judge_with(payload: dict) -> TurnJudge:
    return TurnJudge(router=ModelRouter(client=_FakeClient(payload)))


def _make_game_and_turn(db):
    game = create_game_from_config(db, build_generated_config())
    turn = Turn(
        game_id=game.id,
        turn_number=1,
        player_input="我调查泥痕",
        gm_output="门槛内侧有新鲜泥痕。",
        visible_summary="发现泥痕",
        hidden_summary=None,
        state_delta_json={},
        action_options_json=[],
        model_used="deepseek-v4-pro-test",
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)
    return game, turn


def test_judge_computes_overall_when_missing(db_session) -> None:
    game, turn = _make_game_and_turn(db_session)
    judge = _judge_with(
        {
            "canon_fidelity": 4,
            "state_consistency": 5,
            "pacing": 3,
            "prose_quality": 4,
            "freshness": 4,
            "safety": 5,
            # 故意不给 overall_score
            "rationale": {"pacing": "稍快"},
        }
    )
    result = anyio.run(judge.judge, game, turn)
    # (4+5+3+4+4+5)/6 = 4.1666... -> 4.17
    assert result.overall_score == 4.17


def test_judge_respects_explicit_overall(db_session) -> None:
    game, turn = _make_game_and_turn(db_session)
    judge = _judge_with(
        {
            "canon_fidelity": 2,
            "state_consistency": 2,
            "pacing": 2,
            "prose_quality": 2,
            "freshness": 2,
            "safety": 2,
            "overall_score": 3.5,
        }
    )
    result = anyio.run(judge.judge, game, turn)
    assert result.overall_score == 3.5


def test_evaluate_turn_persists_success(db_session) -> None:
    game, turn = _make_game_and_turn(db_session)
    judge = _judge_with(
        {
            "canon_fidelity": 5,
            "state_consistency": 5,
            "pacing": 4,
            "prose_quality": 4,
            "freshness": 3,
            "safety": 5,
            "overall_score": 4.33,
            "rationale": {"freshness": "略重复"},
        }
    )
    evaluation = anyio.run(lambda: evaluate_turn(db_session, turn.id, judge=judge))
    assert evaluation.status == "success"
    assert evaluation.canon_fidelity == 5
    assert float(evaluation.overall_score) == 4.33
    assert evaluation.rationale == {"freshness": "略重复"}
    assert evaluation.game_id == game.id


def test_evaluate_turn_records_error_on_llm_failure(db_session) -> None:
    _game, turn = _make_game_and_turn(db_session)
    judge = TurnJudge(router=ModelRouter(client=_ErrorClient()))
    evaluation = anyio.run(lambda: evaluate_turn(db_session, turn.id, judge=judge))
    assert evaluation.status == "error"
    assert evaluation.error_message
    assert evaluation.overall_score is None
