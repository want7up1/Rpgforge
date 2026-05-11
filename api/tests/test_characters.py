from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.schemas.generator import GeneratedCharacterProfile, GeneratedGameConfig, GeneratedMode
from app.services.game_creator import create_game_from_config


def build_character_config() -> GeneratedGameConfig:
    return GeneratedGameConfig(
        title="雁回镇旧案",
        genre="黑暗武侠",
        description="失忆镖师追查义庄旧案。",
        system_prompt="你是 GM，每回合生成剧情和 A/B/C/D 行动选项。",
        worldview={"tone": "冷峻"},
        script_outline={"title": "雁回镇旧案", "acts": []},
        generation_notes="test",
        characters=[
            GeneratedCharacterProfile(
                name="沈砚",
                aliases=["失忆镖师"],
                role="protagonist",
                identity="失忆镖师",
                description="刚抵达雁回镇的玩家角色。",
                appearance="旧青色短打，右手缠着褪色布带。",
                portrait_prompt="黑暗武侠，失忆镖师，旧青色短打，褪色布带。",
            )
        ],
        modes=[
            GeneratedMode(
                name="调查模式",
                triggers=["调查"],
                injection="不要直接给出真相，提供可验证线索。",
                priority="medium",
                enabled=True,
            )
        ],
        initial_state={
            "current_turn": 0,
            "time": {"current": "秋末，申时"},
            "location": {"current": "雁回镇义庄"},
            "protagonist": {
                "name": "沈砚",
                "identity": "失忆镖师",
                "appearance": "旧青色短打，右手缠着褪色布带。",
            },
            "npcs": [
                {
                    "name": "陆沉舟",
                    "identity": "常持黑伞的外乡人",
                    "description": "曾在雨夜靠近义庄。",
                    "appearance": "黑伞、灰白长衫、眼神冷淡。",
                    "portrait_prompt": "黑暗武侠，黑伞客，灰白长衫。",
                }
            ],
            "inventory": [],
            "quests": [],
            "factions": [],
            "variables": {},
            "known_facts": [],
            "hidden_facts": [],
            "open_threads": [],
        },
    )


def test_generated_game_creates_character_profiles(db_session) -> None:
    game = create_game_from_config(db_session, build_character_config())
    client = TestClient(app)

    response = client.get(f"/api/games/{game.id}/characters")

    assert response.status_code == 200
    body = response.json()
    assert [character["name"] for character in body] == ["沈砚", "陆沉舟"]
    assert body[0]["role"] == "protagonist"
    assert body[0]["portrait_prompt"]
    assert body[1]["appearance"] == "黑伞、灰白长衫、眼神冷淡。"


def test_update_sync_and_portrait_upload(db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "portrait_storage_path", str(tmp_path))
    game = create_game_from_config(db_session, build_character_config())
    client = TestClient(app)
    character = client.get(f"/api/games/{game.id}/characters").json()[0]

    update_response = client.patch(
        f"/api/games/{game.id}/characters/{character['id']}",
        json={"aliases": ["沈镖师"], "description": "玩家可见主角档案。"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["aliases"] == ["沈镖师"]

    png_bytes = b"\x89PNG\r\n\x1a\nrpgforge"
    upload_response = client.post(
        f"/api/games/{game.id}/characters/{character['id']}/portrait",
        files={"file": ("shen.png", png_bytes, "image/png")},
    )
    assert upload_response.status_code == 200
    portrait_url = upload_response.json()["portrait_url"]
    assert portrait_url

    file_response = client.get(portrait_url)
    assert file_response.status_code == 200
    assert file_response.headers["content-type"] == "image/png"
    assert file_response.content == png_bytes

    sync_response = client.post(f"/api/games/{game.id}/characters/sync")
    assert sync_response.status_code == 200
    assert sync_response.json()["total"] == 2

    delete_response = client.delete(
        f"/api/games/{game.id}/characters/{character['id']}/portrait"
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["portrait_url"] is None
