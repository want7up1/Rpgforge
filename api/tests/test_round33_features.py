"""Round 33（GAME_DIRECTION_AUDIT 第一梯队）回归测试。

覆盖：
- B1 结局闭环：末幕 required 锚点全完成 → story_progress.campaign_complete。
- C2 目标条：当前幕标题/目标派生进 story_progress。
- 序章/尾声生成器：LLM 失败时 fallback 返回空串（不阻断闭环/开局）。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.services.deepseek_client import DeepSeekError
from app.services.epilogue_generator import EpilogueGenerator
from app.services.opening_scene_generator import OpeningSceneGenerator
from app.services.state_applier import _sync_story_progress_and_quests


def _config(acts: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(story_settings={"act_plan": acts, "main_quest_path": []})


def _final_act() -> list[dict]:
    return [
        {
            "id": "act_1",
            "title": "终幕标题",
            "objective": "本幕玩家目标",
            "completion_anchors": [{"id": "a1", "required": True, "title": "锚点一"}],
        }
    ]


# ---------- B1 结局闭环 ----------


def test_campaign_complete_set_when_final_act_anchors_done() -> None:
    state = {"story_progress": {"current_act": "act_1", "completed_anchors": ["a1"]}}
    _sync_story_progress_and_quests(state, SimpleNamespace(turn_number=5), _config(_final_act()))
    assert state["story_progress"].get("campaign_complete") is True


def test_campaign_not_complete_when_required_anchor_pending() -> None:
    state = {"story_progress": {"current_act": "act_1", "completed_anchors": []}}
    _sync_story_progress_and_quests(state, SimpleNamespace(turn_number=5), _config(_final_act()))
    assert state["story_progress"].get("campaign_complete") is not True


def test_campaign_not_complete_when_not_on_final_act() -> None:
    acts = [
        {
            "id": "act_1",
            "title": "第一幕",
            "objective": "目标一",
            "completion_anchors": [{"id": "a1", "required": True}],
            "transition_to_next_act": {"target_act": "act_2"},
        },
        {
            "id": "act_2",
            "title": "终幕",
            "objective": "目标二",
            "completion_anchors": [{"id": "b1", "required": True}],
        },
    ]
    # 停在 act_1 并完成 act_1 锚点：会尝试转幕，但绝不能标记整局完成。
    state = {"story_progress": {"current_act": "act_1", "completed_anchors": ["a1"]}}
    _sync_story_progress_and_quests(state, SimpleNamespace(turn_number=3), _config(acts))
    # act_2（终幕）的 b1 未完成 → 不应 campaign_complete。
    assert state["story_progress"].get("campaign_complete") is not True


# ---------- C2 目标条 ----------


def test_current_act_title_and_objective_projected() -> None:
    state = {"story_progress": {"current_act": "act_1", "completed_anchors": []}}
    _sync_story_progress_and_quests(state, SimpleNamespace(turn_number=2), _config(_final_act()))
    assert state["story_progress"]["current_act_title"] == "终幕标题"
    assert state["story_progress"]["current_act_objective"] == "本幕玩家目标"


# ---------- 序章/尾声生成器 fallback ----------


class _RaisingRouter:
    async def use_pro(self, *args, **kwargs):
        raise DeepSeekError("boom")


class _OkRouter:
    def __init__(self, content: str) -> None:
        self._content = content

    async def use_pro(self, *args, **kwargs):
        return SimpleNamespace(content=self._content)


def test_epilogue_generator_returns_empty_on_llm_error() -> None:
    gen = EpilogueGenerator(router=_RaisingRouter())
    assert asyncio.run(gen.generate({})) == ""


def test_opening_generator_returns_empty_on_llm_error() -> None:
    gen = OpeningSceneGenerator(router=_RaisingRouter())
    assert asyncio.run(gen.generate({})) == ""


@pytest.mark.parametrize("gen_cls", [EpilogueGenerator, OpeningSceneGenerator])
def test_generator_returns_trimmed_content_on_success(gen_cls) -> None:
    gen = gen_cls(router=_OkRouter("  尾声/开场正文  "))
    assert asyncio.run(gen.generate({})) == "尾声/开场正文"
