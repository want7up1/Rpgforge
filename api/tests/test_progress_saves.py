from copy import deepcopy

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models.summary import Summary
from app.models.turn import Turn
from app.services.game_creator import create_game_from_config
from tests.story_settings_fixtures import build_generated_config


def test_progress_save_load_restores_progress_without_changing_settings(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    original_settings = deepcopy(game.config.story_settings)
    game.state.current_turn = 1
    game.state.state_json = {
        **game.state.state_json,
        "current_turn": 1,
        "known_facts": ["门槛内侧有新鲜泥痕"],
    }
    db_session.add(
        Turn(
            game_id=game.id,
            turn_number=1,
            player_input="我检查门槛。",
            gm_output="门槛内侧有新鲜泥痕。",
            visible_summary="发现泥痕。",
            hidden_summary=None,
            state_delta_json={},
            action_options_json=[],
            model_used="deepseek-v4-pro-test",
        )
    )
    db_session.add(
        Summary(
            game_id=game.id,
            type="turn",
            range_start_turn=1,
            range_end_turn=1,
            content="第一回合发现泥痕。",
            important_facts={},
        )
    )
    db_session.commit()

    client = TestClient(app)
    create_response = client.post(
        f"/api/games/{game.id}/progress-saves",
        json={"name": "发现泥痕后", "note": "第一回合"},
    )
    assert create_response.status_code == 201
    save_id = create_response.json()["id"]

    game.state.current_turn = 2
    game.state.state_json = {
        **game.state.state_json,
        "current_turn": 2,
        "known_facts": ["门槛内侧有新鲜泥痕", "临时推进后事实"],
    }
    db_session.add(
        Turn(
            game_id=game.id,
            turn_number=2,
            player_input="我追出义庄。",
            gm_output="院外只剩雨声。",
            visible_summary="离开义庄。",
            hidden_summary=None,
            state_delta_json={},
            action_options_json=[],
            model_used="deepseek-v4-pro-test",
        )
    )
    db_session.commit()

    load_response = client.post(f"/api/games/{game.id}/progress-saves/{save_id}/load")

    assert load_response.status_code == 200
    body = load_response.json()
    assert body["config"]["story_settings"] == original_settings
    assert body["state"]["current_turn"] == 1
    assert body["state"]["state_json"]["known_facts"] == ["门槛内侧有新鲜泥痕"]
    db_session.expire_all()
    restored_turns = list(
        db_session.scalars(select(Turn).where(Turn.game_id == game.id).order_by(Turn.turn_number))
    )
    assert [turn.turn_number for turn in restored_turns] == [1]
    assert db_session.get(type(game), game.id).config.story_settings == original_settings


def test_restart_progress_resets_state_and_keeps_story_settings(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    original_settings = deepcopy(game.config.story_settings)
    game.state.current_turn = 2
    game.state.state_json = {
        **game.state.state_json,
        "current_turn": 2,
        "known_facts": ["后续游玩事实"],
    }
    db_session.add(
        Turn(
            game_id=game.id,
            turn_number=1,
            player_input="我检查门槛。",
            gm_output="门槛内侧有新鲜泥痕。",
            visible_summary="发现泥痕。",
            hidden_summary=None,
            state_delta_json={},
            action_options_json=[],
            model_used="deepseek-v4-pro-test",
        )
    )
    db_session.commit()

    response = TestClient(app).post(f"/api/games/{game.id}/progress/restart")

    assert response.status_code == 200
    body = response.json()
    assert body["config"]["story_settings"] == original_settings
    assert body["state"]["current_turn"] == 0
    assert body["state"]["state_json"]["story_progress"]["current_act"] == "act_1"
    db_session.expire_all()
    assert db_session.get(type(game), game.id).config.story_settings == original_settings
    assert list(db_session.scalars(select(Turn).where(Turn.game_id == game.id))) == []


def test_progress_save_update_delete_and_list(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    client = TestClient(app)
    created = client.post(
        f"/api/games/{game.id}/progress-saves",
        json={"name": "初始存档"},
    ).json()

    update_response = client.patch(
        f"/api/games/{game.id}/progress-saves/{created['id']}",
        json={"name": "改名存档", "note": "已改名"},
    )
    list_response = client.get(f"/api/games/{game.id}/progress-saves")
    delete_response = client.delete(f"/api/games/{game.id}/progress-saves/{created['id']}")
    list_after_delete = client.get(f"/api/games/{game.id}/progress-saves")

    assert update_response.status_code == 200
    assert update_response.json()["name"] == "改名存档"
    assert len(list_response.json()) == 1
    assert delete_response.status_code == 204
    assert list_after_delete.json() == []
