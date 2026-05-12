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

from app.config import settings
from app.db.session import SessionLocal
from app.models.generator_job import GeneratorChatJob, GeneratorFinalizeJob, TurnJob
from app.services.generator_chat_jobs import CHAT_JOB_TIMEOUT_SECONDS, run_chat_job
from app.services.generator_jobs import FINALIZE_JOB_TIMEOUT_SECONDS, run_finalize_job
from app.services.turn_jobs import TURN_JOB_TIMEOUT_SECONDS, run_turn_job

logger = logging.getLogger(__name__)
QUEUE_NAME = "rpgforge"
ACTIVE_STATUSES = ("pending", "running")


def redis_connection() -> Redis:
    return Redis.from_url(settings.redis_url)


def rpgforge_queue(connection: Redis | None = None) -> Queue:
    return Queue(QUEUE_NAME, connection=connection or redis_connection())


def rq_job_id(kind: str, job_id: UUID) -> str:
    return f"{kind}:{job_id}"


def enqueue_turn_job(job_id: UUID) -> None:
    _enqueue_job("turn", job_id, run_turn_job_sync, TURN_JOB_TIMEOUT_SECONDS + 90)


def enqueue_chat_job(job_id: UUID) -> None:
    _enqueue_job("chat", job_id, run_chat_job_sync, CHAT_JOB_TIMEOUT_SECONDS + 90)


def enqueue_finalize_job(job_id: UUID) -> None:
    _enqueue_job("finalize", job_id, run_finalize_job_sync, FINALIZE_JOB_TIMEOUT_SECONDS + 90)


def run_turn_job_sync(job_id: str) -> None:
    asyncio.run(run_turn_job(UUID(job_id)))


def run_chat_job_sync(job_id: str) -> None:
    asyncio.run(run_chat_job(UUID(job_id)))


def run_finalize_job_sync(job_id: str) -> None:
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

        db.commit()

    return counts


def _enqueue_job(kind: str, job_id: UUID, func, timeout_seconds: int) -> None:
    queue = rpgforge_queue()
    queue.enqueue_call(
        func=func,
        args=(str(job_id),),
        job_id=rq_job_id(kind, job_id),
        job_timeout=timeout_seconds,
        result_ttl=3600,
        failure_ttl=86400,
    )


def _rq_job_exists(connection: Redis, job_id: str) -> bool:
    try:
        Job.fetch(job_id, connection=connection)
        return True
    except NoSuchJobError:
        return False
    except RedisError as exc:
        logger.warning("Unable to inspect Redis job %s: %s", job_id, exc)
        return True


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
    job.last_event_at = now
    job.completed_at = now
