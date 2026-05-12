from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.game import Game
from app.models.state_delta import StateDelta
from app.models.turn import Turn
from app.services.game_activity import touch_game
from app.services.state_applier import apply_state_delta

AUTO_APPLY_STATUSES = {"pending", "edited"}


def apply_pending_state_deltas(db: Session, game: Game) -> bool:
    if game.state is None:
        return False

    deltas = list(
        db.scalars(
            select(StateDelta)
            .options(selectinload(StateDelta.turn))
            .join(Turn, StateDelta.turn_id == Turn.id)
            .where(
                StateDelta.game_id == game.id,
                StateDelta.status.in_(AUTO_APPLY_STATUSES),
            )
            .order_by(Turn.turn_number.asc(), StateDelta.created_at.asc())
        ).all()
    )
    if not deltas:
        return False

    approved_at = datetime.now(UTC)
    for delta in deltas:
        game.state.state_json = apply_state_delta(game.state, delta.turn, delta.delta_json)
        game.state.current_turn = max(game.state.current_turn, delta.turn.turn_number)
        delta.status = "approved"
        delta.approved_at = approved_at
        db.add(delta)

    db.add(game.state)
    touch_game(db, game.id)
    db.commit()
    db.refresh(game.state)
    return True


def apply_pending_state_deltas_for_game_id(db: Session, game_id: UUID) -> bool:
    game = db.scalars(
        select(Game)
        .options(selectinload(Game.state))
        .where(Game.id == game_id)
    ).first()
    if game is None:
        return False
    return apply_pending_state_deltas(db, game)
