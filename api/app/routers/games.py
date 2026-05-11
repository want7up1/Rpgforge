import shutil
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db.session import get_db
from app.models.character import Character
from app.models.game import Game
from app.models.generator_job import TurnJob
from app.schemas.game import (
    ContextDiagnosticRead,
    GameCreate,
    GameDetail,
    GameListItem,
    GameMemoryRead,
    LoreEntryMemoryRead,
    LoreReindexResponse,
    SummaryRead,
    SummaryRebuildResponse,
)
from app.services.context_compressor import ContextCompressor
from app.services.context_diagnostics import ContextDiagnosticService
from app.services.game_creator import build_manual_generated_config, create_game_from_config
from app.services.lore_retriever import LoreRetriever
from app.services.state_delta_auto_apply import apply_pending_state_deltas

router = APIRouter(prefix="/api/games", tags=["games"])
DB_DEPENDENCY = Depends(get_db)


def game_detail_query(game_id: UUID):
    return (
        select(Game)
        .options(
            selectinload(Game.config),
            selectinload(Game.state),
            selectinload(Game.lore_entries),
            selectinload(Game.modes),
            selectinload(Game.summaries),
            selectinload(Game.turns),
        )
        .where(Game.id == game_id)
    )


def get_game_or_404(db: Session, game_id: UUID) -> Game:
    game = db.scalars(game_detail_query(game_id)).first()
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found.")
    return game


@router.get("", response_model=list[GameListItem])
def list_games(db: Session = DB_DEPENDENCY) -> list[Game]:
    return list(db.scalars(select(Game).order_by(Game.updated_at.desc())).all())


@router.post("", response_model=GameDetail, status_code=status.HTTP_201_CREATED)
def create_game(payload: GameCreate, db: Session = DB_DEPENDENCY) -> Game:
    config = build_manual_generated_config(payload.title, payload.genre, payload.description)
    game = create_game_from_config(db, config)
    return get_game_or_404(db, game.id)


@router.get("/{game_id}", response_model=GameDetail)
def get_game(game_id: UUID, db: Session = DB_DEPENDENCY) -> Game:
    game = get_game_or_404(db, game_id)
    if apply_pending_state_deltas(db, game):
        game = get_game_or_404(db, game_id)
    return game


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


@router.get("/{game_id}/memory", response_model=GameMemoryRead)
def get_game_memory(game_id: UUID, db: Session = DB_DEPENDENCY) -> dict:
    game = get_game_or_404(db, game_id)
    if apply_pending_state_deltas(db, game):
        game = get_game_or_404(db, game_id)
    return {
        "game": GameListItem.model_validate(game),
        "current_turn": game.state.current_turn if game.state else 0,
        "turn_count": len(game.turns),
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
    return LoreReindexResponse(total=len(game.lore_entries), updated=updated)


@router.post("/{game_id}/memory/summaries/rebuild", response_model=SummaryRebuildResponse)
def rebuild_game_summaries(
    game_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> SummaryRebuildResponse:
    game = get_game_or_404(db, game_id)
    summaries = ContextCompressor().rebuild_from_history(db, game)
    return SummaryRebuildResponse(
        total=len(summaries),
        summaries=[SummaryRead.model_validate(summary) for summary in summaries],
    )


def _lore_memory_payload(entry) -> LoreEntryMemoryRead:
    payload = LoreEntryMemoryRead.model_validate(entry).model_dump()
    payload["embedding_configured"] = entry.embedding is not None
    return LoreEntryMemoryRead.model_validate(payload)


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
