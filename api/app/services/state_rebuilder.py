from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.game import Game
from app.models.state import GameState
from app.models.state_delta import StateDelta
from app.models.turn import Turn
from app.services.game_creator import build_default_initial_state
from app.services.state_applier import apply_state_delta
from app.services.state_v2 import normalize_state_v2
from app.services.story_settings import initial_story_progress


def approve_turn_state_delta(
    db: Session,
    *,
    game: Game,
    turn: Turn,
    delta_json: dict[str, Any],
    approved_at: datetime | None = None,
) -> StateDelta:
    approved_at = approved_at or datetime.now(UTC)
    delta = db.scalars(select(StateDelta).where(StateDelta.turn_id == turn.id)).first()
    turn.state_delta_json = deepcopy(delta_json)
    if delta is None:
        delta = StateDelta(
            game_id=game.id,
            turn_id=turn.id,
            delta_json=deepcopy(delta_json),
            status="approved",
            error_message=None,
            approved_at=approved_at,
        )
    else:
        delta.game_id = game.id
        delta.delta_json = deepcopy(delta_json)
        delta.status = "approved"
        delta.error_message = None
        delta.approved_at = approved_at

    db.add(turn)
    db.add(delta)
    db.flush()
    return delta


def rebuild_game_state(db: Session, game_or_id: Game | UUID) -> GameState | None:
    game = _resolve_game(db, game_or_id)
    if game is None or game.state is None:
        return None

    state = game.state
    base_state, base_changed = _initial_state_for_rebuild(game)
    base_turn = int(base_state.get("current_turn") or 0)
    normalized_base_state = normalize_state_v2(base_state, base_turn)
    if base_changed:
        state.initial_state_json = deepcopy(normalized_base_state)
    state.current_turn = base_turn
    state.state_json = normalized_base_state
    db.add(state)
    db.flush()

    for delta in _approved_state_deltas(db, game.id):
        state.state_json = apply_state_delta(state, delta.turn, delta.delta_json)
        state.current_turn = max(state.current_turn, delta.turn.turn_number)

    db.add(state)
    db.flush()
    return state


def sync_turn_state_delta(delta: StateDelta, *, active: bool) -> None:
    if delta.turn is None:
        return
    delta.turn.state_delta_json = deepcopy(delta.delta_json) if active else {}


def _resolve_game(db: Session, game_or_id: Game | UUID) -> Game | None:
    if isinstance(game_or_id, Game):
        return game_or_id
    return db.scalars(
        select(Game)
        .options(
            selectinload(Game.config),
            selectinload(Game.state),
        )
        .where(Game.id == game_or_id)
    ).first()


def _approved_state_deltas(db: Session, game_id: UUID) -> list[StateDelta]:
    return list(
        db.scalars(
            select(StateDelta)
            .options(selectinload(StateDelta.turn))
            .join(Turn, StateDelta.turn_id == Turn.id)
            .where(
                StateDelta.game_id == game_id,
                StateDelta.status == "approved",
            )
            .order_by(Turn.turn_number.asc(), StateDelta.created_at.asc())
        ).all()
    )


def _initial_state_for_rebuild(game: Game) -> tuple[dict[str, Any], bool]:
    state = game.state
    changed = False
    if state and isinstance(state.initial_state_json, dict) and state.initial_state_json:
        initial_state = deepcopy(state.initial_state_json)
    else:
        initial_state = build_default_initial_state(game.title, game.description)
        changed = True

    if game.config is not None and not _has_current_act(initial_state.get("story_progress")):
        initial_state["story_progress"] = _merged_story_progress(
            initial_state.get("story_progress"),
            initial_story_progress(game.config),
        )
        changed = True
    initial_state["current_turn"] = int(initial_state.get("current_turn") or 0)
    return initial_state, changed


def _has_current_act(value: Any) -> bool:
    return isinstance(value, dict) and bool(_text(value.get("current_act") or value.get("act")))


def _merged_story_progress(value: Any, default: dict[str, Any]) -> dict[str, Any]:
    progress = dict(default)
    if isinstance(value, dict):
        progress.update(value)
    if not _text(progress.get("current_act") or progress.get("act")):
        progress["current_act"] = _text(default.get("current_act"))
    return progress


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is not None and not isinstance(value, (dict, list)):
        return str(value).strip()
    return ""
