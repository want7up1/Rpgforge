"""C6 后悔药：回退到第 N 回合 的集成测试（需 DB）。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.models.state_delta import StateDelta
from app.models.turn import Turn
from app.services.game_creator import create_game_from_config
from app.services.state_rebuilder import approve_turn_state_delta, rebuild_game_state
from app.services.turn_rewind import rewind_game_to_turn
from tests.story_settings_fixtures import build_two_act_config


def _add_turn(db, game, n: int) -> Turn:
    turn = Turn(
        game_id=game.id,
        turn_number=n,
        player_input=f"行动{n}",
        gm_output=f"剧情{n}",
        state_delta_json={},
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)
    approve_turn_state_delta(
        db,
        game=game,
        turn=turn,
        delta_json={"new_known_facts": [f"fact{n}"]},
        approved_at=datetime.now(UTC),
    )
    rebuild_game_state(db, game)
    db.commit()
    return turn


def test_rewind_deletes_later_turns_and_cascades_deltas(db_session) -> None:
    game = create_game_from_config(db_session, build_two_act_config())
    for n in range(1, 4):
        _add_turn(db_session, game, n)

    removed = rewind_game_to_turn(db_session, game, 1)

    assert removed == 2
    remaining = db_session.scalars(
        select(Turn).where(Turn.game_id == game.id)
    ).all()
    assert {t.turn_number for t in remaining} == {1}
    # StateDelta 随回合级联删除。
    deltas = db_session.scalars(
        select(StateDelta).where(StateDelta.game_id == game.id)
    ).all()
    assert {d.turn.turn_number for d in deltas} == {1}
    # 重建后状态只含第 1 回合的事实。
    facts = game.state.state_json.get("known_facts") or []
    assert any("fact1" in str(f) for f in facts)
    assert not any("fact2" in str(f) or "fact3" in str(f) for f in facts)


def test_rewind_reactivates_ended_game(db_session) -> None:
    game = create_game_from_config(db_session, build_two_act_config())
    _add_turn(db_session, game, 1)
    _add_turn(db_session, game, 2)
    game.status = "defeated"
    db_session.commit()

    rewind_game_to_turn(db_session, game, 1)

    assert game.status == "active"


def test_rewind_noop_when_target_is_latest(db_session) -> None:
    game = create_game_from_config(db_session, build_two_act_config())
    _add_turn(db_session, game, 1)

    removed = rewind_game_to_turn(db_session, game, 5)

    assert removed == 0
