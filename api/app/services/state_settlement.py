from __future__ import annotations

import logging
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.game import Game
from app.models.state_delta import StateDelta
from app.models.turn import Turn
from app.services.deepseek_client import DeepSeekError
from app.services.state_extractor import StateExtractor, StateExtractorValidationError
from app.services.state_rebuilder import (
    approve_turn_state_delta,
    rebuild_game_state,
    sync_turn_state_delta,
)

logger = logging.getLogger(__name__)

STATE_SETTLEMENT_RETRY_ATTEMPTS = 3
AUTO_APPROVE_STATUSES = {"pending", "edited"}
FAILED_SETTLEMENT_STATUSES = {"failed"}
SETTLED_STATUSES = {"approved", "rejected"}


class StateSettlementError(RuntimeError):
    pass


class StateSettlementService:
    def __init__(
        self,
        *,
        extractor: StateExtractor | None = None,
        retry_attempts: int = STATE_SETTLEMENT_RETRY_ATTEMPTS,
    ) -> None:
        self.extractor = extractor or StateExtractor()
        self.retry_attempts = max(1, retry_attempts)

    async def ensure_settled(self, db: Session, game: Game) -> bool:
        if game.state is None:
            return False

        changed = rebuild_game_state(db, game) is not None
        for turn in _game_turns(db, game.id):
            delta = _state_delta_for_turn(db, turn.id)
            if delta is not None and delta.status in SETTLED_STATUSES:
                if delta.status == "rejected":
                    sync_turn_state_delta(delta, active=False)
                continue

            if delta is not None and delta.status in AUTO_APPROVE_STATUSES:
                delta.status = "approved"
                delta.error_message = None
                delta.approved_at = datetime.now(UTC)
                sync_turn_state_delta(delta, active=True)
                db.add(delta)
                db.add(turn)
                rebuild_game_state(db, game)
                changed = True
                continue

            delta_json = await self._extract_with_retries(game, turn)
            if delta_json is None:
                message = f"第 {turn.turn_number} 回合状态自动结算失败。系统会在下次继续前重试。"
                _record_failed_delta(db, game, turn, self._last_error or message)
                rebuild_game_state(db, game)
                raise StateSettlementError(message)

            approve_turn_state_delta(
                db,
                game=game,
                turn=turn,
                delta_json=delta_json,
                approved_at=datetime.now(UTC),
            )
            rebuild_game_state(db, game)
            changed = True

        return changed

    async def _extract_with_retries(self, game: Game, turn: Turn) -> dict[str, Any] | None:
        self._last_error = ""
        for attempt in range(1, self.retry_attempts + 1):
            try:
                return await self.extractor.extract(game, turn)
            except (DeepSeekError, StateExtractorValidationError, ValueError) as exc:
                self._last_error = str(exc)
                logger.warning(
                    "State settlement extraction failed for turn %s on attempt %s/%s: %s",
                    turn.id,
                    attempt,
                    self.retry_attempts,
                    exc,
                )
        return None


def _game_turns(db: Session, game_id) -> list[Turn]:
    return list(
        db.scalars(
            select(Turn).where(Turn.game_id == game_id).order_by(Turn.turn_number.asc())
        ).all()
    )


def _state_delta_for_turn(db: Session, turn_id) -> StateDelta | None:
    return db.scalars(
        select(StateDelta)
        .options(selectinload(StateDelta.turn))
        .where(StateDelta.turn_id == turn_id)
    ).first()


def _record_failed_delta(db: Session, game: Game, turn: Turn, error: str) -> StateDelta:
    delta = _state_delta_for_turn(db, turn.id)
    if delta is None:
        delta = StateDelta(
            game_id=game.id,
            turn_id=turn.id,
            delta_json={},
            status="failed",
            error_message=error[:4000],
            approved_at=None,
        )
    else:
        delta.game_id = game.id
        delta.delta_json = deepcopy(delta.delta_json or {})
        delta.status = "failed"
        delta.error_message = error[:4000]
        delta.approved_at = None
    turn.state_delta_json = {}
    db.add(turn)
    db.add(delta)
    db.flush()
    return delta


def record_failed_turn_state_delta(
    db: Session,
    *,
    game: Game,
    turn: Turn,
    error: str,
) -> StateDelta:
    return _record_failed_delta(db, game, turn, error)
