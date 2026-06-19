import asyncio
import logging
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.generator_job import TurnJob
from app.models.turn import Turn
from app.schemas.turn import GMRuntimeOutput
from app.services.agent_traces import set_trace_context
from app.services.characters import sync_characters_from_game
from app.services.context_compressor import ContextCompressor
from app.services.deepseek_client import DeepSeekError
from app.services.drift_validator import DriftValidator
from app.services.epilogue_generator import EpilogueGenerator
from app.services.game_activity import touch_game
from app.services.gameplay import gameplay_game_query
from app.services.state_extractor import StateExtractor, StateExtractorValidationError
from app.services.state_rebuilder import approve_turn_state_delta, rebuild_game_state
from app.services.state_settlement import record_failed_turn_state_delta
from app.services.state_v2 import state_v2_view
from app.services.story_director import StoryDirectorDecision
from app.services.story_settings import build_runtime_story
from app.services.turn_jobs import publish_turn_job_snapshot

logger = logging.getLogger(__name__)

TURN_MAINTENANCE_TIMEOUT_SECONDS = 10 * 60
MEMORY_SUMMARY_INTERVAL_TURNS = 4
# 偏离审计稀疏采样：只为趋势监控（剧透安全已由同步整串门负责），不必每回合烧一次 Flash。
DRIFT_AUDIT_INTERVAL_TURNS = 3


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

    # 偏离校验改异步事后审计（Round 46）：在 _apply_delta 之前跑，用 pre-turn state 审计本回合
    # 输出（与旧同步链一致，避免幕转换回合用已推进的新幕 state 误判）；observe-only、稀疏采样、
    # 失败只记日志、不影响维护。回填 drift_severity 供 admin 看板监控"去同步控制后跑偏趋势"。
    await _audit_drift(job_id)

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

        # A3：把本回合行动判定结果并入 delta 并持久化，让 survival_clock 据失败侵蚀危机条，
        # 且 rebuild 重放时可复现（action_outcome 随 turn.state_delta_json / StateDelta 落库）。
        runtime_inputs = job.turn_runtime_inputs or {}
        action_outcome = (
            runtime_inputs.get("action_outcome") if isinstance(runtime_inputs, dict) else None
        )
        if isinstance(action_outcome, dict) and action_outcome:
            delta_json = {**delta_json, "action_outcome": action_outcome}

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


# B1 胜利 / A3 失败 两种结局对应的终态 game.status。
_ENDED_STATUSES = {"completed", "defeated"}
_ENDING_STATUS = {"victory": "completed", "defeat": "defeated"}


async def _finalize_campaign_if_complete(job_id: UUID) -> None:
    """打通末幕（胜利）或危机条归零（失败）则生成结局并置终态 game.status。

    幂等：game.status 已是终态、或两种结局标记都未置时直接返回。
    结局生成失败/超时返回空串，此时仅置状态、不写结局正文（前端展示 fallback）。
    LLM 调用放在 session 之外，避免长事务占用连接。
    """
    context = _load_campaign_ending_context(job_id)
    if context is None:
        return
    try:
        epilogue = await EpilogueGenerator().generate(context["payload"])
    except Exception:
        logger.exception("Ending generation crashed for job %s", job_id)
        epilogue = ""
    _persist_campaign_ending(context["game_id"], epilogue, context["status"])
    publish_turn_job_snapshot(job_id)


def _load_campaign_ending_context(job_id: UUID) -> dict[str, Any] | None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None or job.turn_id is None:
            return None
        game = db.scalars(gameplay_game_query(job.game_id)).first()
        if game is None or game.state is None or game.status in _ENDED_STATUSES:
            return None
        state_json = game.state.state_json or {}
        progress = state_json.get("story_progress")
        if not isinstance(progress, dict):
            return None
        # 胜利优先于失败（同回合既满足末幕完成又危机归零时，按通关处理）。
        if progress.get("campaign_complete"):
            ending_type = "victory"
        elif progress.get("defeat"):
            ending_type = "defeat"
        else:
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
            "ending_type": ending_type,
            "game": {
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
            },
            "worldview": runtime_story.get("worldview"),
            "story_core": runtime_story.get("story_core"),
            "completed_acts": progress.get("completed_acts", []),
            "current_act": runtime_story.get("current_act"),
            "protagonist": view.get("protagonist_sheet"),
            "crisis": state_json.get("crisis"),
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
        return {
            "game_id": game.id,
            "payload": payload,
            "status": _ENDING_STATUS[ending_type],
        }


def _persist_campaign_ending(game_id: Any, epilogue: str, status: str) -> None:
    with SessionLocal() as db:
        game = db.scalars(gameplay_game_query(game_id)).first()
        if game is None or game.state is None or game.status in _ENDED_STATUSES:
            return
        game.status = status
        if epilogue:
            # 写入 live state（即时展示）+ initial_state（rebuild 重放时保留，
            # 结局不随 delta 重算）。JSONB 需整体重新赋值，SQLAlchemy 才能侦测到嵌套变更。
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


async def _audit_drift(job_id: UUID) -> None:
    """异步事后偏离审计（observe-only）：回填 drift_severity，不触发任何重写。

    专门用来监控"去掉同步 drift 控制后跑偏有没有变严重"。LLM 调用在 session 之外（game/config/
    state 经 selectinload eager-load，detach 后访问已加载列安全）。任何失败只记日志、不影响维护。
    """
    try:
        context = _load_drift_audit_context(job_id)
        if context is None:
            return
        result = await DriftValidator().validate(
            game=context["game"],
            player_input=context["player_input"],
            recent_turns=context["recent_turns"],
            director_decision=context["director_decision"],
            runtime_output=context["runtime_output"],
        )
        _persist_drift_audit(job_id, result.severity, result.model_dump())
    except Exception:
        logger.exception("Async drift audit failed for job %s", job_id)


def _load_drift_audit_context(job_id: UUID) -> dict[str, Any] | None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None or job.turn_id is None:
            return None
        turn = db.get(Turn, job.turn_id)
        if turn is None:
            return None
        # 稀疏采样：只取首回合与每 DRIFT_AUDIT_INTERVAL_TURNS 回合做趋势监控，省 Flash 成本。
        if not (turn.turn_number == 1 or turn.turn_number % DRIFT_AUDIT_INTERVAL_TURNS == 0):
            return None
        game = db.scalars(gameplay_game_query(job.game_id)).first()
        if game is None or game.state is None:
            return None
        # GMRuntimeOutput 需正好 4 个 A/B/C/D 选项；重建失败说明数据异常，跳过审计。
        try:
            runtime_output = GMRuntimeOutput.model_validate(
                {
                    "narrative": turn.gm_output,
                    "visible_clues": [
                        line for line in (turn.visible_summary or "").split("\n") if line.strip()
                    ],
                    "action_options": turn.action_options_json or [],
                }
            )
        except (ValidationError, ValueError):
            return None
        runtime_inputs = (
            job.turn_runtime_inputs if isinstance(job.turn_runtime_inputs, dict) else {}
        )
        director_raw = runtime_inputs.get("director_decision")
        try:
            director_decision = (
                StoryDirectorDecision.model_validate(director_raw)
                if isinstance(director_raw, dict)
                else StoryDirectorDecision()
            )
        except ValidationError:
            director_decision = StoryDirectorDecision()
        recent = db.scalars(
            select(Turn)
            .where(Turn.game_id == game.id, Turn.turn_number < turn.turn_number)
            .order_by(Turn.turn_number.desc())
            .limit(6)
        ).all()
        return {
            "game": game,
            "player_input": turn.player_input,
            "recent_turns": list(reversed(recent)),
            "director_decision": director_decision,
            "runtime_output": runtime_output,
        }


def _persist_drift_audit(job_id: UUID, severity: str, validation: dict[str, Any]) -> None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return
        job.drift_severity = severity
        runtime_inputs = (
            dict(job.turn_runtime_inputs) if isinstance(job.turn_runtime_inputs, dict) else {}
        )
        runtime_inputs["drift_validation"] = validation
        job.turn_runtime_inputs = runtime_inputs
        db.add(job)
        db.commit()
    publish_turn_job_snapshot(job_id)


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
