"""Round 20 输出观测层纯函数测试（不依赖 DB）。"""

from app.services.output_observer import observe_gm_output

_RUNTIME_STORY = {
    "current_act": {
        "id": "act_1",
        "forbidden_reveals": ["账册真凶", "最终主谋身份"],
    },
    "story_core": {
        "canon_terms": ["雁回镇", "义庄", "黑伞客"],
    },
    "core_characters": [
        {"name": "陆沉舟", "aliases": ["黑伞客"]},
        {"name": "沈砚", "aliases": []},
        {"name": "老账房", "aliases": []},
    ],
}
_GEN_PARAMS = {
    "narrative_min_chars": 50,
    "narrative_target_min_chars": 80,
    "narrative_target_max_chars": 400,
    "paragraph_min": 2,
    "paragraph_max": 5,
    "scene_heading_max": 1,
    "emphasis_min": 1,
    "emphasis_max": 3,
}


def _options(n: int = 4) -> list[dict]:
    return [{"key": k, "label": f"行动{k}"} for k in ["A", "B", "C", "D"][:n]]


def test_observer_reports_generation_metrics_when_compliant() -> None:
    narrative = (
        "沈砚走进义庄，**门槛泥痕**仍在，泥土尚带湿气，像是有人刚翻入过。\n\n"
        "他在雁回镇四处打听，老账房欲言又止，似乎与黑伞客之间藏着一段旧怨。"
    )
    obs = observe_gm_output(
        narrative=narrative,
        visible_clues=["泥痕新鲜"],
        action_options=_options(4),
        runtime_story=_RUNTIME_STORY,
        generation_parameters=_GEN_PARAMS,
    )
    gen = obs["generation"]
    assert gen["meets_min_chars"] is True
    assert gen["paragraph_count"] == 2
    assert gen["paragraph_in_range"] is True
    assert gen["emphasis_count"] == 1
    assert gen["action_options_ok"] is True
    # 无违规 flag。
    assert obs["flags"] == []
    # 提及的剧本角色（整串 name+aliases；陆沉舟经别名"黑伞客"命中，记其 name）。
    assert set(obs["characters_mentioned"]) == {"沈砚", "陆沉舟", "老账房"}
    # canon 使用度：雁回镇/义庄/黑伞客 都出现。
    assert obs["canon"]["used"] == 3
    assert obs["canon"]["unused"] == []


def test_observer_flags_violations() -> None:
    # 字数不足、段落挤成一坨、选项数不对、命中 forbidden 整串。
    narrative = "账册真凶就是沈砚。**A****B****C****D**"
    obs = observe_gm_output(
        narrative=narrative,
        visible_clues=[],
        action_options=_options(2),
        runtime_story=_RUNTIME_STORY,
        generation_parameters=_GEN_PARAMS,
    )
    flags = obs["flags"]
    assert any("字数" in f for f in flags)
    assert any("段落数" in f for f in flags)  # 段落 < 下限（挤成一坨）仍报
    assert any("行动选项数" in f for f in flags)
    # 强调"超上限"不再算违规（让位于剧本详细描写要求）。
    assert not any("强调数" in f for f in flags)
    # 当前幕 forbidden_reveals 整串命中。
    assert "账册真凶" in obs["forbidden_reveal_hits"]
    assert any("禁止揭露" in f for f in flags)


def test_observer_does_not_flag_detailed_scene_overflow() -> None:
    """详细描写场景（大篇幅、多段、多强调）不应被判违规——上限让位于剧本。"""
    narrative = (
        "环境铺垫。\n\n前戏调情，**敏感带**反应。\n\n插入抽插，**身体痉挛**。\n\n"
        "高潮射精，**[能量]**注入。\n\n事后余韵，**情感值提升**。\n\n"
        "她的**乳房**、**臀**、**腰**都被细致刻画。" + "细节" * 400
    )
    obs = observe_gm_output(
        narrative=narrative,
        visible_clues=[],
        action_options=_options(4),
        runtime_story=_RUNTIME_STORY,
        generation_parameters=_GEN_PARAMS,
    )
    # 字数足、段落足、选项对、强调虽多但不报警。
    assert obs["flags"] == []
    assert obs["generation"]["emphasis_count"] >= 7  # 强调确实超上限，但不进 flags


def test_observer_canon_unused_tracked() -> None:
    obs = observe_gm_output(
        narrative="一段没有任何专名的普通叙述，足够长以满足字数要求啦啦啦啦啦啦啦。",
        visible_clues=[],
        action_options=_options(4),
        runtime_story=_RUNTIME_STORY,
        generation_parameters=_GEN_PARAMS,
    )
    assert obs["canon"]["used"] == 0
    assert set(obs["canon"]["unused"]) == {"雁回镇", "义庄", "黑伞客"}
    assert obs["forbidden_reveal_hits"] == []


def test_observer_flags_opening_repeat() -> None:
    """新回合开头逐字重复上一回合开头 → flag（重述同场景，Round 20b）。"""
    prev = "### [地点]厨房\n\n发电机低沉的嗡鸣声中，主角坐下。"
    cur = "### [地点]厨房\n\n发电机低沉的嗡鸣声里，他起身走向角色D。"
    obs = observe_gm_output(
        narrative=cur,
        visible_clues=[],
        action_options=_options(4),
        runtime_story=_RUNTIME_STORY,
        generation_parameters=_GEN_PARAMS,
        previous_narrative=prev,
    )
    assert obs["opening_repeat"]["repeat_chars"] >= 12
    assert any("开头与上一回合重复" in f for f in obs["flags"])


def test_observer_no_opening_repeat_when_scene_changes() -> None:
    """场景切换、开头不同 → 不 flag。"""
    prev = "### [地点]厨房\n\n发电机低沉的嗡鸣声中，主角坐下。"
    cur = "### 城南医院·后勤通道\n\n消毒水的气味扑面而来，角色D紧跟其后。"
    obs = observe_gm_output(
        narrative=cur,
        visible_clues=[],
        action_options=_options(4),
        runtime_story=_RUNTIME_STORY,
        generation_parameters=_GEN_PARAMS,
        previous_narrative=prev,
    )
    assert obs["opening_repeat"]["repeat_chars"] < 12
    assert not any("开头与上一回合重复" in f for f in obs["flags"])


def test_observer_robust_to_empty_inputs() -> None:
    obs = observe_gm_output(
        narrative="",
        visible_clues=None,
        action_options=None,
        runtime_story=None,
        generation_parameters=None,
    )
    assert obs["generation"]["narrative_chars"] == 0
    assert obs["characters_mentioned"] == []
    assert obs["forbidden_reveal_hits"] == []
    assert obs["canon"]["total"] == 0
