from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.game import Game
from app.models.generator_job import TurnJob
from app.models.progress_save import GameProgressSave
from app.schemas.game import (
    GameDetail,
    GameProgressSaveCreate,
    GameProgressSaveRead,
    GameProgressSaveUpdate,
)
from app.services.game_activity import touch_game
from app.services.job_queue import reconcile_turn_job_liveness
from app.services.progress_saves import (
    create_progress_save,
    load_progress_save,
    progress_save_or_none,
    restart_game_progress,
)

router = APIRouter(tags=["progress"])
DB_DEPENDENCY = Depends(get_db)


def _game_query(game_id: UUID):
    return (
        select(Game)
        .options(
            selectinload(Game.config),
            selectinload(Game.state),
            selectinload(Game.summaries),
            selectinload(Game.characters),
        )
        .where(Game.id == game_id)
    )


def _get_game_or_404(db: Session, game_id: UUID) -> Game:
    game = db.scalars(_game_query(game_id)).first()
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found.")
    return game


@router.get(
    "/api/games/{game_id}/progress-saves",
    response_model=list[GameProgressSaveRead],
)
def list_progress_saves(
    game_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> list[GameProgressSave]:
    _get_game_or_404(db, game_id)
    return list(
        db.scalars(
            select(GameProgressSave)
            .where(GameProgressSave.game_id == game_id)
            .order_by(GameProgressSave.updated_at.desc())
        ).all()
    )


@router.post(
    "/api/games/{game_id}/progress-saves",
    response_model=GameProgressSaveRead,
    status_code=status.HTTP_201_CREATED,
)
def create_game_progress_save(
    game_id: UUID,
    payload: GameProgressSaveCreate,
    db: Session = DB_DEPENDENCY,
) -> GameProgressSave:
    game = _get_game_or_404(db, game_id)
    _assert_progress_editable(db, game_id)
    progress_save = create_progress_save(
        db,
        game,
        name=_clean_required(payload.name, "存档名称不能为空。"),
        note=_clean_optional(payload.note),
    )
    db.commit()
    db.refresh(progress_save)
    return progress_save


@router.patch(
    "/api/games/{game_id}/progress-saves/{save_id}",
    response_model=GameProgressSaveRead,
)
def update_game_progress_save(
    game_id: UUID,
    save_id: UUID,
    payload: GameProgressSaveUpdate,
    db: Session = DB_DEPENDENCY,
) -> GameProgressSave:
    _get_game_or_404(db, game_id)
    progress_save = _get_progress_save_or_404(db, game_id, save_id)
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates:
        progress_save.name = _clean_required(updates["name"], "存档名称不能为空。")
    if "note" in updates:
        progress_save.note = _clean_optional(updates["note"])
    db.add(progress_save)
    db.commit()
    db.refresh(progress_save)
    return progress_save


@router.post(
    "/api/games/{game_id}/progress-saves/{save_id}/load",
    response_model=GameDetail,
)
def load_game_progress_save(
    game_id: UUID,
    save_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> GameDetail:
    game = _get_game_or_404(db, game_id)
    _assert_progress_editable(db, game_id)
    progress_save = _get_progress_save_or_404(db, game_id, save_id)
    load_progress_save(db, game, progress_save)
    touch_game(db, game_id)
    db.commit()
    return _game_detail_response(_get_game_or_404(db, game_id))


@router.delete(
    "/api/games/{game_id}/progress-saves/{save_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_game_progress_save(
    game_id: UUID,
    save_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> None:
    _get_game_or_404(db, game_id)
    progress_save = _get_progress_save_or_404(db, game_id, save_id)
    db.delete(progress_save)
    db.commit()
    return None


@router.post("/api/games/{game_id}/progress/restart", response_model=GameDetail)
def restart_game_from_beginning(
    game_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> GameDetail:
    game = _get_game_or_404(db, game_id)
    _assert_progress_editable(db, game_id)
    restart_game_progress(db, game)
    touch_game(db, game_id)
    db.commit()
    return _game_detail_response(_get_game_or_404(db, game_id))


def _get_progress_save_or_404(
    db: Session,
    game_id: UUID,
    save_id: UUID,
) -> GameProgressSave:
    progress_save = progress_save_or_none(db, game_id, save_id)
    if progress_save is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Progress save not found.",
        )
    return progress_save


def _assert_progress_editable(db: Session, game_id: UUID) -> None:
    active_job = db.scalars(
        select(TurnJob)
        .where(
            TurnJob.game_id == game_id,
            TurnJob.status.in_(("pending", "running")),
        )
        .order_by(TurnJob.created_at.desc())
        .limit(1)
    ).first()
    if active_job is not None:
        if reconcile_turn_job_liveness(db, active_job):
            db.commit()
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="当前游戏仍有回合生成任务运行中，请完成后再操作进度存档。",
            )

    active_maintenance = db.scalars(
        select(TurnJob)
        .where(
            TurnJob.game_id == game_id,
            TurnJob.status == "completed",
            TurnJob.maintenance_status.in_(("pending", "running")),
            TurnJob.maintenance_stage == "state_extract",
        )
        .order_by(TurnJob.created_at.desc())
        .limit(1)
    ).first()
    if active_maintenance is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前游戏仍有状态提取任务运行中，请完成后再操作进度存档。",
        )


def _game_detail_response(game: Game) -> GameDetail:
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
