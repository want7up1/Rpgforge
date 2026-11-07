"""Semantic regressions found while reviewing applied, player-visible receipts."""

import json
from copy import deepcopy

import pytest

from app.services.settlement_receipts import build_settlement_receipt
from app.services.state_v2 import player_state_view, state_v2_view


def test_receipts_do_not_reveal_hidden_quest_thread_or_npc_fallback():
    after = {
        "quests": [{
            "id": "secret_quest", "title": "SECRET_QUEST", "status": "active",
            "visibility": "hidden", "objective": "SECRET_OBJECTIVE",
        }],
        "open_threads": [{
            "id": "secret_thread", "title": "SECRET_THREAD", "status": "active",
            "visibility": "hidden",
        }],
        "npcs": [{
            "name": "SECRET_NPC", "visibility": "hidden", "attitude": "SECRET_INTENTION",
        }],
    }
    gm_view = state_v2_view(after)
    assert "SECRET_INTENTION" in json.dumps(gm_view)
    receipt = build_settlement_receipt({}, after, {}, turn_number=1)
    assert "SECRET_" not in json.dumps(receipt)


def test_receipt_does_not_report_view_window_eviction_as_resolved_thread():
    threads = [
        {"id": f"clue_{i}", "title": f"Clue {i}", "status": "active"}
        for i in range(24)
    ]
    before = {"open_threads": threads}
    after = {"open_threads": [
        *threads, {"id": "clue_24", "title": "Clue 24", "status": "active"},
    ]}
    receipt = build_settlement_receipt(before, after, {}, turn_number=2)
    changes = [change for section in receipt["sections"] for change in section["changes"]]
    assert not any(change["subject"] == "Clue 0" for change in changes)
    assert any(change["subject"] == "Clue 24" for change in changes)


def test_visibility_change_is_not_confirmed_as_condition_removal():
    before = {"conditions": [{"name": "Poisoned", "status": "active", "visibility": "known"}]}
    after = {"conditions": [{"name": "Poisoned", "status": "active", "visibility": "hidden"}]}
    receipt = build_settlement_receipt(before, after, {}, turn_number=3)
    assert receipt["sections"] == []


def test_player_inventory_uses_common_gm_only_visibility_aliases():
    view = state_v2_view({"inventory": [
        {"name": "SECRET_DIRECTOR", "visibility": "director"},
        {"name": "SECRET_GM", "visibility": "gm_only"},
    ]})
    assert len(view["inventory"]) == 2
    assert player_state_view(view)["inventory"] == []


@pytest.mark.parametrize("reference", ["SECRET_NPC", "secret_alias", "secret_id"])
@pytest.mark.parametrize("visibility", [None, "known"])
def test_explicit_relationship_inherits_hidden_npc_visibility(reference, visibility):
    relation = {"npc": reference, "status": "SECRET_ATTITUDE"}
    if visibility is not None:
        relation["visibility"] = visibility
    state = {
        "npcs": [{
            "id": "SECRET_ID", "name": "SECRET_NPC", "aliases": ["SECRET_ALIAS"],
            "visibility": "hidden",
        }],
        "relationships": [relation],
    }
    original = deepcopy(state)
    gm = state_v2_view(state)
    assert gm["relationship_tracks"][0]["status"] == "SECRET_ATTITUDE"
    assert state == original
    assert player_state_view(gm)["relationship_tracks"] == []
    receipt = build_settlement_receipt({}, state, {}, turn_number=1)
    assert "SECRET_" not in json.dumps(receipt)
    assert "secret_alias" not in json.dumps(receipt)
    assert "secret_id" not in json.dumps(receipt)


def test_receipt_uses_canonical_hidden_npc_metadata_for_legacy_known_projection():
    state = {
        "npcs": [{"name": "SECRET_NPC", "aliases": ["SECRET_ALIAS"], "visibility": "hidden"}],
        "relationships": [{"npc": "SECRET_ALIAS", "status": "SECRET_ATTITUDE"}],
    }
    state["v2"] = state_v2_view(state)
    state["v2"]["relationship_tracks"][0]["visibility"] = "known"
    state["v2"]["npc_registry"] = [{"name": "SECRET_NPC"}]
    assert build_settlement_receipt({}, state, {}, turn_number=1)["sections"] == []


def test_hiding_npc_does_not_report_still_existing_relationship_as_lost():
    before = {
        "npcs": [{"name": "Archivist", "visibility": "known"}],
        "relationships": [{"npc": "Archivist", "status": "Cooperating"}],
    }
    after = deepcopy(before)
    after["npcs"][0]["visibility"] = "hidden"
    assert build_settlement_receipt(before, after, {}, turn_number=1)["sections"] == []


def test_known_npc_relationship_changes_remain_visible():
    state = {
        "npcs": [{"name": "Archivist", "visibility": "known"}],
        "relationships": [{"npc": "Archivist", "status": "Cooperating"}],
    }
    assert player_state_view(state_v2_view(state))["relationship_tracks"][0]["npc"] == "Archivist"
    receipt = build_settlement_receipt({}, state, {}, turn_number=1)
    assert receipt["sections"][0]["changes"][0]["after"] == "Cooperating"
