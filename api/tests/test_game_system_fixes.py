"""游戏系统修复（docs/GAME_SYSTEM_AUDIT.md 路线图）的回归测试。

纯函数级、不依赖数据库。当前覆盖：
- 阶段 1：字段契约根治（quest_id/thread_id 归一、僵尸空记录丢弃）
- 阶段 2：线索 resolve 与分桶（长句线索匹配、防复活、status 分桶、证据池排除线索）
"""

from app.services.state_applier import (
    _apply_upserts,
    _clean_thread_record,
    _merge_thread_record,
    _normalized_upsert_update,
    _state_evidence_units,
    _thread_matches_completed_anchor,
    _thread_matches_completed_quest,
)
from app.services.state_v2 import _thread_is_resolved

# ---------- 阶段 1：字段契约根治 ----------


def test_quest_id_normalized_to_id() -> None:
    """LLM 用 quest_id 作身份键应被归一到标准 id（否则下游取不到身份 → 僵尸记录）。"""
    out = _normalized_upsert_update(
        {"quest_id": "main_quest_1", "status": "completed"}, collection_key="quests"
    )
    assert out.get("id") == "main_quest_1"


def test_npc_id_normalized_to_id() -> None:
    out = _normalized_upsert_update(
        {"npc_id": "npc_7", "attitude": "友好"}, collection_key="npcs"
    )
    assert out.get("id") == "npc_7"


def test_existing_id_not_overwritten_by_alias() -> None:
    out = _normalized_upsert_update(
        {"id": "real_id", "quest_id": "other"}, collection_key="quests"
    )
    assert out.get("id") == "real_id"


def test_thread_id_normalized_to_id() -> None:
    out = _clean_thread_record(
        {"thread_id": "bai_rescue", "description": "线索描述", "status": "active"}
    )
    assert out.get("id") == "bai_rescue"


def test_apply_upserts_drops_identityless_zombie() -> None:
    """归一后仍无任何身份键的空壳记录应被丢弃，不产生僵尸任务。"""
    state: dict = {}
    _apply_upserts(state, "quests", [{"status": "active", "source": "explicit"}])
    assert state["quests"] == []


def test_apply_upserts_keeps_normalized_record() -> None:
    state: dict = {}
    _apply_upserts(state, "quests", [{"quest_id": "main_quest_1", "status": "completed"}])
    assert len(state["quests"]) == 1
    assert state["quests"][0]["id"] == "main_quest_1"


# ---------- 阶段 2：线索 resolve 与分桶 ----------


def test_long_thread_matches_completed_quest() -> None:
    """长句线索（topic 提取失败）应通过"已完成任务专名子串"匹配上（修 P1-2）。"""
    thread = {
        "thread_id": "bai_rescue",
        "description": "[地点]南麓居民区有女性幸存者角色D发出求救信号，被困第七天。",
        "status": "active",
    }
    quest = {"id": "main_quest_2", "title": "营救角色D", "status": "completed"}
    assert _thread_matches_completed_quest(thread, quest) is True


def test_long_thread_matches_completed_anchor() -> None:
    thread = {
        "description": "[地点]南麓居民区有女性幸存者角色D发出求救信号，被困第七天。",
        "status": "active",
    }
    anchor = {
        "id": "act_1_bai_rescued",
        "title": "营救角色D",
        "completion_signal": "角色D获救",
    }
    assert _thread_matches_completed_anchor(thread, anchor) is True


def test_two_char_topic_not_substring_matched() -> None:
    """2 字主题词不参与子串匹配（≥3 字门槛，避免 Round 16 式短词误杀）。"""
    # "探索星域" → 剥离"探索"前缀 → topic "星域"(2字) → 不走子串兜底
    thread = {"description": "夜空中闪过一道星域般的波动", "status": "active"}
    quest = {"id": "q", "title": "探索星域", "status": "completed"}
    assert _thread_matches_completed_quest(thread, quest) is False


def test_resolved_thread_not_revived_by_active_update() -> None:
    """已 resolved 的线索不被普通 active 更新复活（修 P1-3）。"""
    target = {"id": "t1", "title": "线索", "status": "resolved"}
    _merge_thread_record(target, {"id": "t1", "title": "线索", "status": "active"})
    assert target["status"] == "resolved"


def test_active_thread_can_be_resolved_by_merge() -> None:
    """正常 active→resolved 合并不受影响。"""
    target = {"id": "t1", "status": "active"}
    _merge_thread_record(target, {"id": "t1", "status": "resolved"})
    assert target["status"] == "resolved"


def test_thread_is_resolved_ignores_title_substring() -> None:
    """state_v2 分桶只看 status，不拿 title 子串误判（修 P1-4）。"""
    assert _thread_is_resolved({"title": "调查未完成的仪式", "status": "active"}) is False
    assert _thread_is_resolved({"title": "解决粮食危机", "status": "active"}) is False
    assert _thread_is_resolved({"title": "任意", "status": "resolved"}) is True


def test_thread_no_split_across_id_and_title_forms() -> None:
    """同一线索先以 {thread_id, description} 出现、后以 {title} resolve，应合并为一条而非分裂。

    复现真实存档 survivor_signal 分裂：早期回合带 thread_id+description（无 title），
    末期 resolve 只带 title（无 thread_id），归一后 id-key 与 title-key 对不上。
    """
    from app.services.state_applier import _apply_thread_updates

    desc = "废墟城市方向约两公里外有规律火光，疑似幸存者"
    state: dict = {}
    # 早期回合：带 thread_id + description（无 title）
    _apply_thread_updates(
        state,
        [{"thread_id": "survivor_signal", "description": desc, "status": "active"}],
    )
    # 末期 resolve：只带 title（== 早期 description）
    _apply_thread_updates(state, [{"title": desc, "status": "resolved"}])
    threads = state["open_threads"]
    assert len(threads) == 1, f"线索分裂成 {len(threads)} 条"
    assert threads[0].get("status") == "resolved"


def test_evidence_pool_excludes_open_threads() -> None:
    """证据池不含 open_threads（未解线索不能当锚点完成证据），但保留 known_facts（修 P2-1）。"""
    state = {
        "open_threads": [{"title": "秘密线索XYZ", "status": "active"}],
        "known_facts": ["事实ABC已发生"],
    }
    blob = "\n".join(_state_evidence_units(state))
    assert "秘密线索XYZ" not in blob
    assert "事实ABC已发生" in blob


# ---------- 阶段 3：砍脆弱字符串匹配 ----------


def test_quest_status_bucket_rejects_negation() -> None:
    """否定/进行中表述不被误判为完成（修 P2-4）。"""
    from app.services.state_applier import _quest_status_bucket

    assert _quest_status_bucket("未完成") == ""
    assert _quest_status_bucket("尚未完成") == ""
    assert _quest_status_bucket("无法解决") == ""
    assert _quest_status_bucket("进行中") == ""
    assert _quest_status_bucket("已完成") == "completed"
    assert _quest_status_bucket("completed") == "completed"
    assert _quest_status_bucket("failed") == "failed"


# ---------- 阶段 5：基础字段与数值 ----------


def test_inventory_remove_matches_across_item_and_name_keys() -> None:
    """删除指令用 name、库存项存 item 键时也能匹配删除（修 P1-5）。"""
    from app.services.state_applier import _apply_inventory

    state = {"inventory": [{"item": "压缩干粮", "quantity": 3}]}
    _apply_inventory(state, {"inventory_remove": [{"name": "压缩干粮"}]})
    assert state["inventory"] == []


def test_relationship_unknown_axis_skipped() -> None:
    """未知关系轴不默认计入 trust（修 P2-10）。"""
    from app.services.quantified_state import apply_quantified_state_events

    state: dict = {}
    apply_quantified_state_events(
        state,
        {"relationship_events": [{"npc": "测试NPC", "axis": "romance", "intensity": "major"}]},
    )
    assert all(
        r.get("trust", 0) == 0 for r in state.get("relationships", []) if isinstance(r, dict)
    )
