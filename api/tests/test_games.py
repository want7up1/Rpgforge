from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.main import app
from app.models.character import Character
from app.models.game import Game
from app.models.generator_job import TurnJob
from app.models.summary import Summary
from app.models.turn import Turn
from app.services.game_creator import create_game_from_config
from tests.test_gameplay import build_generated_config


def test_create_and_read_manual_game(reset_database) -> None:
    client = TestClient(app)

    create_response = client.post(
        "/api/games",
        json={
            "title": "雁回镇旧案",
            "genre": "黑暗武侠",
            "description": "失忆镖师追查义庄旧案。",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["title"] == "雁回镇旧案"
    assert created["config"]["worldview"]["genre"] == "黑暗武侠"
    assert created["state"]["current_turn"] == 0
    assert created["state"]["state_json"]["progression"]["level"] == 1
    assert created["state"]["state_json"]["skills"] == []
    assert created["state"]["state_json"]["abilities"] == []
    assert created["state"]["state_json"]["conditions"] == []
    assert created["state"]["state_json"]["relationships"] == []
    assert created["state"]["state_json"]["v2"]["progression"]["next_level_xp"] == 100

    list_response = client.get("/api/games")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    detail_response = client.get(f"/api/games/{created['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == created["id"]


def test_delete_game_removes_game_data_and_portraits(db_session, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "portrait_storage_path", str(tmp_path))
    game = create_game_from_config(db_session, build_generated_config())
    game_id = game.id
    character = db_session.scalars(
        select(Character).where(Character.game_id == game_id)
    ).first()
    portrait_dir = tmp_path / str(game_id)
    portrait_dir.mkdir(parents=True)
    portrait_path = portrait_dir / f"{character.id}.png"
    portrait_path.write_bytes(b"portrait")
    character.portrait_path = str(portrait_path)
    character.portrait_mime_type = "image/png"
    db_session.add(character)
    db_session.commit()

    client = TestClient(app)
    response = client.delete(f"/api/games/{game_id}")

    assert response.status_code == 204
    db_session.expire_all()
    assert db_session.get(Game, game_id) is None
    assert not portrait_path.exists()
    assert not portrait_dir.exists()
    assert client.get(f"/api/games/{game_id}").status_code == 404


def test_delete_game_rejects_active_turn_job(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    job = TurnJob(
        game_id=game.id,
        status="running",
        request_json={"player_input": "我继续前进。"},
    )
    db_session.add(job)
    db_session.commit()

    client = TestClient(app)
    response = client.delete(f"/api/games/{game.id}")

    assert response.status_code == 409
    assert db_session.get(Game, game.id) is not None


def test_game_memory_endpoint_exposes_lore_and_summaries(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    db_session.add(
        Summary(
            game_id=game.id,
            type="long_term",
            range_start_turn=1,
            range_end_turn=1,
            content="长期记忆：义庄旧案与黑伞客有关。",
            important_facts={"known_facts": ["黑伞客"]},
        )
    )
    db_session.commit()
    client = TestClient(app)

    response = client.get(f"/api/games/{game.id}/memory")

    assert response.status_code == 200
    body = response.json()
    assert body["game"]["id"] == str(game.id)
    assert body["lore_entries"][0]["embedding_configured"] is True
    assert body["summaries"][0]["content"].startswith("长期记忆")


def test_rebuild_game_summaries_from_history(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    db_session.add_all(
        [
            Turn(
                game_id=game.id,
                turn_number=1,
                player_input="我检查门槛。",
                gm_output="门槛内侧有新鲜泥痕。",
                visible_summary="门槛内侧有新鲜泥痕。",
                hidden_summary="泥痕来自后院。",
                state_delta_json={},
                action_options_json=[],
                model_used="deepseek-v4-pro-test",
            ),
            Turn(
                game_id=game.id,
                turn_number=2,
                player_input="我沿着泥痕去后院。",
                gm_output="后院墙根有黑伞留下的水痕。",
                visible_summary="后院墙根有黑伞水痕。",
                hidden_summary=None,
                state_delta_json={},
                action_options_json=[],
                model_used="deepseek-v4-pro-test",
            ),
        ]
    )
    db_session.commit()
    client = TestClient(app)

    response = client.post(f"/api/games/{game.id}/memory/summaries/rebuild")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 4
    summary_types = {
        summary.type
        for summary in db_session.scalars(
            select(Summary).where(Summary.game_id == game.id)
        ).all()
    }
    assert {"turn", "chapter", "long_term"}.issubset(summary_types)


def test_reindex_game_lore_embeddings(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    for entry in game.lore_entries:
        entry.embedding = None
        db_session.add(entry)
    db_session.commit()
    client = TestClient(app)

    response = client.post(f"/api/games/{game.id}/memory/lore/reindex")

    assert response.status_code == 200
    assert response.json() == {"total": 2, "updated": 2}
    memory_response = client.get(f"/api/games/{game.id}/memory")
    assert all(entry["embedding_configured"] for entry in memory_response.json()["lore_entries"])


def test_context_diagnostic_for_turn(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    turn = Turn(
        game_id=game.id,
        turn_number=1,
        player_input="我追问雨夜的黑伞客。",
        gm_output="守庄老仆提到雨夜曾有黑伞客靠近义庄。",
        visible_summary="雨夜黑伞客靠近义庄。",
        hidden_summary=None,
        state_delta_json={},
        action_options_json=[],
        model_used="deepseek-v4-pro-test",
    )
    db_session.add(turn)
    db_session.commit()
    client = TestClient(app)

    response = client.get(f"/api/games/{game.id}/context-diagnostic?turn_id={turn.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["turn_number"] == 1
    assert body["always_on_lore"][0]["title"] == "义庄"
    assert "黑伞客陆沉舟" in [entry["title"] for entry in body["related_lore"]]
