"""Round 1-7 新增基础设施的纯函数单元测试。

这些测试不依赖数据库（不使用 db_session fixture），覆盖 trace / judge /
gameplay 的纯逻辑，作为实现的规格说明与回归保护。
"""

from app.services.agent_traces import extract_usage
from app.services.gameplay import GameplayService
from app.services.state_extractor import _director_hints, _drift_hints
from app.services.story_director import StoryDirectorDecision
from app.services.story_settings import StoryMaterialResult
from app.services.turn_judge import JudgeResult


# ---------- agent_traces.extract_usage ----------

def test_extract_usage_none_and_empty() -> None:
    assert extract_usage(None) == (None, None, None)
    assert extract_usage({}) == (None, None, None)
    assert extract_usage({"usage": "not-a-dict"}) == (None, None, None)


def test_extract_usage_basic() -> None:
    raw = {"usage": {"prompt_tokens": 120, "completion_tokens": 340}}
    assert extract_usage(raw) == (120, 340, None)


def test_extract_usage_reasoning_tokens() -> None:
    raw = {
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "completion_tokens_details": {"reasoning_tokens": 7},
        }
    }
    assert extract_usage(raw) == (10, 20, 7)


def test_extract_usage_garbage_values() -> None:
    raw = {"usage": {"prompt_tokens": "x", "completion_tokens": None}}
    assert extract_usage(raw) == (None, None, None)


# ---------- turn_judge.JudgeResult clamp ----------

def test_judge_result_clamps_to_1_5() -> None:
    result = JudgeResult.model_validate(
        {
            "canon_fidelity": 9,
            "state_consistency": 0,
            "pacing": 3,
            "prose_quality": -2,
            "freshness": 5,
            "safety": 4,
        }
    )
    assert result.canon_fidelity == 5  # clamped from 9
    assert result.state_consistency == 1  # clamped from 0
    assert result.pacing == 3
    assert result.prose_quality == 1  # clamped from -2
    assert result.freshness == 5
    assert result.safety == 4


def test_judge_result_handles_missing_and_invalid() -> None:
    result = JudgeResult.model_validate({"canon_fidelity": "oops"})
    assert result.canon_fidelity is None
    assert result.pacing is None


# ---------- GameplayService._filter_materials_by_director ----------

def _material(title: str) -> StoryMaterialResult:
    return StoryMaterialResult(material={"title": title}, score=1.0, matched_terms=[])


def test_filter_materials_empty_titles_returns_all() -> None:
    materials = [_material("A"), _material("B")]
    out = GameplayService._filter_materials_by_director(materials, [])
    assert out is materials  # 同一对象，未过滤


def test_filter_materials_no_match_falls_back_to_all() -> None:
    materials = [_material("A"), _material("B")]
    out = GameplayService._filter_materials_by_director(materials, ["Z"])
    assert out is materials  # 空集退回全集，避免 GM 失盲


def test_filter_materials_partial_match() -> None:
    materials = [_material("雁回镇义庄"), _material("黑伞客"), _material("旧案")]
    out = GameplayService._filter_materials_by_director(materials, ["黑伞客", "旧案"])
    titles = [r.material["title"] for r in out]
    assert titles == ["黑伞客", "旧案"]


def test_filter_materials_strips_whitespace_titles() -> None:
    materials = [_material("A"), _material("B")]
    out = GameplayService._filter_materials_by_director(materials, ["  A  ", "   "])
    assert [r.material["title"] for r in out] == ["A"]


# ---------- GameplayService._enforce_hard_forbidden_reveals ----------

def test_enforce_merges_script_forbidden_items() -> None:
    decision = StoryDirectorDecision(forbidden_reveals=["已有项"])
    runtime_story = {
        "current_act": {"forbidden_reveals": ["幕禁止揭露"]},
        "story_core": {
            "forbidden_drift": ["禁止跑偏"],
            "must_not_become": ["禁止变成"],
        },
    }
    GameplayService._enforce_hard_forbidden_reveals(decision, runtime_story=runtime_story)
    assert "已有项" in decision.forbidden_reveals
    assert "幕禁止揭露" in decision.forbidden_reveals
    assert "禁止跑偏" in decision.forbidden_reveals
    assert "禁止变成" in decision.forbidden_reveals


def test_enforce_does_not_merge_must_hit_beats() -> None:
    """回归：must_hit_beats 是'必须发生'，绝不能当成'禁止揭露'。"""
    decision = StoryDirectorDecision(forbidden_reveals=[])
    runtime_story = {
        "current_act": {
            "forbidden_reveals": ["真凶身份"],
            "must_hit_beats": ["玩家必须找到泥痕"],
        },
    }
    GameplayService._enforce_hard_forbidden_reveals(decision, runtime_story=runtime_story)
    assert "真凶身份" in decision.forbidden_reveals
    assert "玩家必须找到泥痕" not in decision.forbidden_reveals


def test_enforce_dedupes() -> None:
    decision = StoryDirectorDecision(forbidden_reveals=["重复项"])
    runtime_story = {"story_core": {"forbidden_drift": ["重复项"]}}
    GameplayService._enforce_hard_forbidden_reveals(decision, runtime_story=runtime_story)
    assert decision.forbidden_reveals.count("重复项") == 1


def test_enforce_empty_runtime_story_is_noop() -> None:
    decision = StoryDirectorDecision(forbidden_reveals=["原项"])
    GameplayService._enforce_hard_forbidden_reveals(decision, runtime_story={})
    assert decision.forbidden_reveals == ["原项"]


# ---------- state_extractor._director_hints / _drift_hints ----------

def test_director_hints_none_and_non_dict() -> None:
    assert _director_hints(None) == {}
    assert _director_hints("nope") == {}  # type: ignore[arg-type]


def test_director_hints_keeps_relevant_fields() -> None:
    decision = {
        "continuity_notes": ["保持 NPC 态度一致"],
        "scene_objective": "调查泥痕",
        "current_act": "act_1",
        "pacing_limit": "不升级",
        "active_material_titles": ["义庄"],
        "forbidden_reveals": ["真凶"],
        "player_intent": "should be dropped",
    }
    hints = _director_hints(decision)
    assert hints["continuity_notes"] == ["保持 NPC 态度一致"]
    assert hints["scene_objective"] == "调查泥痕"
    assert hints["current_act"] == "act_1"
    assert "player_intent" not in hints


def test_director_hints_drops_empty_values() -> None:
    decision = {"continuity_notes": [], "scene_objective": "   "}
    assert _director_hints(decision) == {}


def test_drift_hints_keeps_lists_and_severity() -> None:
    findings = {
        "state_conflicts": ["物品冲突"],
        "contract_violations": [],
        "issues": ["小问题"],
        "severity": "major",
        "approved": False,
    }
    hints = _drift_hints(findings)
    assert hints["state_conflicts"] == ["物品冲突"]
    assert "contract_violations" not in hints  # 空 list 丢弃
    assert hints["issues"] == ["小问题"]
    assert hints["severity"] == "major"
    assert "approved" not in hints


def test_drift_hints_none() -> None:
    assert _drift_hints(None) == {}
