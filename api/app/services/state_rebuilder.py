from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.game import Game
from app.models.state import GameState
from app.models.state_delta import StateDelta
from app.models.turn import Turn
from app.services.game_creator import build_default_initial_state
from app.services.progress_rules import ProgressRules
from app.services.settlement_receipts import build_settlement_receipt
from app.services.state_applier import apply_state_delta
from app.services.state_v2 import normalize_state_v2
from app.services.story_settings import initial_story_progress, progress_rules_from_config
from app.services.timeline import clean_replay_seed

StateHistory = list[tuple[Turn, StateDelta | None]]


def approve_turn_state_delta(
    db: Session,
    *,
    game: Game,
    turn: Turn,
    delta_json: dict[str, Any],
    approved_at: datetime | None = None,
    existing_delta: StateDelta | None = None,
    lookup_existing: bool = True,
) -> StateDelta:
    approved_at = approved_at or datetime.now(UTC)
    delta = existing_delta
    if delta is None and lookup_existing:
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


def rebuild_game_state(
    db: Session, game_or_id: Game | UUID, *,
    history: StateHistory | None = None, rules: ProgressRules | None = None,
) -> GameState | None:
    game = _resolve_game(db, game_or_id)
    if game is None or game.state is None:
        return None

    state = game.state
    rules = rules or progress_rules_from_config(game.config)
    history = history if history is not None else load_turn_state_history(db, game.id)
    base_state, _ = _initial_state_for_rebuild(game, rules=rules)
    base_turn = int(base_state.get("current_turn") or 0)
    normalized_base_state = normalize_state_v2(base_state, base_turn)
    base_changed = state.initial_state_json != normalized_base_state
    if base_changed:
        state.initial_state_json = deepcopy(normalized_base_state)
    # Fold off the ORM object: an intermediate seed must never be flushed as live state.
    folded = SimpleNamespace(state_json=normalized_base_state, game=game)
    current_turn = base_turn
    for turn, delta in history:
        before = folded.state_json
        if delta is not None and delta.status == "approved":
            folded.state_json = apply_state_delta(folded, turn, delta.delta_json, rules=rules)
            current_turn = max(current_turn, turn.turn_number)
        update_turn_settlement_receipt(db, turn, delta, before, folded.state_json)

    final_state = folded.state_json
    # Endings belong to the live timeline, never to the seed. Keep a generated
    # epilogue only while the replay still reaches a terminal state.
    old_progress = (state.state_json or {}).get("story_progress") or {}
    progress = final_state.get("story_progress") or {}
    if (progress.get("campaign_complete") or progress.get("defeat")) and old_progress.get(
        "epilogue"
    ):
        progress["epilogue"] = old_progress["epilogue"]
        final_state = normalize_state_v2(final_state, current_turn)
    if state.state_json != final_state or state.current_turn != current_turn or base_changed:
        state.state_json = final_state
        state.current_turn = current_turn
        db.add(state)
    db.flush()
    return state


def apply_approved_turn_delta(
    db: Session, game: Game, turn: Turn, delta: StateDelta, *, rules: ProgressRules,
) -> None:
    """Append one approved tail delta after a known-correct replay prefix."""
    state = game.state
    if state is None:
        return
    before = state.state_json
    state.state_json = apply_state_delta(state, turn, delta.delta_json, rules=rules)
    state.current_turn = max(state.current_turn, turn.turn_number)
    update_turn_settlement_receipt(db, turn, delta, before, state.state_json)
    db.add(state)


def update_turn_settlement_receipt(
    db: Session, turn: Turn, delta: StateDelta | None,
    before: dict[str, Any], after: dict[str, Any],
) -> bool:
    status = delta.status if delta is not None else "pending"
    if status == "approved":
        status = "skipped" if delta.error_message and not delta.delta_json else "confirmed"
    elif status == "edited":
        status = "pending"
    receipt = build_settlement_receipt(
        before, after, delta.delta_json if delta is not None else {},
        turn_number=turn.turn_number, status=status,
        message=(delta.error_message or "") if delta is not None else "",
    )
    if getattr(turn, "settlement_receipt", None) == receipt:
        return False
    turn.settlement_receipt = receipt
    db.add(turn)
    return True


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


def load_turn_state_history(db: Session, game_id: UUID) -> StateHistory:
    """One ordered read, including turns whose extraction has not produced a delta."""
    return list(db.execute(
        select(Turn, StateDelta)
        .outerjoin(StateDelta, (StateDelta.turn_id == Turn.id) & (StateDelta.game_id == game_id))
        .where(Turn.game_id == game_id)
        .order_by(Turn.turn_number.asc(), StateDelta.created_at.asc())
    ).all())


def _initial_state_for_rebuild(
    game: Game, *, rules: ProgressRules | None = None,
) -> tuple[dict[str, Any], bool]:
    state = game.state
    changed = False
    if state and isinstance(state.initial_state_json, dict) and state.initial_state_json:
        initial_state = state.initial_state_json
    else:
        initial_state = build_default_initial_state(game.title, game.description)
        changed = True

    clean_seed = clean_replay_seed(initial_state)
    if clean_seed != initial_state:
        changed = True
    initial_state = clean_seed

    if _sync_source_variables(initial_state, game):
        changed = True

    if game.config is not None and not _has_current_act(initial_state.get("story_progress")):
        initial_state["story_progress"] = _merged_story_progress(
            initial_state.get("story_progress"),
            initial_story_progress(rules or game.config),
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


def _sync_source_variables(state: dict[str, Any], game: Game) -> bool:
    variables = state.setdefault("variables", {})
    changed = False
    if not isinstance(variables, dict):
        variables = {}
        state["variables"] = variables
        changed = True

    expected = {
        "source_title": _text(game.title),
        "source_description": _text(game.description),
    }
    for key, value in expected.items():
        if variables.get(key) != value:
            variables[key] = value
            changed = True
    return changed
