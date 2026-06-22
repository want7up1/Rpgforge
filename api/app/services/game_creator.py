from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.models.character import Character
from app.models.game import Game, GameConfig
from app.models.state import GameState
from app.schemas.generator import GeneratedGameConfig
from app.services.state_v2 import normalize_state_v2
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
            "body": "正常",
            "mind": "平静",
            "weaknesses": [],
        },
        # 纯叙事化：不再有等级/经验/危机条/压力时钟/技能/能力等数值结构。
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


def _extract_story_settings(payload: Any) -> Any:
    """从粘贴的 JSON 里解出 story_settings 本体。

    兼容三种形态：① 裸 story_settings 对象；② settings-export 包裹体
    （含 story_settings 键）；③ 前端再包一层。靠 format_version/game_profile
    标记判定是否已到本体，最多向下钻 3 层防御无限递归。
    """
    current = payload
    for _ in range(3):
        if not isinstance(current, dict):
            break
        if current.get("format_version") or current.get("game_profile"):
            return current
        nested = current.get("story_settings")
        if isinstance(nested, dict):
            current = nested
            continue
        break
    return current


def _story_has_content(story: dict[str, Any]) -> bool:
    """判断归一化后的剧本是否含真实剧情设定。

    normalize 会把任意输入纠成合法空壳（title 缺省「未命名游戏」、format_version 纠回），
    所以仅靠 validate 挡不住垃圾粘贴。只要标题/世界观/角色/幕/故事核心任一非空即视为有内容。
    """
    profile = story.get("game_profile") or {}
    title = str(profile.get("title") or "").strip()
    if title not in ("", "未命名游戏"):
        return True
    worldview = story.get("worldview")
    if isinstance(worldview, dict) and any(worldview.values()):
        return True
    if story.get("core_characters") or story.get("act_plan"):
        return True
    core = story.get("story_core") or {}
    return bool(
        str(core.get("premise") or "").strip()
        or str(core.get("main_goal") or "").strip()
        or str(core.get("central_mystery") or "").strip()
    )


def build_imported_game_config(payload: Any) -> GeneratedGameConfig:
    """把外部 AI 写的 story_settings JSON 校验+归一化成 GeneratedGameConfig。

    校验失败（角色重名、幕 id 重复、内容为空等）抛 ValueError，由路由层转成 400。
    不建游戏、不落库——预览满意后再走 create_game_from_config。
    """
    raw = _extract_story_settings(payload)
    story_settings = validate_story_settings(raw)
    if not _story_has_content(story_settings):
        raise ValueError(
            "剧本内容为空或格式不正确：未识别到任何剧情设定"
            "（标题、世界观、角色、幕、故事核心都为空）。"
            "请确认粘贴的是完整的 story_settings JSON。"
        )
    profile = game_profile(story_settings)
    return GeneratedGameConfig(
        title=profile["title"],
        genre=profile["genre"] or None,
        description=profile["description"] or None,
        story_settings=story_settings,
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
    # 纯叙事化：不再种六维属性，主角只补名字/身份等文字字段。
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
