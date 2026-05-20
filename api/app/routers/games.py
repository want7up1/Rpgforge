import json
import shutil
from datetime import UTC, datetime
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
from app.models.lore import LoreEntry
from app.models.mode import Mode
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
    LoreEntryCreate,
    LoreEntryMemoryRead,
    LoreEntryRead,
    LoreEntryUpdate,
    LoreReindexResponse,
    ModeCreate,
    ModeRead,
    ModeUpdate,
    SummaryRead,
    SummaryRebuildResponse,
)
from app.services.context_compressor import ContextCompressor
from app.services.context_diagnostics import ContextDiagnosticService
from app.services.game_activity import touch_game
from app.services.game_creator import build_manual_generated_config, create_game_from_config
from app.services.generation_settings import normalize_generation_settings
from app.services.lore_retriever import LoreRetriever
from app.services.script_exporter import export_game_script_markdown, script_export_filename
from app.services.settings_export_guide import (
    settings_export_ai_editing_guide,
    settings_export_field_guide,
)
from app.services.state_delta_auto_apply import apply_pending_state_deltas
from app.services.story_blueprint import merge_required_script_fields, protect_user_brief_contract
from app.services.text_vectorizer import text_to_vector

router = APIRouter(prefix="/api/games", tags=["games"])
DB_DEPENDENCY = Depends(get_db)
SETTINGS_EXPORT_FORMAT_VERSION = "rpgforge.settings.v1"
SETTINGS_IMPORT_MODE_PROTECTED = "protected"
SETTINGS_IMPORT_MODE_REPLACE_ALL = "replace_all"
ACCEPTED_SETTINGS_IMPORT_MODES = {
    SETTINGS_IMPORT_MODE_PROTECTED,
    SETTINGS_IMPORT_MODE_REPLACE_ALL,
}
ACCEPTED_SETTINGS_FORMAT_VERSIONS = {
    SETTINGS_EXPORT_FORMAT_VERSION,
    "rpgforge_settings_v1",
    "1",
    1,
}
CHARACTER_ROLES = {"protagonist", "npc", "companion", "other"}
CHARACTER_VISIBILITIES = {"visible", "hidden"}


def game_detail_query(game_id: UUID, *, include_turns: bool = False):
    options = [
        selectinload(Game.config),
        selectinload(Game.state),
        selectinload(Game.lore_entries),
        selectinload(Game.modes),
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
        lore_entries=list(game.lore_entries),
        modes=list(game.modes),
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
            selectinload(Game.lore_entries),
            selectinload(Game.modes),
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
        "settings_import",
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
        game.config = GameConfig(worldview={}, script_outline={}, generation_settings={})
        db.add(game.config)
        db.flush()

    _ensure_baseline_version(db, game, "config", None, _config_snapshot(game))
    updates = payload.model_dump(exclude_unset=True)

    if "title" in updates and updates["title"] is not None:
        game.title = _clean_required(updates["title"], "标题不能为空。")
    if "genre" in updates:
        game.genre = _clean_optional(updates["genre"])
    if "description" in updates:
        game.description = _clean_optional(updates["description"])
    if "system_prompt" in updates:
        game.config.system_prompt = _clean_optional(updates["system_prompt"])
    if "generation_notes" in updates:
        game.config.generation_notes = _clean_optional(updates["generation_notes"])
    if "generation_settings" in updates:
        game.config.generation_settings = normalize_generation_settings(
            updates["generation_settings"]
        )

    if updates.get("worldview_json") is not None:
        worldview = _json_object(updates["worldview_json"], "worldview_json")
    else:
        worldview = dict(game.config.worldview or {})
    if "title" in updates and updates["title"] is not None:
        worldview["title"] = game.title
    if "genre" in updates:
        worldview["genre"] = game.genre or ""
    if "description" in updates:
        worldview["description"] = game.description or ""
    if payload.worldview is not None:
        _merge_clean_mapping(worldview, payload.worldview.model_dump(exclude_unset=True))
    game.config.worldview = worldview

    existing_script_outline = dict(game.config.script_outline or {})
    if updates.get("script_outline_json") is not None:
        script_outline = merge_required_script_fields(
            _json_object(updates["script_outline_json"], "script_outline_json"),
            existing_script_outline,
        )
    else:
        script_outline = existing_script_outline
    if "title" in updates and updates["title"] is not None:
        script_outline["title"] = game.title
    _merge_contract(script_outline, "campaign_contract", payload.campaign_contract)
    _merge_contract(script_outline, "director_contract", payload.director_contract)
    _merge_contract(script_outline, "story_contract", payload.story_contract)
    game.config.script_outline = protect_user_brief_contract(script_outline)

    touch_game(db, game_id)
    db.add(game)
    db.flush()
    _save_setting_version(db, game_id, "config", None, "updated", _config_snapshot(game))
    db.commit()
    return game_detail_response(get_game_or_404(db, game_id))


@router.post(
    "/{game_id}/memory/lore",
    response_model=LoreEntryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_game_lore_entry(
    game_id: UUID,
    payload: LoreEntryCreate,
    db: Session = DB_DEPENDENCY,
) -> LoreEntryRead:
    get_game_or_404(db, game_id)
    _assert_settings_editable(db, game_id)
    entry = LoreEntry(
        game_id=game_id,
        title=_clean_required(payload.title, "世界资料标题不能为空。"),
        type=_clean_optional(payload.type),
        keywords=_clean_list(payload.keywords),
        trigger_words=_clean_list(payload.trigger_words),
        priority=_clean_optional(payload.priority) or "medium",
        always_on=payload.always_on,
        visibility=_clean_optional(payload.visibility) or "mixed",
        public_info=_clean_optional(payload.public_info),
        gm_secret=_clean_optional(payload.gm_secret),
        content=_clean_required(payload.content, "世界资料内容不能为空。"),
        usage_note=_clean_optional(payload.usage_note),
        is_active=True,
        archived_at=None,
    )
    entry.embedding = _lore_embedding(entry)
    db.add(entry)
    db.flush()
    _save_setting_version(db, game_id, "lore", entry.id, "created", _lore_snapshot(entry))
    touch_game(db, game_id)
    db.commit()
    db.refresh(entry)
    return LoreEntryRead.model_validate(entry)


@router.patch("/{game_id}/memory/lore/{lore_id}", response_model=LoreEntryRead)
def update_game_lore_entry(
    game_id: UUID,
    lore_id: UUID,
    payload: LoreEntryUpdate,
    db: Session = DB_DEPENDENCY,
) -> LoreEntryRead:
    get_game_or_404(db, game_id)
    _assert_settings_editable(db, game_id)
    entry = _get_lore_or_404(db, game_id, lore_id)
    _ensure_baseline_version(
        db,
        None,
        "lore",
        entry.id,
        _lore_snapshot(entry),
        game_id=game_id,
    )
    previous_active = entry.is_active
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key in {"keywords", "trigger_words"}:
            setattr(entry, key, _clean_list(value or []))
        elif key == "always_on":
            entry.always_on = bool(value)
        elif key == "is_active":
            entry.is_active = bool(value)
            entry.archived_at = (
                None if entry.is_active else entry.archived_at or datetime.now(UTC)
            )
        elif isinstance(value, str) or value is None:
            if key in {"title", "content"}:
                setattr(entry, key, _clean_required(value, f"{key} 不能为空。"))
            else:
                setattr(entry, key, _clean_optional(value))
        else:
            setattr(entry, key, value)

    if entry.is_active and not previous_active:
        entry.archived_at = None
    entry.embedding = _lore_embedding(entry)
    db.add(entry)
    touch_game(db, game_id)
    action = "restored" if entry.is_active and not previous_active else "updated"
    db.flush()
    _save_setting_version(db, game_id, "lore", entry.id, action, _lore_snapshot(entry))
    db.commit()
    db.refresh(entry)
    return LoreEntryRead.model_validate(entry)


@router.delete("/{game_id}/memory/lore/{lore_id}", response_model=LoreEntryRead)
def archive_game_lore_entry(
    game_id: UUID,
    lore_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> LoreEntryRead:
    get_game_or_404(db, game_id)
    _assert_settings_editable(db, game_id)
    entry = _get_lore_or_404(db, game_id, lore_id)
    _ensure_baseline_version(
        db,
        None,
        "lore",
        entry.id,
        _lore_snapshot(entry),
        game_id=game_id,
    )
    entry.is_active = False
    entry.archived_at = datetime.now(UTC)
    db.add(entry)
    touch_game(db, game_id)
    db.flush()
    _save_setting_version(db, game_id, "lore", entry.id, "archived", _lore_snapshot(entry))
    db.commit()
    db.refresh(entry)
    return LoreEntryRead.model_validate(entry)


@router.post("/{game_id}/modes", response_model=ModeRead, status_code=status.HTTP_201_CREATED)
def create_game_mode(
    game_id: UUID,
    payload: ModeCreate,
    db: Session = DB_DEPENDENCY,
) -> ModeRead:
    get_game_or_404(db, game_id)
    _assert_settings_editable(db, game_id)
    mode = Mode(
        game_id=game_id,
        name=_clean_required(payload.name, "模式名称不能为空。"),
        triggers=_clean_list(payload.triggers),
        injection=_clean_required(payload.injection, "模式注入不能为空。"),
        priority=_clean_optional(payload.priority) or "medium",
        enabled=payload.enabled,
    )
    db.add(mode)
    db.flush()
    _save_setting_version(db, game_id, "mode", mode.id, "created", _mode_snapshot(mode))
    touch_game(db, game_id)
    db.commit()
    db.refresh(mode)
    return ModeRead.model_validate(mode)


@router.patch("/{game_id}/modes/{mode_id}", response_model=ModeRead)
def update_game_mode(
    game_id: UUID,
    mode_id: UUID,
    payload: ModeUpdate,
    db: Session = DB_DEPENDENCY,
) -> ModeRead:
    get_game_or_404(db, game_id)
    _assert_settings_editable(db, game_id)
    mode = _get_mode_or_404(db, game_id, mode_id)
    _ensure_baseline_version(
        db,
        None,
        "mode",
        mode.id,
        _mode_snapshot(mode),
        game_id=game_id,
    )
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "triggers":
            mode.triggers = _clean_list(value or [])
        elif key == "enabled":
            mode.enabled = bool(value)
        elif key in {"name", "injection"}:
            setattr(mode, key, _clean_required(value, f"{key} 不能为空。"))
        elif isinstance(value, str) or value is None:
            setattr(mode, key, _clean_optional(value))
        else:
            setattr(mode, key, value)

    db.add(mode)
    touch_game(db, game_id)
    db.flush()
    _save_setting_version(db, game_id, "mode", mode.id, "updated", _mode_snapshot(mode))
    db.commit()
    db.refresh(mode)
    return ModeRead.model_validate(mode)


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

    if version.scope == "config":
        _ensure_baseline_version(db, game, "config", None, _config_snapshot(game))
        _restore_config_snapshot(game, version.snapshot_json)
        db.add(game)
        db.flush()
        _save_setting_version(db, game_id, "config", None, "restored", _config_snapshot(game))
    elif version.scope == "lore":
        entry = _restore_lore_snapshot(db, game_id, version.snapshot_json)
        db.flush()
        _save_setting_version(db, game_id, "lore", entry.id, "restored", _lore_snapshot(entry))
    elif version.scope == "mode":
        mode = _restore_mode_snapshot(db, game_id, version.snapshot_json)
        db.flush()
        _save_setting_version(db, game_id, "mode", mode.id, "restored", _mode_snapshot(mode))
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported version scope.",
        )

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
        "lore_entries": [_lore_memory_payload(entry) for entry in game.lore_entries],
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


@router.post("/{game_id}/memory/lore/reindex", response_model=LoreReindexResponse)
def reindex_game_lore(game_id: UUID, db: Session = DB_DEPENDENCY) -> LoreReindexResponse:
    game = get_game_or_404(db, game_id)
    updated = LoreRetriever().rebuild_lore_embeddings(db, game.lore_entries)
    if updated:
        touch_game(db, game_id)
        db.commit()
    return LoreReindexResponse(total=len(game.lore_entries), updated=updated)


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


def _lore_memory_payload(entry) -> LoreEntryMemoryRead:
    payload = LoreEntryMemoryRead.model_validate(entry).model_dump()
    payload["embedding_configured"] = entry.embedding is not None
    return LoreEntryMemoryRead.model_validate(payload)


def _get_game_for_settings_transfer(db: Session, game_id: UUID) -> Game:
    game = db.scalars(
        select(Game)
        .options(
            selectinload(Game.config),
            selectinload(Game.lore_entries),
            selectinload(Game.modes),
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
    config = game.config
    payload: dict[str, Any] = {
        "format_version": SETTINGS_EXPORT_FORMAT_VERSION,
        "import_mode": SETTINGS_IMPORT_MODE_REPLACE_ALL,
    }
    if include_guides:
        payload["_ai_editing_guide"] = settings_export_ai_editing_guide()
        payload["_field_guide"] = settings_export_field_guide()
    payload.update(
        {
            "game": {
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
                "status": game.status,
            },
            "system_prompt": config.system_prompt if config else None,
            "generation_notes": config.generation_notes if config else None,
            "generation_settings": normalize_generation_settings(
                config.generation_settings if config else None
            ),
            "worldview": config.worldview if config else {},
            "script_outline": config.script_outline if config else {},
            "lore_entries": [_lore_export_payload(entry) for entry in game.lore_entries],
            "modes": [_mode_export_payload(mode) for mode in game.modes],
            "characters": [_character_export_payload(character) for character in game.characters],
        }
    )
    return payload


def _lore_export_payload(entry: LoreEntry) -> dict[str, Any]:
    return {
        "title": entry.title,
        "type": entry.type,
        "keywords": entry.keywords,
        "trigger_words": entry.trigger_words,
        "priority": entry.priority,
        "always_on": entry.always_on,
        "visibility": entry.visibility,
        "public_info": entry.public_info,
        "gm_secret": entry.gm_secret,
        "content": entry.content,
        "usage_note": entry.usage_note,
        "is_active": entry.is_active,
    }


def _mode_export_payload(mode: Mode) -> dict[str, Any]:
    return {
        "name": mode.name,
        "triggers": mode.triggers,
        "injection": mode.injection,
        "priority": mode.priority,
        "enabled": mode.enabled,
    }


def _character_export_payload(character: Character) -> dict[str, Any]:
    return {
        "id": str(character.id),
        "name": character.name,
        "aliases": character.aliases,
        "role": character.role,
        "identity": character.identity,
        "description": character.description,
        "appearance": character.appearance,
        "story_profile": character.story_profile,
        "portrait_prompt": character.portrait_prompt,
        "visibility": character.visibility,
        "is_visible": character.is_visible,
        "source": character.source,
        "sync_meta": character.sync_meta,
        "manual_fields": character.manual_fields,
    }


def _apply_settings_import(db: Session, game: Game, payload: dict[str, Any]) -> None:
    format_version = payload.get("format_version")
    if format_version not in ACCEPTED_SETTINGS_FORMAT_VERSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="settings JSON format_version 不受支持。",
        )
    import_mode = str(payload.get("import_mode") or SETTINGS_IMPORT_MODE_PROTECTED).strip()
    if import_mode not in ACCEPTED_SETTINGS_IMPORT_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="settings JSON import_mode 不受支持。",
        )
    replace_all = import_mode == SETTINGS_IMPORT_MODE_REPLACE_ALL

    if game.config is None:
        game.config = GameConfig(worldview={}, script_outline={}, generation_settings={})
        db.add(game.config)
        db.flush()

    _ensure_baseline_version(db, game, "config", None, _config_snapshot(game))

    game_payload = _optional_record(payload.get("game"), "game")
    config_payload = _optional_record(payload.get("config"), "config")
    game.title = _clean_required(
        game_payload.get("title", game.title),
        "导入设置中的标题不能为空。",
    )
    if "genre" in game_payload:
        game.genre = _clean_optional(game_payload.get("genre"))
    if "description" in game_payload:
        game.description = _clean_optional(game_payload.get("description"))
    if "status" in game_payload:
        game_status = _clean_required(
            game_payload.get("status"),
            "导入设置中的游戏状态不能为空。",
        )
        if len(game_status) > 32:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="导入设置中的游戏状态不能超过 32 个字符。",
            )
        game.status = game_status

    system_prompt = _pick_import_value(payload, config_payload, "system_prompt")
    if system_prompt is not _MISSING:
        game.config.system_prompt = _clean_optional(system_prompt)
    generation_notes = _pick_import_value(payload, config_payload, "generation_notes")
    if generation_notes is not _MISSING:
        game.config.generation_notes = _clean_optional(generation_notes)

    generation_settings = _pick_import_value(payload, config_payload, "generation_settings")
    game.config.generation_settings = normalize_generation_settings(
        {} if generation_settings is _MISSING else generation_settings
    )

    worldview = _pick_import_value(payload, config_payload, "worldview")
    game.config.worldview = _json_object({} if worldview is _MISSING else worldview, "worldview")

    existing_script_outline = dict(game.config.script_outline or {})
    script_outline = _pick_import_value(payload, config_payload, "script_outline")
    imported_script_outline = _json_object(
        {} if script_outline is _MISSING else script_outline,
        "script_outline",
    )
    if replace_all:
        game.config.script_outline = imported_script_outline
    else:
        game.config.script_outline = protect_user_brief_contract(
            merge_required_script_fields(imported_script_outline, existing_script_outline)
        )

    game.lore_entries = [
        _lore_entry_from_import(item)
        for item in _list_of_records(payload.get("lore_entries"), "lore_entries")
    ]
    game.modes = [
        _mode_from_import(item)
        for item in _list_of_records(payload.get("modes"), "modes")
    ]
    if replace_all:
        game.characters = _characters_from_import(
            game,
            _list_of_records(payload.get("characters"), "characters"),
        )


_MISSING = object()


def _pick_import_value(
    payload: dict[str, Any],
    config_payload: dict[str, Any],
    key: str,
) -> Any:
    if key in config_payload:
        return config_payload[key]
    if key in payload:
        return payload[key]
    return _MISSING


def _optional_record(value: Any, label: str) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    return _json_object(value, label)


def _list_of_records(value: Any, label: str) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} 必须是 JSON 数组。",
        )
    records: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label}[{index}] 必须是 JSON 对象。",
            )
        records.append(item)
    return records


def _lore_entry_from_import(item: dict[str, Any]) -> LoreEntry:
    entry = LoreEntry(
        title=_clean_required(item.get("title"), "世界资料标题不能为空。"),
        type=_clean_optional(item.get("type")),
        keywords=_clean_payload_list(item.get("keywords")),
        trigger_words=_clean_payload_list(item.get("trigger_words")),
        priority=_clean_optional(item.get("priority")) or "medium",
        always_on=_bool_value(item.get("always_on"), False),
        visibility=_clean_optional(item.get("visibility")) or "mixed",
        public_info=_clean_optional(item.get("public_info")),
        gm_secret=_clean_optional(item.get("gm_secret")),
        content=_clean_required(item.get("content"), "世界资料内容不能为空。"),
        usage_note=_clean_optional(item.get("usage_note")),
        is_active=_bool_value(item.get("is_active"), True),
    )
    entry.archived_at = None if entry.is_active else datetime.now(UTC)
    entry.embedding = _lore_embedding(entry)
    return entry


def _mode_from_import(item: dict[str, Any]) -> Mode:
    return Mode(
        name=_clean_required(item.get("name"), "模式名称不能为空。"),
        triggers=_clean_payload_list(item.get("triggers")),
        injection=_clean_required(item.get("injection"), "模式注入不能为空。"),
        priority=_clean_optional(item.get("priority")) or "medium",
        enabled=_bool_value(item.get("enabled"), True),
    )


def _characters_from_import(game: Game, records: list[dict[str, Any]]) -> list[Character]:
    existing_characters = list(game.characters)
    existing_by_id = {character.id: character for character in existing_characters}
    existing_by_name = {character.name: character for character in existing_characters}
    imported_characters: list[Character] = []
    used_existing_ids: set[UUID] = set()
    seen_names: set[str] = set()

    for index, item in enumerate(records):
        label = f"characters[{index}]"
        imported_id = _optional_uuid(item.get("id"), f"{label}.id")
        imported_name = _clean_required(item.get("name"), f"{label}.name 不能为空。")
        character = existing_by_id.get(imported_id) if imported_id else None
        if character is None:
            character = existing_by_name.get(imported_name)
        if character is not None and character.id in used_existing_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label} 重复引用了同一个角色。",
            )

        character = _character_from_import(item, label, character)
        if character.name in seen_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{label}.name 与其他导入角色重复。",
            )
        seen_names.add(character.name)
        if character.id is not None:
            used_existing_ids.add(character.id)
        imported_characters.append(character)

    return imported_characters


def _character_from_import(
    item: dict[str, Any],
    label: str,
    existing: Character | None,
) -> Character:
    character = existing or Character()
    role = _clean_optional(item.get("role")) or "npc"
    if role not in CHARACTER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label}.role 必须是 protagonist、npc、companion 或 other。",
        )
    visibility = _clean_optional(item.get("visibility")) or "visible"
    if visibility not in CHARACTER_VISIBILITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label}.visibility 必须是 visible 或 hidden。",
        )
    source = _clean_optional(item.get("source")) or "settings_import"
    if len(source) > 32:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label}.source 不能超过 32 个字符。",
        )

    character.name = _clean_required(item.get("name"), f"{label}.name 不能为空。")
    character.aliases = _clean_payload_list(item.get("aliases"))
    character.role = role
    character.identity = _clean_optional(item.get("identity"))
    character.description = _clean_optional(item.get("description"))
    character.appearance = _clean_optional(item.get("appearance"))
    character.story_profile = _optional_json_object(
        item.get("story_profile"),
        f"{label}.story_profile",
    )
    character.portrait_prompt = _clean_optional(item.get("portrait_prompt"))
    character.visibility = visibility
    character.is_visible = _bool_value(item.get("is_visible"), visibility == "visible")
    character.source = source
    character.sync_meta = _optional_json_object(item.get("sync_meta"), f"{label}.sync_meta")
    character.manual_fields = _clean_payload_list(item.get("manual_fields"))
    return character


def _optional_uuid(value: Any, label: str) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} 必须是合法 UUID。",
        ) from exc


def _optional_json_object(value: Any, label: str) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    return _json_object(value, label)


def _clean_payload_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return _clean_list(value)
    if isinstance(value, str):
        return _clean_list([value])
    return _clean_list([str(value)])


def _bool_value(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "y", "on"}:
            return True
        if text in {"false", "0", "no", "n", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


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
        "title": game.title,
        "genre": game.genre,
        "description": game.description,
        "system_prompt": config.system_prompt if config else None,
        "worldview": config.worldview if config else {},
        "script_outline": config.script_outline if config else {},
        "generation_settings": normalize_generation_settings(
            config.generation_settings if config else None
        ),
        "generation_notes": config.generation_notes if config else None,
    }


def _lore_snapshot(entry: LoreEntry) -> dict:
    return {
        "id": str(entry.id),
        "title": entry.title,
        "type": entry.type,
        "keywords": entry.keywords,
        "trigger_words": entry.trigger_words,
        "priority": entry.priority,
        "always_on": entry.always_on,
        "visibility": entry.visibility,
        "public_info": entry.public_info,
        "gm_secret": entry.gm_secret,
        "content": entry.content,
        "usage_note": entry.usage_note,
        "is_active": entry.is_active,
        "archived_at": entry.archived_at.isoformat() if entry.archived_at else None,
    }


def _mode_snapshot(mode: Mode) -> dict:
    return {
        "id": str(mode.id),
        "name": mode.name,
        "triggers": mode.triggers,
        "injection": mode.injection,
        "priority": mode.priority,
        "enabled": mode.enabled,
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


def _merge_contract(script_outline: dict, key: str, update) -> None:
    if update is None:
        return
    contract = dict(script_outline.get(key) or {})
    _merge_clean_mapping(contract, update.model_dump(exclude_unset=True))
    script_outline[key] = contract


def _json_object(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} 必须是 JSON 对象。",
        )
    return dict(value)


def _merge_clean_mapping(target: dict, updates: dict) -> None:
    for key, value in updates.items():
        if isinstance(value, str) or value is None:
            target[key] = _clean_optional(value)
        elif isinstance(value, list):
            target[key] = _clean_list(value)
        else:
            target[key] = value


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


def _lore_embedding(entry: LoreEntry) -> list[float] | None:
    return text_to_vector(
        "\n".join(
            [
                entry.title,
                entry.type or "",
                " ".join(entry.keywords),
                " ".join(entry.trigger_words),
                entry.public_info or "",
                entry.gm_secret or "",
                entry.content,
                entry.usage_note or "",
            ]
        )
    )


def _get_lore_or_404(db: Session, game_id: UUID, lore_id: UUID) -> LoreEntry:
    entry = db.scalars(
        select(LoreEntry).where(LoreEntry.id == lore_id, LoreEntry.game_id == game_id)
    ).first()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lore entry not found.")
    return entry


def _get_mode_or_404(db: Session, game_id: UUID, mode_id: UUID) -> Mode:
    mode = db.scalars(
        select(Mode).where(Mode.id == mode_id, Mode.game_id == game_id)
    ).first()
    if mode is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mode not found.")
    return mode


def _restore_config_snapshot(game: Game, snapshot: dict) -> None:
    if game.config is None:
        game.config = GameConfig(worldview={}, script_outline={}, generation_settings={})
    game.title = _clean_required(snapshot.get("title"), "版本中的标题为空，无法恢复。")
    game.genre = _clean_optional(snapshot.get("genre"))
    game.description = _clean_optional(snapshot.get("description"))
    game.config.system_prompt = _clean_optional(snapshot.get("system_prompt"))
    game.config.generation_notes = _clean_optional(snapshot.get("generation_notes"))
    game.config.worldview = (
        snapshot.get("worldview") if isinstance(snapshot.get("worldview"), dict) else {}
    )
    game.config.script_outline = (
        snapshot.get("script_outline") if isinstance(snapshot.get("script_outline"), dict) else {}
    )
    game.config.generation_settings = normalize_generation_settings(
        snapshot.get("generation_settings")
    )


def _restore_lore_snapshot(db: Session, game_id: UUID, snapshot: dict) -> LoreEntry:
    entity_id = UUID(str(snapshot.get("id")))
    entry = db.get(LoreEntry, entity_id)
    if entry is None:
        entry = LoreEntry(id=entity_id, game_id=game_id, title="", content="")
    if entry.game_id != game_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="版本不属于当前游戏。")
    entry.title = _clean_required(snapshot.get("title"), "版本中的世界资料标题为空，无法恢复。")
    entry.type = _clean_optional(snapshot.get("type"))
    entry.keywords = _clean_list(list(snapshot.get("keywords") or []))
    entry.trigger_words = _clean_list(list(snapshot.get("trigger_words") or []))
    entry.priority = _clean_optional(snapshot.get("priority")) or "medium"
    entry.always_on = bool(snapshot.get("always_on", False))
    entry.visibility = _clean_optional(snapshot.get("visibility")) or "mixed"
    entry.public_info = _clean_optional(snapshot.get("public_info"))
    entry.gm_secret = _clean_optional(snapshot.get("gm_secret"))
    entry.content = _clean_required(snapshot.get("content"), "版本中的世界资料内容为空，无法恢复。")
    entry.usage_note = _clean_optional(snapshot.get("usage_note"))
    entry.is_active = bool(snapshot.get("is_active", True))
    entry.archived_at = None if entry.is_active else datetime.now(UTC)
    entry.embedding = _lore_embedding(entry)
    db.add(entry)
    return entry


def _restore_mode_snapshot(db: Session, game_id: UUID, snapshot: dict) -> Mode:
    entity_id = UUID(str(snapshot.get("id")))
    mode = db.get(Mode, entity_id)
    if mode is None:
        mode = Mode(id=entity_id, game_id=game_id, name="", injection="")
    if mode.game_id != game_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="版本不属于当前游戏。")
    mode.name = _clean_required(snapshot.get("name"), "版本中的模式名称为空，无法恢复。")
    mode.triggers = _clean_list(list(snapshot.get("triggers") or []))
    mode.injection = _clean_required(snapshot.get("injection"), "版本中的模式注入为空，无法恢复。")
    mode.priority = _clean_optional(snapshot.get("priority")) or "medium"
    mode.enabled = bool(snapshot.get("enabled", True))
    db.add(mode)
    return mode


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
