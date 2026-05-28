import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.generator_job import TurnJob
from app.models.turn import Turn
from app.services.agent_traces import set_trace_context
from app.services.context_compressor import ContextCompressor
from app.services.deepseek_client import DeepSeekError
from app.services.game_activity import touch_game
from app.services.gameplay import gameplay_game_query
from app.services.state_extractor import StateExtractor, StateExtractorValidationError
from app.services.state_rebuilder import approve_turn_state_delta, rebuild_game_state
from app.services.state_settlement import record_failed_turn_state_delta
from app.services.turn_jobs import publish_turn_job_snapshot

logger = logging.getLogger(__name__)

TURN_MAINTENANCE_TIMEOUT_SECONDS = 10 * 60
MEMORY_SUMMARY_INTERVAL_TURNS = 4


async def run_turn_maintenance_job(job_id: UUID) -> None:
    # maintenance trace 也归到原 turn job 下，便于在 trace 视图里看到完整一回合的所有 LLM 调用。
    set_trace_context("turn", job_id)
    if not _mark_maintenance_running(
        job_id,
        stage="state_extract",
        message="正在提取状态变更。",
    ):
        return

    try:
        delta_json = await _extract_delta(job_id)
    except (DeepSeekError, StateExtractorValidationError, ValueError) as exc:
        logger.warning("Turn maintenance state extraction failed for job %s: %s", job_id, exc)
        _record_failed_delta(job_id, str(exc))
        _mark_extractor_failed(job_id)
        _mark_maintenance_terminal(
            job_id,
            status="failed",
            stage="state_extract",
            message="状态提取失败，系统会在下次继续前自动重试。",
            error=str(exc),
        )
        return
    except Exception as exc:
        logger.exception("Unexpected turn maintenance failure for job %s", job_id)
        _record_failed_delta(job_id, f"{type(exc).__name__}: {exc}")
        _mark_extractor_failed(job_id)
        _mark_maintenance_terminal(
            job_id,
            status="failed",
            stage="state_extract",
            message="状态维护失败，系统会在下次继续前自动重试。",
            error=f"{type(exc).__name__}: {exc}",
        )
        return

    if not _is_current_maintenance_stage(job_id, "state_extract"):
        logger.info(
            "Turn maintenance job %s stopped because state_extract is no longer active.",
            job_id,
        )
        return

    _apply_delta(job_id, delta_json)

    if not _should_update_memory(job_id):
        _mark_maintenance_terminal(
            job_id,
            status="skipped",
            stage="completed",
            message=f"状态已更新，记忆摘要延后到每 {MEMORY_SUMMARY_INTERVAL_TURNS} 回合批量维护。",
            error=None,
        )
        return

    _update_maintenance_progress(
        job_id,
        stage="memory_summary",
        message="状态已更新，正在批量维护记忆摘要。",
    )
    try:
        await _update_memory_summary(job_id, delta_json)
    except Exception as exc:
        logger.warning("Turn maintenance memory summary failed for job %s: %s", job_id, exc)
        _mark_maintenance_terminal(
            job_id,
            status="failed",
            stage="memory_summary",
            message="状态已更新，但记忆摘要维护失败，下一回合仍可继续。",
            error=str(exc),
        )
        return

    _mark_maintenance_terminal(
        job_id,
        status="completed",
        stage="completed",
        message="状态提取与记忆摘要已完成。",
        error=None,
    )


async def _extract_delta(job_id: UUID) -> dict[str, Any]:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None or job.turn_id is None:
            raise ValueError("Turn job not found or turn has not been persisted.")
        game = db.scalars(gameplay_game_query(job.game_id)).first()
        turn = db.get(Turn, job.turn_id)
        if game is None or turn is None:
            raise ValueError("Game or turn not found.")
        runtime_inputs = job.turn_runtime_inputs or {}

    director_decision = runtime_inputs.get("director_decision") if isinstance(
        runtime_inputs, dict
    ) else None
    drift_findings = runtime_inputs.get("drift_validation") if isinstance(
        runtime_inputs, dict
    ) else None
    return await StateExtractor().extract(
        game,
        turn,
        director_decision=director_decision,
        drift_findings=drift_findings,
    )


def _apply_delta(job_id: UUID, delta_json: dict[str, Any]) -> None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None or job.turn_id is None:
            return
        game = db.scalars(gameplay_game_query(job.game_id)).first()
        turn = db.get(Turn, job.turn_id)
        if game is None or turn is None:
            return

        turn.state_delta_json = delta_json
        if game.state is not None:
            approve_turn_state_delta(
                db,
                game=game,
                turn=turn,
                delta_json=delta_json,
                approved_at=datetime.now(UTC),
            )
            rebuild_game_state(db, game)
        db.add(turn)
        touch_game(db, game.id)
        db.commit()


def _mark_extractor_failed(job_id: UUID) -> None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return
        job.extractor_failed = True
        db.add(job)
        db.commit()


def _record_failed_delta(job_id: UUID, error: str) -> None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None or job.turn_id is None:
            return
        game = db.scalars(gameplay_game_query(job.game_id)).first()
        turn = db.get(Turn, job.turn_id)
        if game is None or turn is None:
            return
        record_failed_turn_state_delta(db, game=game, turn=turn, error=error)
        rebuild_game_state(db, game)
        touch_game(db, game.id)
        db.commit()


def _should_update_memory(job_id: UUID) -> bool:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None or job.turn_id is None:
            return False
        turn_number = db.scalar(select(Turn.turn_number).where(Turn.id == job.turn_id))
    return bool(turn_number and turn_number % MEMORY_SUMMARY_INTERVAL_TURNS == 0)


def _is_current_maintenance_stage(job_id: UUID, stage: str) -> bool:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return False
        return job.maintenance_status == "running" and job.maintenance_stage == stage


async def _update_memory_summary(job_id: UUID, delta_json: dict[str, Any]) -> None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None or job.turn_id is None:
            return
        game = db.scalars(gameplay_game_query(job.game_id)).first()
        turn = db.get(Turn, job.turn_id)
        if game is None or turn is None:
            return
        await asyncio.wait_for(
            ContextCompressor().update_after_turn(db, game, turn, delta_json),
            timeout=TURN_MAINTENANCE_TIMEOUT_SECONDS,
        )


def _mark_maintenance_running(job_id: UUID, *, stage: str, message: str) -> bool:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return False
        now = datetime.now(UTC)
        job.maintenance_status = "running"
        job.maintenance_stage = stage
        job.maintenance_message = message
        job.maintenance_error = None
        job.maintenance_started_at = job.maintenance_started_at or now
        job.maintenance_completed_at = None
        job.last_event_at = now
        db.add(job)
        db.commit()
    publish_turn_job_snapshot(job_id)
    return True


def _update_maintenance_progress(job_id: UUID, *, stage: str, message: str) -> None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return
        now = datetime.now(UTC)
        job.maintenance_stage = stage
        job.maintenance_message = message
        job.last_event_at = now
        db.add(job)
        db.commit()
    publish_turn_job_snapshot(job_id)


def _mark_maintenance_terminal(
    job_id: UUID,
    *,
    status: str,
    stage: str,
    message: str,
    error: str | None,
) -> None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return
        now = datetime.now(UTC)
        job.maintenance_status = status
        job.maintenance_stage = stage
        job.maintenance_message = message
        job.maintenance_error = error[:4000] if error else None
        job.maintenance_completed_at = now
        job.last_event_at = now
        db.add(job)
        db.commit()
    publish_turn_job_snapshot(job_id)
