from copy import deepcopy
from types import SimpleNamespace

from app.services.context_continuity import recent_continuity_facts, recent_narrative_excerpt
from app.services.settlement_receipts import build_settlement_receipt
from app.services.state_v2 import player_state_view, project_state_for_scene, state_v2_view


def test_inventory_survives_gm_projection_but_hidden_items_stay_out_of_player_receipt():
    state = {"inventory": ["钥匙", {"name": "暗记", "visibility": "hidden"}]}
    view = state_v2_view(state)
    assert [item["name"] for item in project_state_for_scene(view)["inventory"]] == ["钥匙", "暗记"]
    assert [item["name"] for item in player_state_view(view)["inventory"]] == ["钥匙"]
    receipt = build_settlement_receipt({}, state, {}, turn_number=1)
    changes = next(s for s in receipt["sections"] if s["key"] == "inventory")["changes"]
    assert [change["subject"] for change in changes] == ["钥匙"]
    assert len(state["inventory"]) == 2


def test_receipt_reports_applied_progress_and_ignores_unapplied_requests():
    old = {"story_progress": {"current_act": "act_1", "completed_anchors": []}}
    after = deepcopy(old)
    after["story_progress"].update(
        {
            "completed_anchors": ["evidence"],
            "anchor_history": [{"turn": 3, "anchor_id": "evidence", "reason": "已取得运单"}],
        }
    )
    requested = {"story_progress_update": {"completed_anchors": ["evidence", "invented"]}}
    receipt = build_settlement_receipt(old, after, requested, turn_number=3)
    change = receipt["sections"][0]["changes"][0]
    assert change["after"] == "确认完成 1 项剧情条件"
    assert change["reason"] == "已取得运单"
    assert "invented" not in str(receipt)
    assert build_settlement_receipt(old, old, requested, turn_number=3)["sections"] == []


def test_receipt_separates_no_change_from_failed_or_skipped_and_hides_private_relationships():
    state = {"relationships": [{"npc": "陌生人", "status": "卧底", "visibility": "hidden"}]}
    assert build_settlement_receipt({}, state, {}, turn_number=1)["sections"] == []
    for status in ("pending", "failed", "skipped", "rejected"):
        receipt = build_settlement_receipt({}, state, {}, turn_number=1, status=status)
        assert receipt["status"] == status
        assert receipt["sections"] == []


def test_recent_excerpt_preserves_opening_and_last_beat_with_same_budget():
    narrative = "开场：仓库门被推开。" + "中段描述" * 1000 + "落点：她把钥匙塞进你的掌心。"
    excerpt = recent_narrative_excerpt(narrative, 1800)
    assert len(excerpt) == 1800
    assert excerpt.startswith("开场：仓库门被推开。")
    assert excerpt.endswith("落点：她把钥匙塞进你的掌心。")
    assert recent_narrative_excerpt("短章节", 1800) == "短章节"


def test_continuity_facts_withdraw_after_recovery_without_changing_past_turns():
    opening = "仓库门口的雨水一直沿着屋檐落下来。"
    turns = [SimpleNamespace(turn_number=n, gm_output=opening + str(n)) for n in (1, 2, 3)]
    assert recent_continuity_facts(turns)["turn_numbers"] == [2, 3]
    turns.append(SimpleNamespace(turn_number=4, gm_output="她把运单摊在桌面，指向同一个签名。"))
    assert recent_continuity_facts(turns) == {}
