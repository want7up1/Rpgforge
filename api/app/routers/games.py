import json
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db.session import get_db
from app.models.character import Character
from app.models.game import Game, GameConfig
from app.models.generator_job import GeneratorChatJob, GeneratorFinalizeJob, TurnJob
from app.models.setting_version import GameSettingVersion
from app.models.turn import Turn
from app.schemas.game import (
    ContextDiagnosticRead,
    GameConfigUpdate,
    GameCreate,
    GameDetail,
    GameListItem,
    GameMemoryRead,
    GameSettingVersionRead,
    SuggestItemRequest,
    SuggestItemResponse,
    SummaryRead,
    SummaryRebuildResponse,
)
from app.services.context_compressor import ContextCompressor
from app.services.context_diagnostics import ContextDiagnosticService
from app.services.game_activity import touch_game
from app.services.game_creator import build_manual_generated_config, create_game_from_config
from app.services.item_suggester import ItemSuggester
from app.services.script_exporter import export_game_script_markdown, script_export_filename
from app.services.settings_guide_exporter import (
    export_settings_guide_markdown,
    settings_guide_export_filename,
)
from app.services.state_delta_auto_apply import apply_pending_state_deltas
from app.services.story_settings import (
    STORY_SETTINGS_FORMAT_VERSION,
    game_profile,
    validate_story_settings,
)

router = APIRouter(prefix="/api/games", tags=["games"])
DB_DEPENDENCY = Depends(get_db)
SETTINGS_EXPORT_FORMAT_VERSION = STORY_SETTINGS_FORMAT_VERSION
ACCEPTED_SETTINGS_FORMAT_VERSIONS = {
    SETTINGS_EXPORT_FORMAT_VERSION,
}
CHARACTER_ROLES = {"protagonist", "npc", "companion", "other"}
CHARACTER_VISIBILITIES = {"visible", "hidden"}


def game_detail_query(game_id: UUID, *, include_turns: bool = False):
    options = [
        selectinload(Game.config),
        selectinload(Game.state),
        selectinload(Game.summaries),
    ]
    if include_turns:
        options.append(selectinload(Game.turns))
    return (
        select(Game)
        .options(*options)
        .where(Game.id == game_id)
    )


def get_game_or_404(db: Session, game_id: UUID, *, include_turns: bool = False) -> Game:
    game = db.scalars(game_detail_query(game_id, include_turns=include_turns)).first()
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found.")
    return game


def game_detail_response(game: Game) -> GameDetail:
    return GameDetail(
        id=game.id,
        title=game.title,
        genre=game.genre,
        description=game.description,
        status=game.status,
        created_at=game.created_at,
        updated_at=game.updated_at,
        config=game.config,
        state=game.state,
        summaries=list(game.summaries),
        turns=[],
    )


@router.get("", response_model=list[GameListItem])
def list_games(db: Session = DB_DEPENDENCY) -> list[Game]:
    return list(db.scalars(select(Game).order_by(Game.updated_at.desc())).all())


@router.post("", response_model=GameDetail, status_code=status.HTTP_201_CREATED)
def create_game(payload: GameCreate, db: Session = DB_DEPENDENCY) -> GameDetail:
    config = build_manual_generated_config(payload.title, payload.genre, payload.description)
    game = create_game_from_config(db, config)
    return game_detail_response(get_game_or_404(db, game.id))


@router.get("/{game_id}", response_model=GameDetail)
def get_game(game_id: UUID, db: Session = DB_DEPENDENCY) -> GameDetail:
    game = get_game_or_404(db, game_id)
    if apply_pending_state_deltas(db, game):
        game = get_game_or_404(db, game_id)
    return game_detail_response(game)


@router.get("/{game_id}/script-export")
def export_game_script(game_id: UUID, db: Session = DB_DEPENDENCY) -> Response:
    game = db.scalars(
        select(Game)
        .options(
            selectinload(Game.config),
            selectinload(Game.characters),
        )
        .where(Game.id == game_id)
    ).first()
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found.")

    content = export_game_script_markdown(game)
    filename = script_export_filename(game.title)
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.get("/{game_id}/settings-export")
def export_game_settings(game_id: UUID, db: Session = DB_DEPENDENCY) -> Response:
    game = _get_game_for_settings_transfer(db, game_id)
    filename = _settings_export_filename(game.title)
    return Response(
        content=json.dumps(_settings_export_payload(game), ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.get("/{game_id}/settings-guide-export")
def export_game_settings_guide(game_id: UUID, db: Session = DB_DEPENDENCY) -> Response:
    game = _get_game_for_settings_transfer(db, game_id)
    filename = settings_guide_export_filename(game.title)
    return Response(
        content=export_settings_guide_markdown(),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.post("/{game_id}/settings-import", response_model=GameDetail)
def import_game_settings(
    game_id: UUID,
    payload: dict[str, Any],
    db: Session = DB_DEPENDENCY,
) -> GameDetail:
    game = _get_game_for_settings_transfer(db, game_id)
    _assert_settings_editable(db, game_id)
    _apply_settings_import(db, game, payload)
    touch_game(db, game_id)
    db.add(game)
    db.flush()
    _save_setting_version(
        db,
        game_id,
        "config",
        None,
        "imported",
        _settings_export_payload(game, include_guides=False),
    )
    db.commit()
    return game_detail_response(get_game_or_404(db, game_id))


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_game(game_id: UUID, db: Session = DB_DEPENDENCY) -> None:
    game = get_game_or_404(db, game_id)
    active_job = db.scalars(
        select(TurnJob)
        .where(TurnJob.game_id == game_id, TurnJob.status.in_(("pending", "running")))
        .limit(1)
    ).first()
    if active_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="游戏正在生成回合，请等待任务完成后再删除。",
        )

    remove_game_portrait_files(db, game_id)
    db.delete(game)
    db.commit()
    return None


@router.patch("/{game_id}/config", response_model=GameDetail)
def update_game_config(
    game_id: UUID,
    payload: GameConfigUpdate,
    db: Session = DB_DEPENDENCY,
) -> GameDetail:
    game = get_game_or_404(db, game_id)
    _assert_settings_editable(db, game_id)
    if game.config is None:
        game.config = GameConfig(story_settings={})
        db.add(game.config)
        db.flush()

    _ensure_baseline_version(db, game, "config", None, _config_snapshot(game))
    updates = payload.model_dump(exclude_unset=True)
    settings_payload = updates.get("story_settings_json")
    if settings_payload is None:
        settings_payload = updates.get("story_settings")
    if settings_payload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="必须提供 story_settings。",
        )
    story_settings = _validated_story_settings(settings_payload)
    game.config.story_settings = story_settings
    _sync_game_profile_from_story_settings(game, story_settings)

    touch_game(db, game_id)
    db.add(game)
    db.flush()
    _save_setting_version(db, game_id, "config", None, "updated", _config_snapshot(game))
    db.commit()
    return game_detail_response(get_game_or_404(db, game_id))


@router.get("/{game_id}/setting-versions", response_model=list[GameSettingVersionRead])
def list_game_setting_versions(
    game_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> list[GameSettingVersion]:
    get_game_or_404(db, game_id)
    return list(
        db.scalars(
            select(GameSettingVersion)
            .where(GameSettingVersion.game_id == game_id)
            .order_by(GameSettingVersion.created_at.desc())
        ).all()
    )


@router.post(
    "/{game_id}/setting-versions/{version_id}/restore",
    response_model=GameDetail,
)
def restore_game_setting_version(
    game_id: UUID,
    version_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> GameDetail:
    game = get_game_or_404(db, game_id)
    _assert_settings_editable(db, game_id)
    version = db.scalars(
        select(GameSettingVersion).where(
            GameSettingVersion.id == version_id,
            GameSettingVersion.game_id == game_id,
        )
    ).first()
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Version not found.",
        )

    if version.scope != "config":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported version scope.",
        )
    _ensure_baseline_version(db, game, "config", None, _config_snapshot(game))
    _restore_config_snapshot(game, version.snapshot_json)
    db.add(game)
    db.flush()
    _save_setting_version(db, game_id, "config", None, "restored", _config_snapshot(game))

    touch_game(db, game_id)
    db.commit()
    return game_detail_response(get_game_or_404(db, game_id))


@router.get("/{game_id}/memory", response_model=GameMemoryRead)
def get_game_memory(game_id: UUID, db: Session = DB_DEPENDENCY) -> dict:
    game = get_game_or_404(db, game_id)
    if apply_pending_state_deltas(db, game):
        game = get_game_or_404(db, game_id)
    turn_count = db.scalar(select(func.count(Turn.id)).where(Turn.game_id == game_id)) or 0
    return {
        "game": GameListItem.model_validate(game),
        "current_turn": game.state.current_turn if game.state else 0,
        "turn_count": turn_count,
        "summaries": [SummaryRead.model_validate(summary) for summary in game.summaries],
    }


@router.get("/{game_id}/context-diagnostic", response_model=ContextDiagnosticRead | None)
def get_context_diagnostic(
    game_id: UUID,
    turn_id: UUID | None = None,
    db: Session = DB_DEPENDENCY,
) -> ContextDiagnosticRead | None:
    game = get_game_or_404(db, game_id)
    return ContextDiagnosticService().build_for_turn(db, game, turn_id)


@router.post("/{game_id}/memory/summaries/rebuild", response_model=SummaryRebuildResponse)
def rebuild_game_summaries(
    game_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> SummaryRebuildResponse:
    game = get_game_or_404(db, game_id)
    summaries = ContextCompressor().rebuild_from_history(db, game)
    touch_game(db, game_id)
    db.commit()
    return SummaryRebuildResponse(
        total=len(summaries),
        summaries=[SummaryRead.model_validate(summary) for summary in summaries],
    )


def _get_game_for_settings_transfer(db: Session, game_id: UUID) -> Game:
    game = db.scalars(
        select(Game)
        .options(
            selectinload(Game.config),
            selectinload(Game.characters),
        )
        .where(Game.id == game_id)
    ).first()
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found.")
    return game


def _settings_export_filename(title: str) -> str:
    safe_title = "".join(
        character if character.isalnum() or character in ("-", "_") else "-"
        for character in title.strip()
    ).strip("-")
    return f"RPGForge-{safe_title or 'settings'}-settings.json"


def _settings_export_payload(game: Game, *, include_guides: bool = True) -> dict[str, Any]:
    if game.config is None:
        return _validated_story_settings({})
    return _validated_story_settings(game.config.story_settings)


def _apply_settings_import(db: Session, game: Game, payload: dict[str, Any]) -> None:
    format_version = payload.get("format_version")
    if format_version not in ACCEPTED_SETTINGS_FORMAT_VERSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="settings JSON format_version 不受支持。",
        )

    if game.config is None:
        game.config = GameConfig(story_settings={})
        db.add(game.config)
        db.flush()

    story_settings = _validated_story_settings(payload)
    new_characters = _characters_from_story_settings(game, story_settings)
    _ensure_baseline_version(db, game, "config", None, _config_snapshot(game))
    _clear_import_replaced_characters(db, game)
    game.config.story_settings = story_settings
    _sync_game_profile_from_story_settings(game, story_settings)
    game.characters = new_characters


def _clear_import_replaced_characters(db: Session, game: Game) -> None:
    remove_game_portrait_files(db, game.id)
    for character in list(game.characters):
        db.delete(character)
    game.characters = []
    db.flush()


def _validated_story_settings(value: Any) -> dict[str, Any]:
    try:
        return validate_story_settings(_json_object(value, "story_settings"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


def _sync_game_profile_from_story_settings(game: Game, story_settings: dict[str, Any]) -> None:
    profile = game_profile(story_settings)
    game.title = _clean_required(profile["title"], "story_settings.game_profile.title 不能为空。")
    game.genre = _clean_optional(profile["genre"])
    game.description = _clean_optional(profile["description"])


def _characters_from_story_settings(game: Game, story_settings: dict[str, Any]) -> list[Character]:
    characters: list[Character] = []
    for item in story_settings.get("core_characters") or []:
        if not isinstance(item, dict):
            continue
        name = _clean_required(item.get("name"), "core_characters[].name 不能为空。")
        role = _clean_optional(item.get("role")) or "npc"
        if role not in CHARACTER_ROLES:
            role = "npc"
        visibility = _clean_optional(item.get("visibility")) or "visible"
        if visibility not in CHARACTER_VISIBILITIES:
            visibility = "visible"
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
        characters.append(
            Character(
                game_id=game.id,
                name=name,
                aliases=_clean_list(list(item.get("aliases") or [])),
                role=role,
                identity=_clean_optional(item.get("identity")),
                description=_clean_optional(item.get("description")),
                appearance=_clean_optional(item.get("appearance")),
                story_profile=story_profile,
                portrait_prompt=_clean_optional(item.get("portrait_prompt")),
                visibility=visibility,
                is_visible=visibility == "visible",
                source="story_settings",
                sync_meta={"source": STORY_SETTINGS_FORMAT_VERSION},
                manual_fields=[],
            )
        )
    return characters


def _assert_settings_editable(db: Session, game_id: UUID) -> None:
    active_turn_job = db.scalars(
        select(TurnJob)
        .where(
            TurnJob.game_id == game_id,
            (
                TurnJob.status.in_(("pending", "running"))
                | (
                    (TurnJob.status == "completed")
                    & TurnJob.maintenance_status.in_(("pending", "running"))
                    & (TurnJob.maintenance_stage == "state_extract")
                )
            ),
        )
        .limit(1)
    ).first()
    if active_turn_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前游戏仍有生成或状态提取任务运行中，请完成后再编辑设定。",
        )

    active_generator_job = (
        db.scalars(
            select(GeneratorChatJob)
            .where(GeneratorChatJob.status.in_(("pending", "running")))
            .limit(1)
        ).first()
        or db.scalars(
            select(GeneratorFinalizeJob)
            .where(GeneratorFinalizeJob.status.in_(("pending", "running")))
            .limit(1)
        ).first()
    )
    if active_generator_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前仍有冒险创建任务运行中，请完成后再编辑设定。",
        )


def _config_snapshot(game: Game) -> dict:
    config = game.config
    return {
        "story_settings": _validated_story_settings(config.story_settings if config else {}),
    }


def _ensure_baseline_version(
    db: Session,
    game: Game | None,
    scope: str,
    entity_id: UUID | None,
    snapshot: dict,
    *,
    game_id: UUID | None = None,
) -> None:
    resolved_game_id = game_id or (game.id if game else None)
    if resolved_game_id is None:
        raise RuntimeError("game_id is required for setting version baseline.")
    query = select(GameSettingVersion).where(
        GameSettingVersion.game_id == resolved_game_id,
        GameSettingVersion.scope == scope,
    )
    if entity_id is None:
        query = query.where(GameSettingVersion.entity_id.is_(None))
    else:
        query = query.where(GameSettingVersion.entity_id == entity_id)
    exists = db.scalars(query.limit(1)).first()
    if exists is None:
        _save_setting_version(db, resolved_game_id, scope, entity_id, "baseline", snapshot)


def _save_setting_version(
    db: Session,
    game_id: UUID,
    scope: str,
    entity_id: UUID | None,
    action: str,
    snapshot: dict,
) -> None:
    db.add(
        GameSettingVersion(
            game_id=game_id,
            scope=scope,
            entity_id=entity_id,
            action=action,
            snapshot_json=snapshot,
        )
    )


def _json_object(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} 必须是 JSON 对象。",
        )
    return dict(value)


def _clean_required(value: object, message: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return text


def _clean_optional(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_list(values: list[object]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def _restore_config_snapshot(game: Game, snapshot: dict) -> None:
    if game.config is None:
        game.config = GameConfig(story_settings={})
    story_settings = _validated_story_settings(snapshot.get("story_settings") or snapshot)
    game.config.story_settings = story_settings
    _sync_game_profile_from_story_settings(game, story_settings)


def remove_game_portrait_files(db: Session, game_id: UUID) -> None:
    root = Path(settings.portrait_storage_path).resolve()
    characters = db.scalars(select(Character).where(Character.game_id == game_id)).all()
    for character in characters:
        if not character.portrait_path:
            continue
        portrait_path = Path(character.portrait_path)
        try:
            resolved = portrait_path.resolve()
        except OSError:
            continue
        if not resolved.is_relative_to(root):
            continue
        if resolved.exists() and resolved.is_file():
            resolved.unlink()

    game_dir = root / str(game_id)
    if game_dir.exists() and game_dir.is_dir():
        shutil.rmtree(game_dir)


@router.post("/{game_id}/settings/suggest-item", response_model=SuggestItemResponse)
async def suggest_settings_item(
    game_id: UUID,
    payload: SuggestItemRequest,
    db: Session = DB_DEPENDENCY,
) -> SuggestItemResponse:
    game = get_game_or_404(db, game_id)
    story_settings = game.config.story_settings if game.config else {}
    fields = await ItemSuggester().suggest(payload.array_key, payload.draft, story_settings)
    return SuggestItemResponse(fields=fields)
