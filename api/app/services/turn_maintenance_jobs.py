import asyncio
import logging
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.generator_job import TurnJob
from app.models.turn import Turn
from app.services.agent_traces import set_trace_context
from app.services.characters import sync_characters_from_game
from app.services.context_compressor import ContextCompressor
from app.services.deepseek_client import DeepSeekError
from app.services.epilogue_generator import EpilogueGenerator
from app.services.game_activity import touch_game
from app.services.gameplay import gameplay_game_query
from app.services.state_extractor import StateExtractor, StateExtractorValidationError
from app.services.state_rebuilder import approve_turn_state_delta, rebuild_game_state
from app.services.state_settlement import record_failed_turn_state_delta
from app.services.state_v2 import state_v2_view
from app.services.story_settings import build_runtime_story
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

    # B1 结局闭环：末幕打通后生成尾声并置 game.status=completed（幂等、独立 fallback）。
    await _finalize_campaign_if_complete(job_id)

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
        job.extractor_failed = False
        if game.state is not None:
            approve_turn_state_delta(
                db,
                game=game,
                turn=turn,
                delta_json=delta_json,
                approved_at=datetime.now(UTC),
            )
            rebuild_game_state(db, game)
            sync_characters_from_game(db, game, commit=False)
        db.add(job)
        db.add(turn)
        touch_game(db, game.id)
        db.commit()


async def _finalize_campaign_if_complete(job_id: UUID) -> None:
    """末幕打通则生成 epilogue 并置 game.status=completed。

    幂等：game.status 已是 completed 或 campaign_complete 未置时直接返回。
    epilogue 生成失败/超时返回空串，此时仅置状态、不写尾声正文（前端展示 fallback）。
    LLM 调用放在 session 之外，避免长事务占用连接。
    """
    context = _load_campaign_completion_context(job_id)
    if context is None:
        return
    try:
        epilogue = await EpilogueGenerator().generate(context["payload"])
    except Exception:
        logger.exception("Epilogue generation crashed for job %s", job_id)
        epilogue = ""
    _persist_campaign_completion(context["game_id"], epilogue)
    publish_turn_job_snapshot(job_id)


def _load_campaign_completion_context(job_id: UUID) -> dict[str, Any] | None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None or job.turn_id is None:
            return None
        game = db.scalars(gameplay_game_query(job.game_id)).first()
        if game is None or game.state is None or game.status == "completed":
            return None
        state_json = game.state.state_json or {}
        progress = state_json.get("story_progress")
        if not (isinstance(progress, dict) and progress.get("campaign_complete")):
            return None

        runtime_story = build_runtime_story(game.config, state_json)
        view = state_v2_view(state_json)
        recent = db.scalars(
            select(Turn)
            .where(Turn.game_id == game.id)
            .order_by(Turn.turn_number.desc())
            .limit(8)
        ).all()
        payload = {
            "game": {
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
            },
            "worldview": runtime_story.get("worldview"),
            "story_core": runtime_story.get("story_core"),
            "completed_acts": progress.get("completed_acts", []),
            "protagonist": view.get("protagonist_sheet"),
            "key_relationships": [
                {
                    "npc": rel.get("npc"),
                    "stage": rel.get("stage"),
                    "attitude": rel.get("attitude") or rel.get("relationship"),
                }
                for rel in (view.get("relationship_tracks") or [])
            ][:8],
            "recent_choices": [
                {"turn": turn.turn_number, "player_input": turn.player_input}
                for turn in reversed(recent)
            ],
        }
        return {"game_id": game.id, "payload": payload}


def _persist_campaign_completion(game_id: Any, epilogue: str) -> None:
    with SessionLocal() as db:
        game = db.scalars(gameplay_game_query(game_id)).first()
        if game is None or game.state is None or game.status == "completed":
            return
        game.status = "completed"
        if epilogue:
            # 写入 live state（即时展示）+ initial_state（rebuild 重放时保留，
            # 尾声不随 delta 重算）。JSONB 需整体重新赋值，SQLAlchemy 才能侦测到嵌套变更。
            game.state.state_json = _with_epilogue(game.state.state_json, epilogue)
            game.state.initial_state_json = _with_epilogue(
                game.state.initial_state_json, epilogue
            )
        db.add(game)
        db.add(game.state)
        touch_game(db, game.id)
        db.commit()


def _with_epilogue(state_json: Any, epilogue: str) -> dict[str, Any]:
    base = deepcopy(state_json) if isinstance(state_json, dict) else {}
    progress = base.setdefault("story_progress", {})
    if not isinstance(progress, dict):
        progress = {}
        base["story_progress"] = progress
    progress["epilogue"] = epilogue
    progress["campaign_complete"] = True
    return base


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
