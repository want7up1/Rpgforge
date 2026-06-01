"""Round 23：GM 场景投影 project_state_for_scene 测试（纯函数，不依赖 DB）。"""

from app.services.state_v2 import project_state_for_scene

_STATE = {
    "version": 2,
    "active_scene": {"location": "厨房", "present_npcs": ["角色D"]},
    "party": ["角色D"],
    "protagonist_sheet": {"name": "主角"},
    "abilities": [{"name": "[异能]"}],
    "conditions": [],
    "skills": [{"name": "调查"}],
    "open_threads": [{"id": "t1"}],
    "story_progress": {"current_act": "act_1"},
    "progression": {"level": 2, "xp": 75, "xp_log": [{"amount": 20, "reason": "..."}]},
    "quest_log": {
        "active": [{"id": "q3", "title": "觉醒星域", "status": "active"}],
        "completed": [
            {"id": "q1", "title": "建立[地点]", "status": "completed"},
            {"id": "q2", "title": "营救角色D", "status": "completed"},
        ],
    },
    "npc_registry": [
        {"name": "角色D", "status": "在场"},
        {"name": "路人甲", "status": "已死亡"},
    ],
    "relationship_tracks": [
        {"npc": "角色D", "trust": 46, "recent_events": [{"r": "a"}, {"r": "b"}, {"r": "c"}]},
        {"npc": "角色F", "trust": 10, "recent_events": [{"r": "x"}]},
    ],
}


def test_projection_drops_xp_log_keeps_progression_summary() -> None:
    p = project_state_for_scene(_STATE)
    assert "xp_log" not in p["progression"]
    assert p["progression"]["level"] == 2 and p["progression"]["xp"] == 75


def test_projection_compacts_completed_quests_to_titles() -> None:
    p = project_state_for_scene(_STATE)
    assert [q["id"] for q in p["quest_log"]["active"]] == ["q3"]
    assert p["quest_log"]["completed_titles"] == ["建立[地点]", "营救角色D"]
    assert "completed" not in p["quest_log"]


def test_projection_keeps_only_onstage_npcs_and_relationships() -> None:
    p = project_state_for_scene(_STATE)
    # 只保留在场（角色D在 present/party；路人甲、角色F不在场）。
    assert [n["name"] for n in p["npc_registry"]] == ["角色D"]
    assert [r["npc"] for r in p["relationship_tracks"]] == ["角色D"]
    # recent_events 只留最近 1 条。
    assert p["relationship_tracks"][0]["recent_events"] == [{"r": "c"}]


def test_projection_keeps_scene_essentials_intact() -> None:
    p = project_state_for_scene(_STATE)
    for key in ("active_scene", "protagonist_sheet", "abilities", "skills",
                "conditions", "open_threads", "story_progress", "party"):
        assert p[key] == _STATE[key]


def test_projection_fallback_when_no_one_onstage() -> None:
    """present 名单为空时不过滤 NPC/关系（兜底防砍光）。"""
    state = {**_STATE, "active_scene": {"location": "x", "present_npcs": []}, "party": []}
    p = project_state_for_scene(state)
    assert len(p["npc_registry"]) == 2  # 未过滤
    assert len(p["relationship_tracks"]) == 2  # 未过滤


def test_projection_robust_to_none() -> None:
    assert project_state_for_scene(None) is None
    assert project_state_for_scene({}) == {}
