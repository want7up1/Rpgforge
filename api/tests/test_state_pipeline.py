"""context_compressor fallback + state_extractor hints 注入测试。"""

import json

import anyio

from app.models.turn import Turn
from app.services.context_compressor import ContextCompressor, _trim_text
from app.services.deepseek_client import ChatCompletionResult
from app.services.game_creator import create_game_from_config
from app.services.model_router import ModelRouter
from app.services.state_extractor import StateDeltaExtraction, StateExtractor
from tests.story_settings_fixtures import build_generated_config

# ---------- context_compressor 纯逻辑 ----------

def test_trim_text_short_unchanged() -> None:
    assert _trim_text("短文本", 100) == "短文本"


def test_trim_text_collapses_whitespace_and_truncates() -> None:
    out = _trim_text("a   b\n\nc" + "x" * 100, 10)
    assert len(out) <= 10
    assert out.endswith("…")


def test_fallback_summary_builds_from_delta() -> None:
    turn = Turn(
        turn_number=3,
        player_input="我搜查房间",
        gm_output="房间里有一封信。",
        visible_summary="发现一封信",
    )
    delta = {
        "new_known_facts": ["信来自陆沉舟"],
        "new_hidden_facts": ["信是伪造的"],
        "open_thread_updates": ["查清写信人"],
    }
    out = ContextCompressor()._fallback_summary(turn, delta, existing_summaries={})
    assert out.turn_visible_summary == "发现一封信"
    assert "信来自陆沉舟" in out.important_facts["known_facts"]
    assert "信是伪造的" in out.important_facts["hidden_facts"]
    # 幕后信息进 hidden_summary，不混入玩家可见
    assert "信是伪造的" in (out.turn_hidden_summary or "")


# ---------- state_extractor hints 注入 ----------


def test_state_delta_extraction_omits_removed_numeric_mechanics() -> None:
    """纯叙事化：delta 契约不再暴露 XP/技能/能力旧字段。"""
    delta = StateDeltaExtraction.model_validate({}).model_dump()

    assert "xp_events" not in delta
    assert "skill_events" not in delta
    assert "ability_updates" not in delta

class _CapturingClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.last_user_content: str | None = None

    async def chat_completion(self, **kwargs):
        # messages[1] 是 user payload（JSON 字符串）
        self.last_user_content = kwargs["messages"][1]["content"]
        return ChatCompletionResult(
            content=json.dumps(self._payload, ensure_ascii=False),
            model=kwargs["model"],
            raw={},
        )


def _make_game_turn(db):
    game = create_game_from_config(db, build_generated_config())
    turn = Turn(
        game_id=game.id,
        turn_number=1,
        player_input="我调查泥痕",
        gm_output="门槛内侧有新鲜泥痕。",
        visible_summary="发现泥痕",
        state_delta_json={},
        action_options_json=[],
        model_used="t",
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)
    return game, turn


def test_extract_injects_director_and_drift_hints(db_session) -> None:
    game, turn = _make_game_turn(db_session)
    client = _CapturingClient({})  # 空 delta
    extractor = StateExtractor(router=ModelRouter(client=client))

    result = anyio.run(
        lambda: extractor.extract(
            game,
            turn,
            director_decision={
                "continuity_notes": ["保持 NPC 态度"],
                "scene_objective": "找线索",
                "player_intent": "应被丢弃",
            },
            drift_findings={"state_conflicts": ["物品冲突"], "severity": "minor"},
        )
    )
    # 返回是结构化 delta dict
    assert isinstance(result, dict)
    assert "inventory_add" in result

    # payload 注入了精简后的 hints
    payload = json.loads(client.last_user_content)
    assert payload["director_hints"]["continuity_notes"] == ["保持 NPC 态度"]
    assert payload["director_hints"]["scene_objective"] == "找线索"
    assert "player_intent" not in payload["director_hints"]
    assert payload["drift_hints"]["state_conflicts"] == ["物品冲突"]
    assert payload["drift_hints"]["severity"] == "minor"


def test_extract_without_hints_omits_keys(db_session) -> None:
    game, turn = _make_game_turn(db_session)
    client = _CapturingClient({})
    extractor = StateExtractor(router=ModelRouter(client=client))
    anyio.run(lambda: extractor.extract(game, turn))
    payload = json.loads(client.last_user_content)
    assert "director_hints" not in payload
    assert "drift_hints" not in payload
