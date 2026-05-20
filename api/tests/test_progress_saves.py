from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models.game import Game
from app.models.generator_job import TurnJob
from app.models.state_delta import StateDelta
from app.models.summary import Summary
from app.models.turn import Turn
from app.services.game_creator import create_game_from_config
from tests.test_gameplay import build_generated_config

ACTION_OPTIONS = [
    {"key": "A", "label": "继续调查"},
    {"key": "B", "label": "询问证人"},
    {"key": "C", "label": "检查现场"},
    {"key": "D", "label": "暂时撤离"},
]


def test_progress_save_load_restores_progress_without_touching_settings(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    config_id = game.config.id
    worldview = dict(game.config.worldview)
    lore_ids = [entry.id for entry in game.lore_entries]
    mode_rules = [(mode.id, mode.injection) for mode in game.modes]
    turn = _add_turn(db_session, game.id, 1, "我检查门槛。", "发现泥痕。")
    _add_summary(db_session, game.id, "turn", 1, 1, "第一回合摘要。")
    _add_state_delta(db_session, game.id, turn.id, {"new_known_facts": ["泥痕"]})
    game.state.current_turn = 1
    game.state.state_json = {
        **game.state.state_json,
        "current_turn": 1,
        "inventory": ["赤铜鱼符"],
        "known_facts": ["门槛内侧有新鲜泥痕"],
        "story_progress": {
            "current_act": "act_2",
            "completed_acts": ["act_1"],
            "last_advance_turn": 1,
            "last_advance_reason": "义庄调查完成。",
            "act_history": [
                {
                    "turn": 1,
                    "from_act": "act_1",
                    "to_act": "act_2",
                    "reason": "义庄调查完成。",
                }
            ],
        },
    }
    db_session.add(game.state)
    db_session.commit()
    client = TestClient(app)

    create_response = client.post(
        f"/api/games/{game.id}/progress-saves",
        json={"name": "义庄泥痕", "note": "第一条线索后。"},
    )

    assert create_response.status_code == 201
    save = create_response.json()
    assert save["state_current_turn"] == 1
    assert save["turn_count"] == 1
    assert save["summary_count"] == 1

    _add_turn(db_session, game.id, 2, "我追到后院。", "后院空无一人。")
    _add_summary(db_session, game.id, "turn", 2, 2, "第二回合摘要。")
    game.state.current_turn = 2
    game.state.state_json = {
        **game.state.state_json,
        "current_turn": 2,
        "inventory": ["赤铜鱼符", "黑漆木牌"],
        "known_facts": ["门槛内侧有新鲜泥痕", "后院有人离开"],
        "story_progress": {
            "current_act": "act_3",
            "completed_acts": ["act_1", "act_2"],
            "last_advance_turn": 2,
            "last_advance_reason": "黑伞追踪完成。",
            "act_history": [],
        },
    }
    db_session.add(game.state)
    db_session.commit()

    load_response = client.post(f"/api/games/{game.id}/progress-saves/{save['id']}/load")

    assert load_response.status_code == 200
    body = load_response.json()
    assert body["state"]["current_turn"] == 1
    assert body["state"]["state_json"]["inventory"] == ["赤铜鱼符"]
    assert body["state"]["state_json"]["known_facts"] == ["门槛内侧有新鲜泥痕"]
    assert body["state"]["state_json"]["story_progress"]["current_act"] == "act_2"
    assert body["state"]["state_json"]["story_progress"]["completed_acts"] == ["act_1"]
    assert len(client.get(f"/api/games/{game.id}/turns").json()) == 1
    assert len(client.get(f"/api/games/{game.id}/memory").json()["summaries"]) == 1

    db_session.expire_all()
    saved_game = db_session.scalars(select(Game).where(Game.id == game.id)).one()
    assert saved_game.config.id == config_id
    assert saved_game.config.worldview == worldview
    assert [entry.id for entry in saved_game.lore_entries] == lore_ids
    assert [(mode.id, mode.injection) for mode in saved_game.modes] == mode_rules


def test_restart_progress_clears_runtime_only_and_keeps_saves(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    config_snapshot = {
        "config_id": game.config.id,
        "script_outline": dict(game.config.script_outline),
        "lore_titles": [entry.title for entry in game.lore_entries],
        "mode_names": [mode.name for mode in game.modes],
    }
    turn = _add_turn(db_session, game.id, 1, "我检查义庄。", "义庄里有旧账。")
    _add_summary(db_session, game.id, "long_term", 1, 1, "长期摘要。")
    _add_state_delta(db_session, game.id, turn.id, {"new_known_facts": ["旧账"]})
    game.state.current_turn = 1
    game.state.state_json = {
        **game.state.state_json,
        "current_turn": 1,
        "inventory": ["旧账残页"],
        "known_facts": ["旧账存在"],
        "story_progress": {
            "current_act": "act_2",
            "completed_acts": ["act_1"],
            "last_advance_turn": 1,
            "last_advance_reason": "进入下一幕。",
            "act_history": [],
        },
    }
    db_session.add(game.state)
    db_session.commit()
    client = TestClient(app)
    save_response = client.post(
        f"/api/games/{game.id}/progress-saves",
        json={"name": "重开前备份"},
    )
    assert save_response.status_code == 201

    restart_response = client.post(f"/api/games/{game.id}/progress/restart")

    assert restart_response.status_code == 200
    body = restart_response.json()
    assert body["state"]["current_turn"] == 0
    assert body["state"]["state_json"]["current_turn"] == 0
    assert body["state"]["state_json"]["location"]["current"] == "雁回镇义庄"
    assert body["state"]["state_json"]["inventory"] == []
    assert body["state"]["state_json"]["story_progress"]["current_act"] == "act_1"
    assert body["state"]["state_json"]["story_progress"]["completed_acts"] == []
    assert client.get(f"/api/games/{game.id}/turns").json() == []
    assert client.get(f"/api/games/{game.id}/memory").json()["summaries"] == []
    assert len(client.get(f"/api/games/{game.id}/progress-saves").json()) == 1

    db_session.expire_all()
    saved_game = db_session.scalars(select(Game).where(Game.id == game.id)).one()
    assert saved_game.config.id == config_snapshot["config_id"]
    assert saved_game.config.script_outline == config_snapshot["script_outline"]
    assert [entry.title for entry in saved_game.lore_entries] == config_snapshot["lore_titles"]
    assert [mode.name for mode in saved_game.modes] == config_snapshot["mode_names"]


def test_progress_operations_reject_active_turn_jobs(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    client = TestClient(app)
    save_response = client.post(
        f"/api/games/{game.id}/progress-saves",
        json={"name": "安全存档"},
    )
    assert save_response.status_code == 201
    db_session.add(
        TurnJob(
            game_id=game.id,
            status="pending",
            request_json={"player_input": "我继续前进。"},
        )
    )
    db_session.commit()

    blocked_create = client.post(
        f"/api/games/{game.id}/progress-saves",
        json={"name": "应被拒绝"},
    )
    blocked_load = client.post(
        f"/api/games/{game.id}/progress-saves/{save_response.json()['id']}/load"
    )
    blocked_restart = client.post(f"/api/games/{game.id}/progress/restart")

    assert blocked_create.status_code == 409
    assert blocked_load.status_code == 409
    assert blocked_restart.status_code == 409


def _add_turn(
    db_session,
    game_id,
    turn_number: int,
    player_input: str,
    gm_output: str,
) -> Turn:
    turn = Turn(
        game_id=game_id,
        turn_number=turn_number,
        player_input=player_input,
        gm_output=gm_output,
        visible_summary=gm_output,
        hidden_summary=None,
        state_delta_json={},
        action_options_json=ACTION_OPTIONS,
        model_used="test-model",
    )
    db_session.add(turn)
    db_session.flush()
    return turn


def _add_summary(
    db_session,
    game_id,
    summary_type: str,
    start_turn: int,
    end_turn: int,
    content: str,
) -> Summary:
    summary = Summary(
        game_id=game_id,
        type=summary_type,
        range_start_turn=start_turn,
        range_end_turn=end_turn,
        content=content,
        important_facts={"known_facts": []},
    )
    db_session.add(summary)
    db_session.flush()
    return summary


def _add_state_delta(db_session, game_id, turn_id, delta_json: dict) -> StateDelta:
    delta = StateDelta(
        game_id=game_id,
        turn_id=turn_id,
        delta_json=delta_json,
        status="approved",
    )
    db_session.add(delta)
    db_session.flush()
    return delta
