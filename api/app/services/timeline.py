"""Short transaction guards shared by turn admission, restore and async writers.

Call guards before modifying ORM objects; never keep the game row locked while
awaiting a model or queue. Revision tracks accepted actions/config changes, while
generation invalidates work belonging to a discarded history.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.generator_job import TurnJob
from app.schemas.turn import TurnCreate


class TimelineConflict(RuntimeError):
    def __init__(self, message: str, *, revision: int | None = None) -> None:
        super().__init__(message)
        self.revision = revision


def lock_game_timeline(db: Session, game_id: UUID) -> Game | None:
    """Refresh and lock only the game row until the caller commits/rolls back."""
    return db.scalars(
        select(Game)
        .where(Game.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()


def assert_timeline_current(db: Session, game_id: UUID, generation: int) -> Game:
    game = lock_game_timeline(db, game_id)
    if game is None or (game.timeline_generation or 0) != generation:
        raise TimelineConflict("游戏进度已读档、回退或重开，此任务已失效。")
    return game


def assert_expected_revision(game: Game, expected_revision: int | None) -> None:
    revision = game.revision or 0
    if expected_revision is not None and revision != expected_revision:
        raise TimelineConflict("游戏进度或设定已经改变，请刷新后再提交。", revision=revision)


def touch_game_revision(db: Session, game: Game) -> int:
    game.revision = (game.revision or 0) + 1
    db.add(game)
    return game.revision


def advance_timeline(db: Session, game: Game) -> None:
    """Caller holds the game lock. Fence late writers in the same transaction."""
    game.timeline_generation = (game.timeline_generation or 0) + 1
    touch_game_revision(db, game)
    now = datetime.now(UTC)
    jobs = db.scalars(
        select(TurnJob).where(
            TurnJob.game_id == game.id,
            TurnJob.timeline_generation < game.timeline_generation,
            (
                TurnJob.status.in_(("pending", "running"))
                | TurnJob.maintenance_status.in_(("pending", "running"))
            ),
        )
    ).all()
    for job in jobs:
        message = "游戏时间线已改变，此任务已失效。"
        if job.status in {"pending", "running"}:
            job.status = "failed"
            job.error_message = message
            job.progress_message = message
            job.completed_at = now
        job.maintenance_status = "skipped"
        job.maintenance_message = message
        job.maintenance_completed_at = now
        job.last_event_at = now
        job.event_seq = (job.event_seq or 0) + 1
        db.add(job)


def request_digest(payload: TurnCreate) -> str:
    # request_id identifies the request; the rest is its immutable content.
    body = payload.model_dump(mode="json", exclude={"request_id"})
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def replay_turn_request(db: Session, game: Game, payload: TurnCreate) -> TurnJob | None:
    if payload.request_id is None:
        return None
    job = db.scalars(
        select(TurnJob).where(
            TurnJob.game_id == game.id,
            TurnJob.request_id == payload.request_id,
        )
    ).first()
    if job is None:
        return None
    if job.request_hash != request_digest(payload):
        raise TimelineConflict("同一个 request_id 已用于不同的回合请求。")
    if job.timeline_generation != (game.timeline_generation or 0):
        raise TimelineConflict("该请求属于已读档、回退或重开的旧进度，请刷新后重新行动。")
    return job


def admit_turn_request(db: Session, game: Game, payload: TurnCreate) -> TurnJob:
    """Caller holds the game row lock and has checked blockers/replays."""
    assert_expected_revision(game, payload.expected_revision)
    if game.status in {"completed", "defeated"}:
        raise TimelineConflict("本局已经结束，请先读档或重开后继续行动。")
    revision = touch_game_revision(db, game)
    job = TurnJob(
        game_id=game.id,
        status="pending",
        request_json=payload.model_dump(mode="json"),
        request_id=payload.request_id,
        request_hash=request_digest(payload) if payload.request_id is not None else None,
        game_revision=revision,
        timeline_generation=game.timeline_generation or 0,
        maintenance_status="pending",
        maintenance_stage="state_extract",
        maintenance_message="等待回合生成完成后执行状态维护。",
    )
    db.add(job)
    db.flush()
    return job


def clean_replay_seed(value: dict[str, Any]) -> dict[str, Any]:
    """Remove legacy ending-writer pollution only from the replay baseline.

    Live/save state is deliberately never passed through this function: an
    actual finished game must retain its ending and epilogue.
    """
    seed = deepcopy(value)
    projections = [seed]
    if isinstance(seed.get("v2"), dict):
        projections.append(seed["v2"])
    for projection in projections:
        progress = projection.get("story_progress")
        if isinstance(progress, dict):
            for key, default in (("epilogue", ""), ("campaign_complete", False), ("defeat", False)):
                if progress.get(key):
                    progress[key] = default
    return seed


def config_digest(game: Game) -> str:
    story = game.config.story_settings if game.config is not None else {}
    encoded = json.dumps(story, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
