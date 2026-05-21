from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.game import Game
from app.models.state import GameState
from app.models.state_delta import StateDelta
from app.schemas.game import GameStateRead
from app.schemas.state_delta import StateDeltaRead, StateDeltaUpdate
from app.services.game_activity import touch_game
from app.services.state_delta_auto_apply import apply_pending_state_deltas
from app.services.state_rebuilder import rebuild_game_state, sync_turn_state_delta

router = APIRouter(tags=["states"])
DB_DEPENDENCY = Depends(get_db)
EDITABLE_STATUSES = {"pending", "edited"}
REJECTABLE_STATUSES = {"pending", "edited", "approved"}


def state_game_query(game_id: UUID):
    return (
        select(Game)
        .options(selectinload(Game.state))
        .where(Game.id == game_id)
    )


def get_game_or_404(db: Session, game_id: UUID) -> Game:
    game = db.scalars(state_game_query(game_id)).first()
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found.")
    return game


def get_state_or_404(game: Game) -> GameState:
    if game.state is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game state not found.")
    return game.state


def get_delta_or_404(db: Session, game_id: UUID, delta_id: UUID) -> StateDelta:
    delta = db.scalars(
        select(StateDelta)
        .options(selectinload(StateDelta.turn))
        .where(StateDelta.game_id == game_id, StateDelta.id == delta_id)
    ).first()
    if delta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="State delta not found.")
    return delta


def ensure_editable(delta: StateDelta) -> None:
    if delta.status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"State delta is already {delta.status}.",
        )


def ensure_rejectable(delta: StateDelta) -> None:
    if delta.status not in REJECTABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"State delta is already {delta.status}.",
        )


@router.get("/api/games/{game_id}/state", response_model=GameStateRead)
def get_game_state(game_id: UUID, db: Session = DB_DEPENDENCY) -> GameState:
    game = get_game_or_404(db, game_id)
    apply_pending_state_deltas(db, game)
    return get_state_or_404(game)


@router.get("/api/games/{game_id}/state-deltas", response_model=list[StateDeltaRead])
def list_state_deltas(
    game_id: UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = DB_DEPENDENCY,
) -> list[StateDelta]:
    get_game_or_404(db, game_id)
    query = select(StateDelta).where(StateDelta.game_id == game_id)
    if status_filter:
        query = query.where(StateDelta.status == status_filter)
    return list(db.scalars(query.order_by(StateDelta.created_at.desc())).all())


@router.patch("/api/games/{game_id}/state-deltas/{delta_id}", response_model=StateDeltaRead)
def update_state_delta(
    game_id: UUID,
    delta_id: UUID,
    payload: StateDeltaUpdate,
    db: Session = DB_DEPENDENCY,
) -> StateDelta:
    get_game_or_404(db, game_id)
    delta = get_delta_or_404(db, game_id, delta_id)
    ensure_editable(delta)
    delta.delta_json = payload.delta_json
    delta.status = "edited"
    delta.error_message = None
    delta.approved_at = None
    sync_turn_state_delta(delta, active=True)
    db.add(delta.turn)
    db.add(delta)
    rebuild_game_state(db, game_id)
    touch_game(db, game_id)
    db.commit()
    db.refresh(delta)
    return delta


@router.post(
    "/api/games/{game_id}/state-deltas/{delta_id}/approve",
    response_model=GameStateRead,
)
def approve_state_delta(
    game_id: UUID,
    delta_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> GameState:
    game = get_game_or_404(db, game_id)
    game_state = get_state_or_404(game)
    delta = get_delta_or_404(db, game_id, delta_id)
    ensure_editable(delta)

    delta.status = "approved"
    delta.error_message = None
    delta.approved_at = datetime.now(UTC)
    sync_turn_state_delta(delta, active=True)
    db.add(delta.turn)
    db.add(game_state)
    db.add(delta)
    rebuild_game_state(db, game)
    touch_game(db, game_id)
    db.commit()
    db.refresh(game_state)
    return game_state


@router.post(
    "/api/games/{game_id}/state-deltas/{delta_id}/reject",
    response_model=StateDeltaRead,
)
def reject_state_delta(
    game_id: UUID,
    delta_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> StateDelta:
    game = get_game_or_404(db, game_id)
    delta = get_delta_or_404(db, game_id, delta_id)
    ensure_rejectable(delta)
    delta.status = "rejected"
    delta.error_message = None
    delta.approved_at = None
    sync_turn_state_delta(delta, active=False)
    db.add(delta.turn)
    db.add(delta)
    rebuild_game_state(db, game)
    touch_game(db, game_id)
    db.commit()
    db.refresh(delta)
    return delta
