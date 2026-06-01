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

            # 走到这里的只有两种正常情况：无 delta（尚未提取）或 delta 属于待重试的失败态。
            # 失败态会重新提取并累加 attempt_count，超限后自动降级（见下方）。
            # 出现未知状态时仅告警、不崩溃（按失败态处理，避免破坏结算循环的防卡死目标）。
            if delta is not None and delta.status not in FAILED_SETTLEMENT_STATUSES:
                logger.warning(
                    "Unsettled delta for turn %s has unexpected status %r; treating as failed.",
                    turn.id,
                    delta.status,
                )
            # 已累计的尝试次数（含本回合历史失败），用于跨续玩累加判断是否超限。
            prior_attempts = int(getattr(delta, "attempt_count", 0) or 0) if delta else 0
            delta_json, used_attempts = await self._extract_with_retries(game, turn)
            total_attempts = prior_attempts + used_attempts
            if delta_json is None:
                if total_attempts >= self.max_attempts:
                    # 累计尝试达上限：自动降级为空 approved delta（跳过本回合状态变更），
                    # 记错误说明并告警，避免无限重试烧 LLM 卡死存档。
                    logger.error(
                        "State settlement for turn %s exhausted %s attempts (>= %s); "
                        "auto-skipping this turn with an empty approved delta. Last error: %s",
                        turn.id,
                        total_attempts,
                        self.max_attempts,
                        self._last_error,
                    )
                    skip_message = (
                        f"第 {turn.turn_number} 回合状态自动结算连续失败 {total_attempts} 次，"
                        f"已跳过该回合状态变更以保证游戏继续。最后错误：{self._last_error}"
                    )
                    self._auto_skip_failed_delta(db, game, turn, skip_message[:4000])
                    rebuild_game_state(db, game)
                    changed = True
                    continue
                message = f"第 {turn.turn_number} 回合状态自动结算失败。系统会在下次继续前重试。"
                _record_failed_delta(
                    db, game, turn, self._last_error or message, attempt_count=total_attempts
                )
                rebuild_game_state(db, game)
                raise StateSettlementError(message)

            approved = approve_turn_state_delta(
                db,
                game=game,
                turn=turn,
                delta_json=delta_json,
                approved_at=datetime.now(UTC),
            )
            # 记录累计尝试次数供观测（含本回合此前失败数）。delta 转 approved 后已属已结算态，
            # 不会再被重新提取，该计数仅作诊断留痕。
            approved.attempt_count = total_attempts
            db.add(approved)
            rebuild_game_state(db, game)
            changed = True

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

    def _auto_skip_failed_delta(self, db: Session, game: Game, turn: Turn, message: str) -> None:
        """累计尝试超限：把该回合 delta 落为空 approved（跳过状态变更，游戏可继续）。"""
        delta = _state_delta_for_turn(db, turn.id)
        turn.state_delta_json = {}
        if delta is None:
            delta = StateDelta(
                game_id=game.id,
                turn_id=turn.id,
                delta_json={},
                status="approved",
                error_message=message,
                approved_at=datetime.now(UTC),
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
        db.flush()


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


def _record_failed_delta(
    db: Session,
    game: Game,
    turn: Turn,
    error: str,
    *,
    attempt_count: int | None = None,
) -> StateDelta:
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
