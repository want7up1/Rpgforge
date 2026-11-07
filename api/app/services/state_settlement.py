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
    apply_approved_turn_delta,
    approve_turn_state_delta,
    load_turn_state_history,
    rebuild_game_state,
    sync_turn_state_delta,
    update_turn_settlement_receipt,
)
from app.services.story_settings import progress_rules_from_config

logger = logging.getLogger(__name__)

STATE_SETTLEMENT_RETRY_ATTEMPTS = 3
# 单回合状态提取累计尝试上限。每次 ensure_settled 最多烧 retry_attempts 次模型，
# 跨多次续玩累加到该上限后自动降级为空 approved delta，避免确定性失败无限烧 LLM 卡死存档。
STATE_SETTLEMENT_MAX_ATTEMPTS = 9
AUTO_APPROVE_STATUSES = {"pending", "edited"}
# failed 状态：尚未结算、需重试提取（区别于已结算的 approved/rejected）。
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
        max_attempts: int = STATE_SETTLEMENT_MAX_ATTEMPTS,
    ) -> None:
        self.extractor = extractor or StateExtractor()
        self.retry_attempts = max(1, retry_attempts)
        # 累计尝试上限至少不小于单次重试数，否则首次结算就会被判超限。
        self.max_attempts = max(self.retry_attempts, max_attempts)

    async def ensure_settled(self, db: Session, game: Game) -> bool:
        if game.state is None:
            return False

        history = load_turn_state_history(db, game.id)
        rules = progress_rules_from_config(game.config)
        before_state = game.state.state_json
        before_seed = game.state.initial_state_json
        before_turn = game.state.current_turn
        before_receipts = [getattr(turn, "settlement_receipt", None) for turn, _ in history]
        rebuild_game_state(db, game, history=history, rules=rules)
        changed = (
            before_state != game.state.state_json
            or before_seed != game.state.initial_state_json
            or before_turn != game.state.current_turn
            or before_receipts != [turn.settlement_receipt for turn, _ in history]
        )
        for index, (turn, delta) in enumerate(history):
            if delta is not None and delta.status in SETTLED_STATUSES:
                if delta.status == "rejected" and turn.state_delta_json:
                    sync_turn_state_delta(delta, active=False)
                    changed = True
                continue

            if delta is not None and delta.status in AUTO_APPROVE_STATUSES:
                delta.status = "approved"
                delta.error_message = None
                delta.approved_at = datetime.now(UTC)
                sync_turn_state_delta(delta, active=True)
                db.add(delta)
                db.add(turn)
            else:
                if delta is not None and delta.status not in FAILED_SETTLEMENT_STATUSES:
                    logger.warning(
                        "Unsettled delta for turn %s has unexpected status %r; treating as failed.",
                        turn.id, delta.status,
                    )
                prior_attempts = int(getattr(delta, "attempt_count", 0) or 0) if delta else 0
                delta_json, used_attempts = await self._extract_with_retries(game, turn)
                total_attempts = prior_attempts + used_attempts
                if delta_json is None:
                    if total_attempts < self.max_attempts:
                        message = (
                            f"第 {turn.turn_number} 回合状态自动结算失败。系统会在下次继续前重试。"
                        )
                        _record_failed_delta(
                            db, game, turn, self._last_error or message,
                            attempt_count=total_attempts,
                            existing_delta=delta, lookup_existing=False,
                        )
                        raise StateSettlementError(message)
                    logger.error(
                        "State settlement for turn %s exhausted %s attempts; auto-skipping: %s",
                        turn.id, total_attempts, self._last_error,
                    )
                    message = (
                        f"第 {turn.turn_number} 回合状态自动结算连续失败 {total_attempts} 次，"
                        f"已跳过该回合状态变更以保证游戏继续。最后错误：{self._last_error}"
                    )
                    delta = self._auto_skip_failed_delta(
                        db, game, turn, message[:4000], existing_delta=delta,
                        lookup_existing=False,
                    )
                else:
                    delta = approve_turn_state_delta(
                        db, game=game, turn=turn, delta_json=delta_json,
                        existing_delta=delta, lookup_existing=False,
                    )
                    delta.attempt_count = total_attempts
                    db.add(delta)

            history[index] = (turn, delta)
            # Tail recovery can append once. An insertion before already-approved
            # history must still replay in order under the current story settings.
            if turn.turn_number >= game.state.current_turn:
                apply_approved_turn_delta(db, game, turn, delta, rules=rules)
            else:
                rebuild_game_state(db, game, history=history, rules=rules)
            changed = True

        db.flush()
        return changed

    async def _extract_with_retries(
        self, game: Game, turn: Turn
    ) -> tuple[dict[str, Any] | None, int]:
        """返回 (delta_json | None, 本次实际消耗的模型调用次数)。"""
        self._last_error = ""
        for attempt in range(1, self.retry_attempts + 1):
            try:
                return await self.extractor.extract(game, turn), attempt
            except (DeepSeekError, StateExtractorValidationError, ValueError) as exc:
                self._last_error = str(exc)
                logger.warning(
                    "State settlement extraction failed for turn %s on attempt %s/%s: %s",
                    turn.id,
                    attempt,
                    self.retry_attempts,
                    exc,
                )
        return None, self.retry_attempts

    def _auto_skip_failed_delta(
        self, db: Session, game: Game, turn: Turn, message: str, *,
        existing_delta: StateDelta | None = None, lookup_existing: bool = True,
    ) -> StateDelta:
        """Keep a distinct skipped receipt while permitting the game to continue."""
        delta = existing_delta
        if delta is None and lookup_existing:
            delta = _state_delta_for_turn(db, turn.id)
        turn.state_delta_json = {}
        if delta is None:
            delta = StateDelta(
                game_id=game.id, turn_id=turn.id, delta_json={}, status="approved",
                error_message=message, approved_at=datetime.now(UTC),
                attempt_count=self.max_attempts,
            )
        else:
            delta.game_id = game.id
            delta.delta_json = {}
            delta.status = "approved"
            delta.error_message = message
            delta.approved_at = datetime.now(UTC)
            delta.attempt_count = max(int(delta.attempt_count or 0), self.max_attempts)
        db.add(turn)
        db.add(delta)
        state = game.state.state_json if game.state is not None else {}
        update_turn_settlement_receipt(db, turn, delta, state, state)
        db.flush()
        return delta


def _state_delta_for_turn(db: Session, turn_id) -> StateDelta | None:
    return db.scalars(
        select(StateDelta)
        .options(selectinload(StateDelta.turn))
        .where(StateDelta.turn_id == turn_id)
    ).first()


def _record_failed_delta(
    db: Session,
    game: Game,
    turn: Turn,
    error: str,
    *,
    attempt_count: int | None = None,
    existing_delta: StateDelta | None = None,
    lookup_existing: bool = True,
) -> StateDelta:
    delta = existing_delta
    if delta is None and lookup_existing:
        delta = _state_delta_for_turn(db, turn.id)
    if delta is None:
        delta = StateDelta(
            game_id=game.id,
            turn_id=turn.id,
            delta_json={},
            status="failed",
            error_message=error[:4000],
            approved_at=None,
            attempt_count=max(0, attempt_count or 0),
        )
    else:
        delta.game_id = game.id
        delta.delta_json = deepcopy(delta.delta_json or {})
        delta.status = "failed"
        delta.error_message = error[:4000]
        delta.approved_at = None
        if attempt_count is not None:
            # 取较大值，避免跨调用回退累计计数（不同入口可能传入不同口径）。
            delta.attempt_count = max(int(delta.attempt_count or 0), attempt_count)
    turn.state_delta_json = {}
    db.add(turn)
    db.add(delta)
    state = game.state.state_json if game.state is not None else {}
    update_turn_settlement_receipt(db, turn, delta, state, state)
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
