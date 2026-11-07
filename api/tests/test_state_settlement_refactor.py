import asyncio
from copy import deepcopy

import pytest
from sqlalchemy import event, select

from app.models.state_delta import StateDelta
from app.models.turn import Turn
from app.services import state_rebuilder
from app.services.deepseek_client import DeepSeekError
from app.services.game_creator import create_game_from_config
from app.services.state_rebuilder import rebuild_game_state
from app.services.state_settlement import StateSettlementError, StateSettlementService
from tests.story_settings_fixtures import build_generated_config


def _turn(db, game, number, status, delta=None):
    turn = Turn(game_id=game.id, turn_number=number, player_input="Observe", gm_output="Scene")
    db.add(turn)
    db.flush()
    if status is not None:
        db.add(StateDelta(
            game_id=game.id, turn_id=turn.id, status=status,
            delta_json=delta or {"new_known_facts": [f"fact_{number}"]},
        ))
    db.flush()
    return turn


class Extractor:
    def __init__(self, fail=False):
        self.seen = []
        self.fail = fail

    async def extract(self, game, turn):
        self.seen.append(deepcopy(game.state.state_json))
        if self.fail:
            raise DeepSeekError("Fixture extraction failure")
        return {"new_known_facts": [f"fact_{turn.turn_number}"]}


def test_settled_history_has_one_read_no_state_writes_and_returns_unchanged(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    for number in range(1, 11):
        _turn(db_session, game, number, "approved")
    service = StateSettlementService(extractor=Extractor())
    asyncio.run(service.ensure_settled(db_session, game))
    db_session.commit()
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    event.listen(db_session.bind, "before_cursor_execute", capture)
    try:
        changed = asyncio.run(service.ensure_settled(db_session, game))
    finally:
        event.remove(db_session.bind, "before_cursor_execute", capture)
    assert changed is False
    assert statements == ["SELECT"]


def test_tail_recovery_reads_once_and_applies_each_delta_once(db_session, monkeypatch):
    game = create_game_from_config(db_session, build_generated_config())
    _turn(db_session, game, 1, "approved")
    _turn(db_session, game, 2, "edited")
    last = _turn(db_session, game, 3, None)
    extractor = Extractor()
    # Gameplay loads these two fixed relationships before settlement. Count only
    # history reads here, independent of fixture/session expiration behavior.
    assert game.state is not None and game.config is not None
    calls = 0
    original = state_rebuilder.apply_state_delta

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(state_rebuilder, "apply_state_delta", counted)
    reads = []

    def capture(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            reads.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", capture)
    try:
        assert asyncio.run(
            StateSettlementService(extractor=extractor).ensure_settled(db_session, game)
        )
    finally:
        event.remove(db_session.bind, "before_cursor_execute", capture)
    assert len(reads) == 1
    assert calls == 3
    assert {"fact_1", "fact_2"} <= set(extractor.seen[0]["known_facts"])
    assert "fact_3" in game.state.state_json["known_facts"]
    assert last.settlement_receipt["status"] == "confirmed"


def test_historical_insertion_replays_later_approved_events_in_order(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    first = _turn(db_session, game, 1, None)
    second = _turn(db_session, game, 2, "approved", {"location_change": "Later scene"})

    class LocationExtractor(Extractor):
        async def extract(self, game, turn):
            self.seen.append(deepcopy(game.state.state_json))
            return {"location_change": "Earlier scene"}

    extractor = LocationExtractor()
    asyncio.run(StateSettlementService(extractor=extractor).ensure_settled(db_session, game))
    assert extractor.seen[0]["location"]["current"] == "Later scene"
    assert game.state.state_json["location"]["current"] == "Later scene"
    assert first.settlement_receipt["status"] == second.settlement_receipt["status"] == "confirmed"


def test_failed_retry_budget_survives_recovery_and_records_skipped_quality(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    turn = _turn(db_session, game, 1, "failed")
    service = StateSettlementService(extractor=Extractor(fail=True))
    for attempts in (3, 6):
        with pytest.raises(StateSettlementError):
            asyncio.run(service.ensure_settled(db_session, game))
        delta = db_session.scalars(select(StateDelta).where(StateDelta.turn_id == turn.id)).one()
        assert delta.attempt_count == attempts
        assert turn.settlement_receipt["status"] == "failed"
    asyncio.run(service.ensure_settled(db_session, game))
    assert delta.status == "approved"
    assert delta.attempt_count == 9
    assert delta.delta_json == {}
    assert turn.settlement_receipt["status"] == "skipped"


def test_rejected_delta_is_not_applied_and_keeps_rejected_receipt(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    turn = _turn(db_session, game, 1, "rejected")
    turn.state_delta_json = {"new_known_facts": ["must_not_apply"]}
    asyncio.run(StateSettlementService(extractor=Extractor()).ensure_settled(db_session, game))
    assert "fact_1" not in game.state.state_json["known_facts"]
    assert turn.state_delta_json == {}
    assert turn.settlement_receipt["status"] == "rejected"


def test_rebuild_uses_current_story_rules_after_settings_edit(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    story = deepcopy(game.config.story_settings)
    anchor_id = story["act_plan"][0]["completion_anchors"][0]["id"]
    _turn(db_session, game, 1, "approved", {
        "story_progress_update": {"completed_anchors": [anchor_id]},
    })
    rebuild_game_state(db_session, game)
    previous_total = game.state.state_json["story_progress"]["current_act_anchor_progress"]["total"]
    story["act_plan"][0]["completion_anchors"].append({
        "id": "new_requirement", "required": True, "title": "New requirement",
    })
    game.config.story_settings = story
    rebuild_game_state(db_session, game)
    assert game.state.state_json["story_progress"]["current_act_anchor_progress"] == {
        "done": 1, "total": previous_total + 1,
    }
