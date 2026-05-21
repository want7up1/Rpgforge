from sqlalchemy import select

from app.models.character import Character
from app.services.characters import (
    build_character_records_from_config,
    extract_profiles_from_config,
    sync_characters_from_game,
)
from app.services.game_creator import create_game_from_config
from tests.story_settings_fixtures import build_generated_config, copied_story_settings


def test_extract_profiles_from_story_settings_core_characters() -> None:
    config = build_generated_config()

    profiles = extract_profiles_from_config(config)

    assert [profile.name for profile in profiles] == ["沈砚", "陆沉舟"]
    protagonist = profiles[0]
    assert protagonist.role == "protagonist"
    assert protagonist.appearance == "旧青色短打，右手缠着褪色布带。"
    assert protagonist.story_profile["desire"] == "找回失去的记忆"


def test_build_character_records_from_config_uses_story_settings_source() -> None:
    records = build_character_records_from_config(build_generated_config())

    assert [record.name for record in records] == ["沈砚", "陆沉舟"]
    assert records[0].source == "story_settings"
    assert records[0].sync_meta["appearance"] == "旧青色短打，右手缠着褪色布带。"
    assert records[0].manual_fields == []


def test_create_game_syncs_characters_from_story_settings(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())

    characters = list(
        db_session.scalars(
            select(Character).where(Character.game_id == game.id).order_by(Character.name.asc())
        )
    )

    assert [character.name for character in characters] == ["沈砚", "陆沉舟"]
    assert characters[0].source == "story_settings"
    assert characters[0].portrait_prompt is None


def test_sync_characters_preserves_manual_fields(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    shen_yan = db_session.scalars(
        select(Character).where(Character.game_id == game.id, Character.name == "沈砚")
    ).one()
    shen_yan.description = "用户手动改写的主角简介。"
    shen_yan.manual_fields = ["description"]
    db_session.add(shen_yan)
    db_session.commit()

    updated = copied_story_settings()
    updated["core_characters"][0]["description"] = "AI 新生成的主角简介。"
    updated["core_characters"][0]["appearance"] = "换成黑色短打。"
    game.config.story_settings = updated
    db_session.add(game.config)
    db_session.commit()

    created, updated_count, characters = sync_characters_from_game(db_session, game)

    assert created == 0
    assert updated_count >= 2
    refreshed = next(character for character in characters if character.name == "沈砚")
    assert refreshed.description == "用户手动改写的主角简介。"
    assert refreshed.appearance
    assert refreshed.manual_fields == ["description"]
