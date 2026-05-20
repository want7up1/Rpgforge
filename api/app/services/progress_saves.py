from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.progress_save import GameProgressSave
from app.models.state import GameState
from app.models.state_delta import StateDelta
from app.models.summary import Summary
from app.models.turn import Turn
from app.services.game_creator import build_default_initial_state
from app.services.state_v2 import normalize_state_v2


def create_progress_save(
    db: Session,
    game: Game,
    *,
    name: str,
    note: str | None = None,
) -> GameProgressSave:
    state = game.state
    turns = _game_turns(db, game.id)
    summaries = _game_summaries(db, game.id)
    state_deltas = _game_state_deltas(db, game.id)
    progress_save = GameProgressSave(
        game_id=game.id,
        name=name,
        note=note,
        state_current_turn=state.current_turn if state else 0,
        state_json=deepcopy(state.state_json if state else {}),
        state_summary=state.summary if state else None,
        turns_json=[_turn_snapshot(turn) for turn in turns],
        summaries_json=[_summary_snapshot(summary) for summary in summaries],
        state_deltas_json=[_state_delta_snapshot(delta) for delta in state_deltas],
        turn_count=len(turns),
        summary_count=len(summaries),
    )
    db.add(progress_save)
    db.flush()
    return progress_save


def load_progress_save(db: Session, game: Game, progress_save: GameProgressSave) -> None:
    _clear_runtime_progress(db, game.id)
    _restore_state(
        db,
        game,
        progress_save.state_json,
        progress_save.state_current_turn,
        progress_save.state_summary,
    )
    _restore_turns(db, game.id, progress_save.turns_json)
    _restore_summaries(db, game.id, progress_save.summaries_json)
    _restore_state_deltas(db, game.id, progress_save.state_deltas_json)
    db.flush()


def restart_game_progress(db: Session, game: Game) -> None:
    _clear_runtime_progress(db, game.id)
    initial_state = _initial_state_for_restart(game)
    _restore_state(db, game, initial_state, int(initial_state.get("current_turn") or 0), "")
    db.flush()


def progress_save_or_none(db: Session, game_id: UUID, save_id: UUID) -> GameProgressSave | None:
    return db.scalars(
        select(GameProgressSave).where(
            GameProgressSave.id == save_id,
            GameProgressSave.game_id == game_id,
        )
    ).first()


def _clear_runtime_progress(db: Session, game_id: UUID) -> None:
    for delta in _game_state_deltas(db, game_id):
        db.delete(delta)
    for summary in _game_summaries(db, game_id):
        db.delete(summary)
    for turn in _game_turns(db, game_id):
        db.delete(turn)
    db.flush()


def _restore_state(
    db: Session,
    game: Game,
    state_json: dict[str, Any],
    current_turn: int,
    summary: str | None,
) -> None:
    normalized_state = normalize_state_v2(deepcopy(state_json), current_turn)
    if game.state is None:
        game.state = GameState(
            current_turn=current_turn,
            state_json=normalized_state,
            initial_state_json=deepcopy(normalized_state),
            summary=summary,
        )
        db.add(game.state)
    else:
        game.state.current_turn = current_turn
        game.state.state_json = normalized_state
        game.state.summary = summary
        db.add(game.state)


def _restore_turns(db: Session, game_id: UUID, turns_json: list[dict[str, Any]]) -> None:
    for item in turns_json:
        db.add(
            Turn(
                id=UUID(str(item["id"])),
                game_id=game_id,
                turn_number=int(item.get("turn_number") or 0),
                player_input=str(item.get("player_input") or ""),
                gm_output=str(item.get("gm_output") or ""),
                visible_summary=_optional_text(item.get("visible_summary")),
                hidden_summary=_optional_text(item.get("hidden_summary")),
                state_delta_json=_record(item.get("state_delta_json")),
                action_options_json=_list(item.get("action_options_json")),
                model_used=_optional_text(item.get("model_used")),
                created_at=_datetime(item.get("created_at")),
            )
        )


def _restore_summaries(db: Session, game_id: UUID, summaries_json: list[dict[str, Any]]) -> None:
    for item in summaries_json:
        db.add(
            Summary(
                id=UUID(str(item["id"])),
                game_id=game_id,
                type=str(item.get("type") or "turn"),
                range_start_turn=_optional_int(item.get("range_start_turn")),
                range_end_turn=_optional_int(item.get("range_end_turn")),
                content=str(item.get("content") or ""),
                important_facts=_record(item.get("important_facts")),
                created_at=_datetime(item.get("created_at")),
                updated_at=_datetime(item.get("updated_at")),
            )
        )


def _restore_state_deltas(
    db: Session,
    game_id: UUID,
    state_deltas_json: list[dict[str, Any]],
) -> None:
    for item in state_deltas_json:
        turn_id = UUID(str(item["turn_id"]))
        delta_json = _record(item.get("delta_json"))
        status = str(item.get("status") or "pending")
        db.add(
            StateDelta(
                id=UUID(str(item["id"])),
                game_id=game_id,
                turn_id=turn_id,
                delta_json=delta_json,
                status=status,
                approved_at=_optional_datetime(item.get("approved_at")),
                created_at=_datetime(item.get("created_at")),
                updated_at=_datetime(item.get("updated_at")),
            )
        )
        turn = db.get(Turn, turn_id)
        if turn is not None:
            turn.state_delta_json = (
                deepcopy(delta_json)
                if status in {"approved", "edited", "pending"}
                else {}
            )
            db.add(turn)


def _initial_state_for_restart(game: Game) -> dict[str, Any]:
    if (
        game.state
        and isinstance(game.state.initial_state_json, dict)
        and game.state.initial_state_json
    ):
        initial_state = deepcopy(game.state.initial_state_json)
    else:
        initial_state = _fallback_initial_state(game)
    initial_state["current_turn"] = 0
    return normalize_state_v2(initial_state, 0)


def _fallback_initial_state(game: Game) -> dict[str, Any]:
    state = build_default_initial_state(game.title, game.description)
    worldview = (
        game.config.worldview
        if game.config and isinstance(game.config.worldview, dict)
        else {}
    )
    setting = _first_text(worldview.get("setting"), worldview.get("summary"))
    if setting:
        state["location"]["current"] = setting

    protagonist = next(
        (character for character in game.characters if character.role == "protagonist"),
        None,
    )
    if protagonist is not None:
        state["protagonist"]["name"] = protagonist.name
        state["protagonist"]["identity"] = protagonist.identity or protagonist.role
        if protagonist.appearance:
            state["protagonist"]["appearance"] = protagonist.appearance
    return state


def _game_turns(db: Session, game_id: UUID) -> list[Turn]:
    return list(
        db.scalars(
            select(Turn).where(Turn.game_id == game_id).order_by(Turn.turn_number.asc())
        ).all()
    )


def _game_summaries(db: Session, game_id: UUID) -> list[Summary]:
    return list(
        db.scalars(
            select(Summary).where(Summary.game_id == game_id).order_by(Summary.created_at.asc())
        ).all()
    )


def _game_state_deltas(db: Session, game_id: UUID) -> list[StateDelta]:
    return list(
        db.scalars(
            select(StateDelta)
            .where(StateDelta.game_id == game_id)
            .order_by(StateDelta.created_at.asc())
        ).all()
    )


def _turn_snapshot(turn: Turn) -> dict[str, Any]:
    return {
        "id": str(turn.id),
        "turn_number": turn.turn_number,
        "player_input": turn.player_input,
        "gm_output": turn.gm_output,
        "visible_summary": turn.visible_summary,
        "hidden_summary": turn.hidden_summary,
        "state_delta_json": deepcopy(turn.state_delta_json),
        "action_options_json": deepcopy(turn.action_options_json),
        "model_used": turn.model_used,
        "created_at": _isoformat(turn.created_at),
    }


def _summary_snapshot(summary: Summary) -> dict[str, Any]:
    return {
        "id": str(summary.id),
        "type": summary.type,
        "range_start_turn": summary.range_start_turn,
        "range_end_turn": summary.range_end_turn,
        "content": summary.content,
        "important_facts": deepcopy(summary.important_facts),
        "created_at": _isoformat(summary.created_at),
        "updated_at": _isoformat(summary.updated_at),
    }


def _state_delta_snapshot(delta: StateDelta) -> dict[str, Any]:
    return {
        "id": str(delta.id),
        "turn_id": str(delta.turn_id),
        "delta_json": deepcopy(delta.delta_json),
        "status": delta.status,
        "approved_at": _isoformat(delta.approved_at),
        "created_at": _isoformat(delta.created_at),
        "updated_at": _isoformat(delta.updated_at),
    }


def _record(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return deepcopy(value) if isinstance(value, list) else []


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _datetime(value: Any) -> datetime:
    parsed = _optional_datetime(value)
    if parsed is None:
        return datetime.now(UTC)
    return parsed


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
