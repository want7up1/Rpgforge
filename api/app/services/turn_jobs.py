import asyncio
import logging
from datetime import UTC, datetime
from time import monotonic
from typing import TypedDict
from uuid import UUID

from pydantic import ValidationError

from app.db.session import SessionLocal
from app.models.generator_job import TurnJob
from app.models.turn import Turn
from app.schemas.turn import TurnCreate, TurnJobRead
from app.services.agent_traces import set_trace_context
from app.services.deepseek_client import DeepSeekError
from app.services.gameplay import GameplayService, GameplayValidationError, gameplay_game_query
from app.services.turn_stream_events import turn_stream_event_broker

# 单回合最坏情况：Director(90s) + GM 首次(360s) + Validator(90s) + GM 重写(360s) = 900s。
# 加上 prepare/retrieve/persist 的 IO 开销，整体 18 min 留余量。
TURN_JOB_TIMEOUT_SECONDS = 18 * 60
STREAM_WRITE_INTERVAL_SECONDS = 0.8
STREAM_WRITE_MIN_CHARS = 512
logger = logging.getLogger(__name__)
TURN_JOB_STAGES: tuple[tuple[str, str], ...] = (
    ("prepare_context", "准备上下文"),
    ("retrieve_memory", "检索资料"),
    ("story_director", "剧情导演"),
    ("gm_runtime", "剧情生成"),
    ("drift_validation", "偏离校验"),
    ("persist_turn", "写入回合"),
    ("completed", "完成"),
)
TURN_JOB_STAGE_LABELS = dict(TURN_JOB_STAGES)
TURN_JOB_STAGE_INDEXES = {
    stage: index for index, (stage, _label) in enumerate(TURN_JOB_STAGES, start=1)
}
TURN_JOB_STAGE_TOTAL = len(TURN_JOB_STAGES)


class StreamState(TypedDict):
    reasoning: str
    content: str
    narrative: str
    model: str | None
    stage: str
    stage_started_at: datetime | None


async def run_turn_job(job_id: UUID) -> None:
    # 设置 trace contextvar，让 ModelRouter 知道当前 LLM 调用归属哪个回合。
    set_trace_context("turn", job_id)
    stream_state: StreamState = {
        "reasoning": "",
        "content": "",
        "narrative": "",
        "model": None,
        "stage": "prepare_context",
        "stage_started_at": None,
    }

    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return
        now = datetime.now(UTC)
        job.status = "running"
        job.error_message = None
        job.reasoning_content = ""
        job.content_buffer = ""
        job.narrative_buffer = ""
        job.progress_message = "正在准备剧情上下文与导演决策..."
        _set_job_stage(job, "prepare_context", now)
        stream_state["stage_started_at"] = job.stage_started_at
        job.stream_started_at = now
        job.last_event_at = now
        db.add(job)
        db.commit()

    try:
        last_saved_at = 0.0
        last_saved_reasoning_length = 0
        last_saved_content_length = 0
        last_saved_narrative_length = 0
        last_published_reasoning_length = 0
        last_published_content_length = 0

        async def on_update(reasoning: str, content: str, model: str | None) -> None:
            nonlocal last_saved_at
            nonlocal last_saved_content_length
            nonlocal last_saved_narrative_length
            nonlocal last_saved_reasoning_length
            nonlocal last_published_content_length
            nonlocal last_published_reasoning_length
            narrative = extract_partial_json_string_field(content, "narrative")
            stream_state["reasoning"] = reasoning
            stream_state["content"] = content
            stream_state["narrative"] = narrative
            stream_state["model"] = model
            reset_buffers = (
                len(reasoning) < last_published_reasoning_length
                or len(content) < last_published_content_length
            )

            _publish_turn_delta(
                job_id,
                status="running",
                reasoning_delta=(
                    reasoning if reset_buffers else reasoning[last_published_reasoning_length:]
                ),
                content_delta=content if reset_buffers else content[last_published_content_length:],
                reasoning_length=len(reasoning),
                content_length=len(content),
                narrative=narrative,
                model=model,
                message=_turn_progress_message(reasoning, content, narrative),
                stage=stream_state["stage"],
                stage_started_at=stream_state["stage_started_at"],
                reset_buffers=reset_buffers,
            )
            last_published_reasoning_length = len(reasoning)
            last_published_content_length = len(content)

            now_monotonic = monotonic()
            reasoning_delta = len(reasoning) - last_saved_reasoning_length
            content_delta = len(content) - last_saved_content_length
            narrative_delta = len(narrative) - last_saved_narrative_length
            should_save = (
                now_monotonic - last_saved_at >= STREAM_WRITE_INTERVAL_SECONDS
                or reasoning_delta >= STREAM_WRITE_MIN_CHARS
                or content_delta >= STREAM_WRITE_MIN_CHARS
                or narrative_delta >= 80
            )
            if not should_save:
                return

            last_saved_at = now_monotonic
            last_saved_reasoning_length = len(reasoning)
            last_saved_content_length = len(content)
            last_saved_narrative_length = len(narrative)
            _update_stream_progress(
                job_id,
                reasoning=reasoning,
                content=content,
                narrative=narrative,
                model=model,
                message=_turn_progress_message(reasoning, content, narrative),
                stage=stream_state["stage"],
                stage_started_at=stream_state["stage_started_at"],
                reset_buffers=reset_buffers,
            )

        async def on_stage(stage: str) -> None:
            _set_stream_stage(stream_state, stage)
            label = TURN_JOB_STAGE_LABELS.get(stage, "处理中")
            # 只 publish broker 给前端即时 stage 切换信号。DB 写入交给紧随其后的
            # on_progress 或 on_update，避免每次 stage 切换都打开一次 SessionLocal
            # 后又被 200ms 内的 on_progress 覆盖一次。
            _publish_turn_progress(
                job_id,
                status="running",
                message=f"进入阶段：{label}",
                model=stream_state["model"],
                reasoning_length=len(stream_state["reasoning"]),
                content_length=len(stream_state["content"]),
                narrative=stream_state["narrative"],
                stage=stream_state["stage"],
                stage_started_at=stream_state["stage_started_at"],
            )

        async def on_progress(message: str) -> None:
            _publish_turn_progress(
                job_id,
                status="running",
                message=message,
                model=stream_state["model"],
                reasoning_length=len(stream_state["reasoning"]),
                content_length=len(stream_state["content"]),
                narrative=stream_state["narrative"],
                stage=stream_state["stage"],
                stage_started_at=stream_state["stage_started_at"],
            )
            _update_progress_message(
                job_id,
                message=message,
                model=stream_state["model"],
                reasoning=stream_state["reasoning"],
                content=stream_state["content"],
                narrative=stream_state["narrative"],
                stage=stream_state["stage"],
                stage_started_at=stream_state["stage_started_at"],
            )

        service = GameplayService()
        with SessionLocal() as db:
            job = db.get(TurnJob, job_id)
            if job is None:
                return
            game = db.scalars(gameplay_game_query(job.game_id)).first()
            if game is None:
                _mark_job_failed(job_id, "Game not found.", stream_state)
                return
            request = TurnCreate.model_validate(job.request_json)
            context = await service.load_turn_runtime_context(
                db,
                game,
                request,
                on_progress=on_progress,
                on_stage=on_stage,
            )

        runtime_output, model_used = await asyncio.wait_for(
            service.generate_turn_runtime_output(
                context,
                on_update=on_update,
                on_progress=on_progress,
                on_stage=on_stage,
            ),
            timeout=TURN_JOB_TIMEOUT_SECONDS,
        )

        await on_stage("persist_turn")
        await on_progress("GM 回复已完成，正在写入回合。")
        with SessionLocal() as db:
            turn = service.persist_runtime_turn(
                db,
                game_id=context.game.id,
                player_input=context.player_input,
                runtime_output=runtime_output,
                model_used=model_used,
            )
    except TimeoutError:
        _mark_job_failed(
            job_id,
            f"回合生成超过 {TURN_JOB_TIMEOUT_SECONDS // 60} 分钟，已停止。请缩短输入或稍后重试。",
            stream_state,
        )
        return
    except (DeepSeekError, GameplayValidationError, ValidationError, ValueError) as exc:
        _mark_job_failed(job_id, str(exc), stream_state)
        return
    except Exception as exc:
        _mark_job_failed(job_id, f"{type(exc).__name__}: {exc}", stream_state)
        return

    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return
        now = datetime.now(UTC)
        job.status = "completed"
        job.turn_id = turn.id
        job.model_used = turn.model_used
        job.reasoning_content = stream_state["reasoning"]
        job.content_buffer = stream_state["content"]
        job.narrative_buffer = turn.gm_output
        job.progress_message = "剧情已生成，状态维护正在后台进行。"
        job.maintenance_status = "pending"
        job.maintenance_stage = "state_extract"
        job.maintenance_message = "等待后台状态维护任务。"
        job.maintenance_error = None
        job.maintenance_started_at = None
        job.maintenance_completed_at = None
        # 写入 telemetry，并把 director/drift 结果留给 maintenance 阶段的 StateExtractor。
        job.director_used_fallback = context.telemetry.director_used_fallback
        job.drift_severity = context.telemetry.drift_severity
        job.rewrite_triggered = context.telemetry.rewrite_triggered
        job.extractor_failed = False
        job.turn_runtime_inputs = context.telemetry.to_runtime_inputs() or None
        _set_job_stage(job, "completed", now)
        stream_state["stage"] = "completed"
        stream_state["stage_started_at"] = job.stage_started_at
        job.last_event_at = now
        job.completed_at = now
        db.add(job)
        db.commit()
        db.refresh(job)
        persisted_turn = db.get(Turn, turn.id)
        _publish_turn_snapshot(job, persisted_turn, event_type="completed", terminal=True)

    try:
        _enqueue_turn_maintenance_job(job_id)
    except Exception as exc:
        logger.warning("Unable to enqueue turn maintenance job %s: %s", job_id, exc)
        _mark_maintenance_failed(
            job_id,
            f"状态维护任务入队失败：{exc}",
            stage="state_extract",
        )



def _mark_job_failed(job_id: UUID, message: str, stream_state: StreamState) -> None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return
        now = datetime.now(UTC)
        job.status = "failed"
        job.error_message = message[:4000]
        job.reasoning_content = stream_state["reasoning"]
        job.content_buffer = stream_state["content"]
        job.narrative_buffer = stream_state["narrative"]
        job.progress_message = "剧情生成失败，已保留收到的流式内容。"
        job.maintenance_status = "failed"
        job.maintenance_message = "剧情生成失败，状态维护未执行。"
        job.maintenance_error = message[:4000]
        job.maintenance_completed_at = now
        _set_job_stage(job, stream_state["stage"], stream_state["stage_started_at"] or now)
        if stream_state["model"]:
            job.model_used = stream_state["model"]
        job.last_event_at = now
        job.completed_at = now
        db.add(job)
        db.commit()
        db.refresh(job)
        _publish_turn_snapshot(job, None, event_type="failed", terminal=True)


def _enqueue_turn_maintenance_job(job_id: UUID) -> None:
    from app.services.job_queue import enqueue_turn_maintenance_job

    enqueue_turn_maintenance_job(job_id)


def _mark_maintenance_failed(job_id: UUID, message: str, *, stage: str) -> None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return
        now = datetime.now(UTC)
        job.maintenance_status = "failed"
        job.maintenance_stage = stage
        job.maintenance_message = "状态维护失败，系统会在下次继续前自动重试。"
        job.maintenance_error = message[:4000]
        job.maintenance_completed_at = now
        job.last_event_at = now
        db.add(job)
        db.commit()
        db.refresh(job)
        turn = db.get(Turn, job.turn_id) if job.turn_id else None
        _publish_turn_snapshot(job, turn, event_type="progress", terminal=False)


def _update_stream_progress(
    job_id: UUID,
    *,
    reasoning: str,
    content: str,
    narrative: str,
    model: str | None,
    message: str,
    stage: str,
    stage_started_at: datetime | None,
    reset_buffers: bool,
) -> None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return
        job.reasoning_content = reasoning
        job.content_buffer = content
        job.narrative_buffer = narrative
        job.progress_message = message
        _set_job_stage(job, stage, stage_started_at or datetime.now(UTC))
        if model:
            job.model_used = model
        job.last_event_at = datetime.now(UTC)
        db.add(job)
        db.commit()


def _update_progress_message(
    job_id: UUID,
    *,
    message: str,
    model: str | None,
    reasoning: str,
    content: str,
    narrative: str,
    stage: str,
    stage_started_at: datetime | None,
) -> None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return
        job.reasoning_content = reasoning
        job.content_buffer = content
        job.narrative_buffer = narrative
        job.progress_message = message
        _set_job_stage(job, stage, stage_started_at or datetime.now(UTC))
        if model:
            job.model_used = model
        job.last_event_at = datetime.now(UTC)
        db.add(job)
        db.commit()


def _publish_turn_delta(
    job_id: UUID,
    *,
    status: str,
    reasoning_delta: str,
    content_delta: str,
    reasoning_length: int,
    content_length: int,
    narrative: str,
    model: str | None,
    message: str,
    stage: str,
    stage_started_at: datetime | None,
    reset_buffers: bool,
) -> None:
    turn_stream_event_broker.publish(
        job_id,
        {
            "type": "delta",
            "status": status,
            "model_used": model,
            "progress_message": message,
            **_turn_stage_event_payload(stage, stage_started_at),
            "reasoning_delta": reasoning_delta,
            "content_delta": content_delta,
            "reset_buffers": reset_buffers,
            "reasoning_length": reasoning_length,
            "content_length": content_length,
            "narrative_buffer": narrative,
            "narrative_length": len(narrative),
            "last_event_at": datetime.now(UTC).isoformat(),
        },
    )


def _publish_turn_progress(
    job_id: UUID,
    *,
    status: str,
    message: str,
    model: str | None,
    reasoning_length: int,
    content_length: int,
    narrative: str,
    stage: str,
    stage_started_at: datetime | None,
) -> None:
    turn_stream_event_broker.publish(
        job_id,
        {
            "type": "progress",
            "status": status,
            "model_used": model,
            "progress_message": message,
            **_turn_stage_event_payload(stage, stage_started_at),
            "reasoning_length": reasoning_length,
            "content_length": content_length,
            "narrative_buffer": narrative,
            "narrative_length": len(narrative),
            "last_event_at": datetime.now(UTC).isoformat(),
        },
    )


def _publish_turn_snapshot(
    job: TurnJob,
    turn: Turn | None,
    *,
    event_type: str,
    terminal: bool,
) -> None:
    payload = TurnJobRead(
        id=job.id,
        game_id=job.game_id,
        status=job.status,
        turn=turn,
        turn_id=job.turn_id,
        model_used=job.model_used,
        error_message=job.error_message,
        reasoning_content=job.reasoning_content,
        content_buffer=job.content_buffer,
        narrative_buffer=job.narrative_buffer,
        progress_message=job.progress_message,
        stage=job.stage,
        stage_label=job.stage_label,
        stage_index=job.stage_index,
        stage_total=job.stage_total,
        stage_started_at=job.stage_started_at,
        maintenance_status=job.maintenance_status,
        maintenance_stage=job.maintenance_stage,
        maintenance_message=job.maintenance_message,
        maintenance_error=job.maintenance_error,
        maintenance_started_at=job.maintenance_started_at,
        maintenance_completed_at=job.maintenance_completed_at,
        director_used_fallback=job.director_used_fallback,
        drift_severity=job.drift_severity,
        rewrite_triggered=job.rewrite_triggered,
        extractor_failed=job.extractor_failed,
        stream_started_at=job.stream_started_at,
        last_event_at=job.last_event_at,
    )
    turn_stream_event_broker.publish(
        job.id,
        {
            "type": event_type,
            "job": payload,
            "terminal": terminal,
        },
    )


def publish_turn_job_snapshot(
    job_id: UUID,
    *,
    event_type: str = "progress",
    terminal: bool = False,
) -> None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return
        turn = db.get(Turn, job.turn_id) if job.turn_id else None
        _publish_turn_snapshot(job, turn, event_type=event_type, terminal=terminal)


def _set_stream_stage(stream_state: StreamState, stage: str) -> None:
    if stream_state["stage"] != stage or stream_state["stage_started_at"] is None:
        stream_state["stage"] = stage
        stream_state["stage_started_at"] = datetime.now(UTC)


def _set_job_stage(job: TurnJob, stage: str, started_at: datetime) -> None:
    if job.stage != stage or job.stage_started_at is None:
        job.stage_started_at = started_at
    job.stage = stage
    job.stage_label = TURN_JOB_STAGE_LABELS.get(stage, "处理中")
    job.stage_index = TURN_JOB_STAGE_INDEXES.get(stage, 0)
    job.stage_total = TURN_JOB_STAGE_TOTAL


def _turn_stage_event_payload(stage: str, stage_started_at: datetime | None) -> dict[str, object]:
    return {
        "stage": stage,
        "stage_label": TURN_JOB_STAGE_LABELS.get(stage, "处理中"),
        "stage_index": TURN_JOB_STAGE_INDEXES.get(stage, 0),
        "stage_total": TURN_JOB_STAGE_TOTAL,
        "stage_started_at": stage_started_at.isoformat() if stage_started_at else None,
    }


def _turn_progress_message(reasoning: str, content: str, narrative: str) -> str:
    if narrative.strip():
        return f"DeepSeek 正在书写剧情，已收到 {len(narrative)} 字剧情。"
    if content.strip():
        return "DeepSeek 正在组织剧情结构，等待剧情正文..."
    if reasoning.strip():
        return f"DeepSeek 正在思考剧情，已收到 {len(reasoning)} 字思考过程。"
    return "正在准备剧情上下文与导演决策..."


def extract_partial_json_string_field(content: str, field_name: str) -> str:
    key = f'"{field_name}"'
    key_index = content.find(key)
    if key_index < 0:
        return ""

    colon_index = content.find(":", key_index + len(key))
    if colon_index < 0:
        return ""

    value_index = colon_index + 1
    while value_index < len(content) and content[value_index].isspace():
        value_index += 1
    if value_index >= len(content) or content[value_index] != '"':
        return ""

    chars: list[str] = []
    index = value_index + 1
    while index < len(content):
        char = content[index]
        if char == '"':
            break
        if char == "\\":
            decoded, consumed = _decode_json_string_escape(content, index)
            if consumed == 0:
                break
            chars.append(decoded)
            index += consumed
            continue
        chars.append(char)
        index += 1
    return "".join(chars)


def _decode_json_string_escape(content: str, backslash_index: int) -> tuple[str, int]:
    if backslash_index + 1 >= len(content):
        return "", 0

    escape = content[backslash_index + 1]
    simple_escapes = {
        '"': '"',
        "\\": "\\",
        "/": "/",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }
    if escape in simple_escapes:
        return simple_escapes[escape], 2

    if escape != "u":
        return escape, 2

    hex_start = backslash_index + 2
    hex_end = hex_start + 4
    if hex_end > len(content):
        return "", 0

    try:
        return chr(int(content[hex_start:hex_end], 16)), 6
    except ValueError:
        return "", 0
