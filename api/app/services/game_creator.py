from typing import Any

from sqlalchemy.orm import Session

from app.models.game import Game, GameConfig
from app.models.lore import LoreEntry
from app.models.mode import Mode
from app.models.state import GameState
from app.schemas.generator import GeneratedGameConfig
from app.services.characters import build_character_records_from_config
from app.services.state_v2 import normalize_state_v2
from app.services.text_vectorizer import text_to_vector


def build_default_initial_state(title: str, description: str | None = None) -> dict[str, Any]:
    return {
        "current_turn": 0,
        "time": {"current": "未开始", "pressure": ""},
        "location": {"current": "未定", "known_locations": []},
        "protagonist": {
            "name": "未定",
            "identity": "未定",
            "attributes": {},
            "body": "正常",
            "mind": "平静",
            "weaknesses": [],
        },
        "progression": {
            "level": 1,
            "xp": 0,
            "next_level_xp": 100,
            "total_xp": 0,
            "xp_log": [],
        },
        "skills": [],
        "abilities": [],
        "conditions": [],
        "relationships": [],
        "inventory": [],
        "quests": [],
        "npcs": [],
        "factions": [],
        "variables": {"source_title": title, "source_description": description or ""},
        "known_facts": [],
        "hidden_facts": [],
        "open_threads": [],
    }


def build_manual_generated_config(
    title: str,
    genre: str | None,
    description: str | None,
) -> GeneratedGameConfig:
    return GeneratedGameConfig(
        title=title,
        genre=genre,
        description=description,
        system_prompt=(
            "你是 RPGForge 的 GM。当前游戏仍处于手动创建草稿状态，"
            "正式规则、世界书和模式注入将在规则生成器完成后补齐。"
        ),
        worldview={"title": title, "description": description or "", "genre": genre or ""},
        script_outline={"title": title, "acts": []},
        generation_notes="Manual Phase 1 creation without generator output.",
        lore_entries=[],
        modes=[],
        initial_state=build_default_initial_state(title, description),
    )


def create_game_from_config(db: Session, config: GeneratedGameConfig) -> Game:
    script_outline = dict(config.script_outline)
    if config.characters and "_character_profiles" not in script_outline:
        script_outline["_character_profiles"] = [
            profile.model_dump(mode="json") for profile in config.characters
        ]
    game = Game(
        title=config.title,
        genre=config.genre,
        description=config.description,
        status="active",
    )
    game.config = GameConfig(
        system_prompt=config.system_prompt,
        worldview=config.worldview,
        script_outline=script_outline,
        generation_notes=config.generation_notes,
    )
    game.state = GameState(
        current_turn=int(config.initial_state.get("current_turn", 0)),
        state_json=normalize_state_v2(
            config.initial_state or build_default_initial_state(config.title, config.description),
            int(config.initial_state.get("current_turn", 0)),
        ),
        summary="",
    )
    game.lore_entries = [
        LoreEntry(
            title=entry.title,
            type=entry.type,
            keywords=entry.keywords,
            trigger_words=entry.trigger_words,
            priority=entry.priority,
            always_on=entry.always_on,
            visibility=entry.visibility,
            public_info=entry.public_info,
            gm_secret=entry.gm_secret,
            content=entry.content,
            usage_note=entry.usage_note,
            embedding=text_to_vector(
                "\n".join(
                    [
                        entry.title,
                        entry.type or "",
                        " ".join(entry.keywords),
                        " ".join(entry.trigger_words),
                        entry.public_info,
                        entry.gm_secret,
                        entry.content,
                        entry.usage_note,
                    ]
                )
            ),
        )
        for entry in config.lore_entries
    ]
    game.modes = [
        Mode(
            name=mode.name,
            triggers=mode.triggers,
            injection=mode.injection,
            priority=mode.priority,
            enabled=mode.enabled,
        )
        for mode in config.modes
    ]
    game.characters = build_character_records_from_config(config)

    db.add(game)
    db.commit()
    db.refresh(game)
    return game
