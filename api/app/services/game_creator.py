from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.models.character import Character
from app.models.game import Game, GameConfig
from app.models.state import GameState
from app.schemas.generator import GeneratedGameConfig
from app.services.state_v2 import DEFAULT_PROTAGONIST_ATTRIBUTES, normalize_state_v2
from app.services.story_settings import (
    default_story_settings,
    game_profile,
    initial_story_progress,
    validate_story_settings,
)


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
        # A3 危机条 + B3 压力时钟（survival_clock 每回合推进）。
        "crisis": {"value": 100, "max": 100},
        "pressure_clock": {"value": 0, "threshold": 10, "triggers": 0},
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
        "story_progress": {
            "current_act": "",
            "completed_acts": [],
            "last_advance_turn": None,
            "last_advance_reason": "",
            "act_history": [],
        },
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
        story_settings=default_story_settings(title, genre, description),
        initial_state=build_default_initial_state(title, description),
    )


def create_game_from_config(db: Session, config: GeneratedGameConfig) -> Game:
    story_settings = validate_story_settings(config.story_settings)
    profile = game_profile(story_settings)
    game = Game(
        title=config.title or profile["title"],
        genre=config.genre or profile["genre"],
        description=config.description or profile["description"],
        status="active",
    )
    game.config = GameConfig(story_settings=story_settings)
    initial_state = (
        deepcopy(config.initial_state)
        if config.initial_state
        else build_default_initial_state(
            config.title,
            config.description,
        )
    )
    story_progress = initial_state.get("story_progress")
    if not isinstance(story_progress, dict) or not story_progress.get("current_act"):
        initial_state["story_progress"] = initial_story_progress(game.config)
    _sync_source_variables(initial_state, game.title, game.description)
    _fill_protagonist_from_story_settings(initial_state, story_settings)
    initial_turn = int(initial_state.get("current_turn", 0))
    normalized_initial_state = normalize_state_v2(initial_state, initial_turn)
    game.state = GameState(
        current_turn=initial_turn,
        state_json=normalized_initial_state,
        initial_state_json=normalized_initial_state,
        summary="",
    )
    game.characters = [
        _character_from_story_settings(item)
        for item in story_settings["core_characters"]
    ]

    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def _fill_protagonist_from_story_settings(
    initial_state: dict[str, Any],
    story_settings: dict[str, Any],
) -> None:
    protagonist = initial_state.setdefault("protagonist", {})
    if not isinstance(protagonist, dict):
        protagonist = {}
        initial_state["protagonist"] = protagonist
    # 属性兜底（总执行，在下方 configured 早返回之前）：AI 未生成或手动建档时填中性默认六维，
    # 让角色 build / 行动判定从开局就有依托，而不是空属性→判定纯靠运气。
    existing_attrs = protagonist.get("attributes")
    if not isinstance(existing_attrs, dict) or not existing_attrs:
        protagonist["attributes"] = dict(DEFAULT_PROTAGONIST_ATTRIBUTES)
    configured = next(
        (
            character
            for character in story_settings.get("core_characters") or []
            if isinstance(character, dict)
            and str(character.get("role") or "").lower()
            in {"protagonist", "主角", "pc", "player"}
        ),
        None,
    )
    if not isinstance(configured, dict):
        return
    for key in ("name", "identity", "appearance"):
        incoming = str(configured.get(key) or "").strip()
        current = str(protagonist.get(key) or "").strip()
        if incoming and current in {"", "未定", "未知", "无名", "待定"}:
            protagonist[key] = incoming


def _sync_source_variables(
    initial_state: dict[str, Any],
    title: str,
    description: str | None,
) -> None:
    variables = initial_state.setdefault("variables", {})
    if not isinstance(variables, dict):
        variables = {}
        initial_state["variables"] = variables
    variables["source_title"] = title
    variables["source_description"] = description or ""


def _character_from_story_settings(item: dict[str, Any]) -> Character:
    story_profile = {
        key: str(item.get(key) or "")
        for key in (
            "dramatic_function",
            "desire",
            "fear",
            "leverage",
            "relationship_arc",
            "public_limit",
        )
    }
    visibility = str(item.get("visibility") or "visible")
    return Character(
        name=str(item.get("name") or "未命名角色"),
        aliases=[str(alias) for alias in item.get("aliases") or []],
        role=str(item.get("role") or "npc"),
        identity=str(item.get("identity") or "") or None,
        description=str(item.get("description") or "") or None,
        appearance=str(item.get("appearance") or "") or None,
        story_profile=story_profile,
        portrait_prompt=str(item.get("portrait_prompt") or "") or None,
        visibility=visibility,
        is_visible=visibility == "visible",
        source="story_settings",
        sync_meta={"source": "story_settings.v2"},
        manual_fields=[],
    )
