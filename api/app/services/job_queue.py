from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import SessionLocal, dispose_db_connections
from app.models.generator_job import GeneratorChatJob, GeneratorFinalizeJob, TurnJob
from app.services.generator_chat_jobs import CHAT_JOB_TIMEOUT_SECONDS, run_chat_job
from app.services.generator_jobs import FINALIZE_JOB_TIMEOUT_SECONDS, run_finalize_job
from app.services.turn_jobs import TURN_JOB_TIMEOUT_SECONDS, run_turn_job
from app.services.turn_maintenance_jobs import (
    TURN_MAINTENANCE_TIMEOUT_SECONDS,
    run_turn_maintenance_job,
)

logger = logging.getLogger(__name__)
QUEUE_NAME = "rpgforge"
ACTIVE_STATUSES = ("pending", "running")
FAILED_RQ_STATUSES = {"failed", "stopped", "canceled"}
PENDING_MISSING_GRACE_SECONDS = 10


def redis_connection() -> Redis:
    return Redis.from_url(settings.redis_url)


def rpgforge_queue(connection: Redis | None = None) -> Queue:
    return Queue(QUEUE_NAME, connection=connection or redis_connection())


def rq_job_id(kind: str, job_id: UUID) -> str:
    return f"{kind}-{job_id}"


def enqueue_turn_job(job_id: UUID) -> None:
    _enqueue_job("turn", job_id, run_turn_job_sync, TURN_JOB_TIMEOUT_SECONDS + 90)


def enqueue_turn_maintenance_job(job_id: UUID) -> None:
    _enqueue_job(
        "turn-maintenance",
        job_id,
        run_turn_maintenance_job_sync,
        TURN_MAINTENANCE_TIMEOUT_SECONDS + 90,
    )


def enqueue_chat_job(job_id: UUID) -> None:
    _enqueue_job("chat", job_id, run_chat_job_sync, CHAT_JOB_TIMEOUT_SECONDS + 90)


def enqueue_finalize_job(job_id: UUID) -> None:
    _enqueue_job("finalize", job_id, run_finalize_job_sync, FINALIZE_JOB_TIMEOUT_SECONDS + 90)


def run_turn_job_sync(job_id: str) -> None:
    dispose_db_connections()
    asyncio.run(run_turn_job(UUID(job_id)))


def run_turn_maintenance_job_sync(job_id: str) -> None:
    dispose_db_connections()
    asyncio.run(run_turn_maintenance_job(UUID(job_id)))


def run_chat_job_sync(job_id: str) -> None:
    dispose_db_connections()
    asyncio.run(run_chat_job(UUID(job_id)))


def run_finalize_job_sync(job_id: str) -> None:
    dispose_db_connections()
    asyncio.run(run_finalize_job(UUID(job_id)))


def recover_stale_jobs(connection: Redis | None = None) -> dict[str, int]:
    redis = connection or redis_connection()
    now = datetime.now(UTC)
    counts = {
        "running_timeout": 0,
        "pending_missing": 0,
    }

    with SessionLocal() as db:
        running_jobs = (
            ("turn", TurnJob, TURN_JOB_TIMEOUT_SECONDS),
            ("chat", GeneratorChatJob, CHAT_JOB_TIMEOUT_SECONDS),
            ("finalize", GeneratorFinalizeJob, FINALIZE_JOB_TIMEOUT_SECONDS),
        )
        for _kind, model, timeout_seconds in running_jobs:
            for job in db.scalars(select(model).where(model.status == "running")).all():
                anchor = (
                    job.last_event_at
                    or job.stream_started_at
                    or job.updated_at
                    or job.created_at
                )
                if _age_seconds(anchor, now) <= timeout_seconds:
                    continue
                _mark_stale_failed(
                    job,
                    "任务执行超过超时阈值，已标记失败。请重新发起。",
                    now,
                )
                counts["running_timeout"] += 1

        pending_jobs = (
            ("turn", TurnJob),
            ("chat", GeneratorChatJob),
            ("finalize", GeneratorFinalizeJob),
        )
        for kind, model in pending_jobs:
            for job in db.scalars(select(model).where(model.status == "pending")).all():
                if _rq_job_exists(redis, rq_job_id(kind, job.id)):
                    continue
                _mark_stale_failed(
                    job,
                    "任务仍在等待，但队列中已找不到对应任务。请重新发起。",
                    now,
                )
                counts["pending_missing"] += 1

        for job in db.scalars(
            select(TurnJob).where(
                TurnJob.status == "completed",
                TurnJob.maintenance_status == "running",
            )
        ).all():
            anchor = job.last_event_at or job.maintenance_started_at or job.updated_at
            if _age_seconds(anchor, now) <= TURN_MAINTENANCE_TIMEOUT_SECONDS:
                continue
            _mark_stale_maintenance_failed(
                job,
                "状态维护执行超过超时阈值，已标记失败。下一回合仍可继续。",
                now,
            )
            counts["maintenance_timeout"] = counts.get("maintenance_timeout", 0) + 1

        for job in db.scalars(
            select(TurnJob).where(
                TurnJob.status == "completed",
                TurnJob.maintenance_status == "pending",
            )
        ).all():
            if _rq_job_exists(redis, rq_job_id("turn-maintenance", job.id)):
                continue
            _mark_stale_maintenance_failed(
                job,
                "状态维护仍在等待，但队列中已找不到对应任务。下一回合仍可继续。",
                now,
            )
            counts["maintenance_pending_missing"] = (
                counts.get("maintenance_pending_missing", 0) + 1
            )

        db.commit()

    return counts


def reconcile_turn_job_liveness(
    db: Session,
    job: TurnJob,
    connection: Redis | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    if job.status not in ACTIVE_STATUSES:
        return False

    checked_at = now or datetime.now(UTC)
    anchor = job.last_event_at or job.stream_started_at or job.updated_at or job.created_at
    if _age_seconds(anchor, checked_at) > TURN_JOB_TIMEOUT_SECONDS:
        _mark_stale_failed(
            job,
            "回合任务执行超过超时阈值，已标记失败。请重新发起。",
            checked_at,
        )
        db.add(job)
        return True

    if (
        job.status == "pending"
        and _age_seconds(job.created_at, checked_at) <= PENDING_MISSING_GRACE_SECONDS
    ):
        return False

    redis = connection or redis_connection()
    rq_status = _rq_job_status(redis, rq_job_id("turn", job.id))
    if rq_status == "missing":
        _mark_stale_failed(
            job,
            "任务队列中已找不到对应回合任务，已标记失败。请重新发起。",
            checked_at,
        )
        db.add(job)
        return True

    if rq_status in FAILED_RQ_STATUSES:
        _mark_stale_failed(
            job,
            f"任务队列已将回合任务标记为 {rq_status}，已解除阻塞。请重新发起。",
            checked_at,
        )
        db.add(job)
        return True

    return False


def _enqueue_job(kind: str, job_id: UUID, func, timeout_seconds: int) -> None:
    queue = rpgforge_queue()
    queue.enqueue_call(
        func=func,
        args=(str(job_id),),
        job_id=rq_job_id(kind, job_id),
        timeout=timeout_seconds,
        result_ttl=3600,
        failure_ttl=86400,
    )


def _rq_job_exists(connection: Redis, job_id: str) -> bool:
    return _rq_job_status(connection, job_id) != "missing"


def _rq_job_status(connection: Redis, job_id: str) -> str:
    try:
        status_value = Job.fetch(job_id, connection=connection).get_status(refresh=True)
    except NoSuchJobError:
        return "missing"
    except RedisError as exc:
        logger.warning("Unable to inspect Redis job %s: %s", job_id, exc)
        return "unknown"
    return _normalize_rq_status(status_value)


def _normalize_rq_status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw).rsplit(".", maxsplit=1)[-1].lower()


def _age_seconds(value: datetime | None, now: datetime) -> float:
    if value is None:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return (now - value).total_seconds()


def _mark_stale_failed(job, message: str, now: datetime) -> None:
    job.status = "failed"
    job.error_message = message
    job.progress_message = message
    if isinstance(job, TurnJob):
        job.maintenance_status = "failed"
        job.maintenance_message = message
        job.maintenance_error = message
        job.maintenance_completed_at = now
    job.last_event_at = now
    job.completed_at = now


def _mark_stale_maintenance_failed(job: TurnJob, message: str, now: datetime) -> None:
    job.maintenance_status = "failed"
    job.maintenance_message = message
    job.maintenance_error = message
    job.maintenance_completed_at = now
    job.last_event_at = now
