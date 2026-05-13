from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.config import settings
from app.main import app
from app.models.character import Character
from app.schemas.generator import (
    GeneratedCharacterProfile,
    GeneratedGameConfig,
    GeneratedLoreEntry,
    GeneratedMode,
)
from app.services.game_creator import create_game_from_config
from app.services.script_exporter import export_game_script_markdown


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
                dramatic_function="被旧案牵引的调查主角",
                desire="找回失去的记忆",
                fear="发现自己才是旧案凶手",
                leverage="对义庄铃声有生理反应",
                relationship_arc="从孤身追查到重新信任同伴",
                public_limit="不能提前公开旧案真凶",
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
    assert body[0]["aliases"] == []
    assert body[0]["portrait_prompt"] is None
    assert body[0]["story_profile"]["desire"] == "找回失去的记忆"
    assert body[1]["appearance"] == "黑伞、灰白长衫、眼神冷淡。"


def test_public_character_scope_hides_hidden_and_director_fields(db_session) -> None:
    game = create_game_from_config(db_session, build_character_config())
    hidden = Character(
        game_id=game.id,
        name="暗线证人",
        role="npc",
        visibility="hidden",
        is_visible=False,
        story_profile={"desire": "逃离雁回镇"},
        source="generated",
    )
    db_session.add(hidden)
    db_session.commit()
    client = TestClient(app)

    response = client.get(f"/api/games/{game.id}/characters?scope=public")

    assert response.status_code == 200
    body = response.json()
    assert [character["name"] for character in body] == ["沈砚", "陆沉舟"]
    assert body[0]["portrait_prompt"] is None
    assert body[0]["story_profile"]["desire"] == ""


def test_character_profiles_merge_lore_titles_with_display_names(db_session) -> None:
    config = build_character_config()
    config.lore_entries = [
        GeneratedLoreEntry(
            title="沈砚——失忆镖师",
            type="protagonist",
            public_info="义庄旧案的玩家角色。",
            content="义庄旧案的玩家角色。",
        ),
        GeneratedLoreEntry(
            title="陆沉舟——黑伞客",
            type="npc",
            public_info="常持黑伞的外乡人。",
            content="常持黑伞的外乡人。",
        ),
    ]
    game = create_game_from_config(db_session, config)
    client = TestClient(app)

    response = client.get(f"/api/games/{game.id}/characters")

    assert response.status_code == 200
    names = [character["name"] for character in response.json()]
    assert names == ["沈砚", "陆沉舟"]


def test_character_sync_merges_existing_duplicate_lore_cards(db_session) -> None:
    game = create_game_from_config(db_session, build_character_config())
    db_session.add(
        Character(
            game_id=game.id,
            name="沈砚——失忆镖师",
            role="protagonist",
            description="重复的世界资料角色卡。",
            source="lore",
        )
    )
    db_session.commit()
    client = TestClient(app)

    sync_response = client.post(f"/api/games/{game.id}/characters/sync")

    assert sync_response.status_code == 200
    body = sync_response.json()
    assert body["total"] == 2
    assert [character["name"] for character in body["characters"]] == ["沈砚", "陆沉舟"]


def test_character_sync_does_not_downgrade_existing_role(db_session) -> None:
    game = create_game_from_config(db_session, build_character_config())
    character = db_session.scalar(
        select(Character).where(Character.game_id == game.id, Character.name == "陆沉舟")
    )
    character.role = "companion"
    db_session.commit()
    client = TestClient(app)

    sync_response = client.post(f"/api/games/{game.id}/characters/sync")

    assert sync_response.status_code == 200
    body = sync_response.json()
    lu = next(character for character in body["characters"] if character["name"] == "陆沉舟")
    assert lu["role"] == "companion"


def test_character_sync_preserves_manual_fields_and_backfills_story_profile(db_session) -> None:
    game = create_game_from_config(db_session, build_character_config())
    character = db_session.scalar(
        select(Character).where(Character.game_id == game.id, Character.name == "沈砚")
    )
    character.description = "玩家手动改写的公开介绍。"
    character.manual_fields = ["description"]
    character.story_profile = {}
    character.sync_meta = {}
    db_session.commit()
    client = TestClient(app)

    sync_response = client.post(f"/api/games/{game.id}/characters/sync")

    assert sync_response.status_code == 200
    shen = next(
        character for character in sync_response.json()["characters"] if character["name"] == "沈砚"
    )
    assert shen["description"] == "玩家手动改写的公开介绍。"
    assert shen["story_profile"]["dramatic_function"] == "被旧案牵引的调查主角"


def test_character_update_rejects_visibility_conflict_and_keeps_old_name_alias(
    db_session,
) -> None:
    game = create_game_from_config(db_session, build_character_config())
    client = TestClient(app)
    character = client.get(f"/api/games/{game.id}/characters").json()[0]

    conflict_response = client.patch(
        f"/api/games/{game.id}/characters/{character['id']}",
        json={"visibility": "visible", "is_visible": False},
    )
    assert conflict_response.status_code == 400

    update_response = client.patch(
        f"/api/games/{game.id}/characters/{character['id']}",
        json={"name": "沈砚之", "aliases": ["沈镖师"]},
    )

    assert update_response.status_code == 200
    body = update_response.json()
    assert body["name"] == "沈砚之"
    assert body["aliases"] == ["沈砚", "沈镖师"]


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

    png_bytes = make_png_bytes()
    upload_response = client.post(
        f"/api/games/{game.id}/characters/{character['id']}/portrait",
        files={"file": ("shen.png", png_bytes, "image/png")},
    )
    assert upload_response.status_code == 200
    portrait_url = upload_response.json()["portrait_url"]
    thumb_url = upload_response.json()["portrait_thumb_url"]
    assert portrait_url
    assert thumb_url

    file_response = client.get(portrait_url)
    assert file_response.status_code == 200
    assert file_response.headers["content-type"] == "image/png"
    assert file_response.content == png_bytes
    thumb_response = client.get(thumb_url)
    assert thumb_response.status_code == 200
    assert thumb_response.headers["content-type"] == "image/webp"

    sync_response = client.post(f"/api/games/{game.id}/characters/sync")
    assert sync_response.status_code == 200
    assert sync_response.json()["total"] == 2

    delete_response = client.delete(
        f"/api/games/{game.id}/characters/{character['id']}/portrait"
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["portrait_url"] is None
    assert delete_response.json()["portrait_thumb_url"] is None


def test_portrait_upload_rejects_fake_image_content(db_session, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "portrait_storage_path", str(tmp_path))
    game = create_game_from_config(db_session, build_character_config())
    client = TestClient(app)
    character = client.get(f"/api/games/{game.id}/characters").json()[0]

    response = client.post(
        f"/api/games/{game.id}/characters/{character['id']}/portrait",
        files={"file": ("fake.png", b"not a real image", "image/png")},
    )

    assert response.status_code == 400


def test_script_export_includes_character_story_profile(db_session) -> None:
    game = create_game_from_config(db_session, build_character_config())

    markdown = export_game_script_markdown(game)

    assert "## 角色档案" in markdown
    assert "戏剧功能：被旧案牵引的调查主角" in markdown
    assert "欲望：找回失去的记忆" in markdown


def make_png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), color=(120, 40, 30)).save(output, format="PNG")
    return output.getvalue()
