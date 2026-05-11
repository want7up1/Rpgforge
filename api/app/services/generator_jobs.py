import asyncio
from datetime import UTC, datetime
from time import monotonic
from typing import TypedDict
from uuid import UUID

from pydantic import ValidationError

from app.db.session import SessionLocal
from app.models.generator_job import GeneratorFinalizeJob
from app.schemas.generator import (
    GeneratedGameConfig,
    GeneratorFinalizeJobRead,
    GeneratorFinalizeRequest,
)
from app.services.deepseek_client import DeepSeekError
from app.services.game_generator import GameGeneratorService, ModelOutputValidationError
from app.services.generator_stream_events import generator_stream_event_broker

FINALIZE_JOB_TIMEOUT_SECONDS = 14 * 60
STREAM_WRITE_INTERVAL_SECONDS = 0.8
STREAM_WRITE_MIN_CHARS = 1024


class StreamState(TypedDict):
    reasoning: str
    content: str
    model: str | None


async def run_finalize_job(job_id: UUID) -> None:
    stream_state: StreamState = {"reasoning": "", "content": "", "model": None}

    with SessionLocal() as db:
        job = db.get(GeneratorFinalizeJob, job_id)
        if job is None:
            return
        now = datetime.now(UTC)
        job.status = "running"
        job.error_message = None
        job.reasoning_content = ""
        job.content_buffer = ""
        job.progress_message = "已连接 DeepSeek Pro，等待流式返回..."
        job.stream_started_at = now
        job.last_event_at = now
        db.add(job)
        db.commit()
        db.refresh(job)
        _publish_finalize_snapshot(job, event_type="progress", terminal=False)

    try:
        with SessionLocal() as db:
            job = db.get(GeneratorFinalizeJob, job_id)
            if job is None:
                return
            request = GeneratorFinalizeRequest.model_validate(job.request_json)

        last_saved_at = 0.0
        last_saved_reasoning_length = 0
        last_saved_content_length = 0

        async def on_update(reasoning: str, content: str, model: str | None) -> None:
            nonlocal last_saved_at, last_saved_reasoning_length, last_saved_content_length
            stream_state["reasoning"] = reasoning
            stream_state["content"] = content
            stream_state["model"] = model

            now_monotonic = monotonic()
            reasoning_delta = len(reasoning) - last_saved_reasoning_length
            content_delta = len(content) - last_saved_content_length
            latest_reasoning_delta = reasoning[last_saved_reasoning_length:]
            has_stage_update = "配置生成：" in latest_reasoning_delta
            should_save = (
                now_monotonic - last_saved_at >= STREAM_WRITE_INTERVAL_SECONDS
                or reasoning_delta >= STREAM_WRITE_MIN_CHARS
                or content_delta >= STREAM_WRITE_MIN_CHARS
                or has_stage_update
            )
            if not should_save:
                return

            last_saved_at = now_monotonic
            last_saved_reasoning_length = len(reasoning)
            last_saved_content_length = len(content)
            _update_stream_progress(
                job_id,
                reasoning=reasoning,
                content=content,
                model=model,
                message=_finalize_progress_message(reasoning, content),
            )

        result = await asyncio.wait_for(
            GameGeneratorService().finalize_stream(request, on_update=on_update),
            timeout=FINALIZE_JOB_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        _mark_job_failed(
            job_id,
            "完整配置生成超过 14 分钟，已停止。请缩短设定或稍后重试。",
            stream_state,
        )
        return
    except (DeepSeekError, ModelOutputValidationError, ValidationError, ValueError) as exc:
        _mark_job_failed(job_id, str(exc), stream_state)
        return
    except Exception as exc:
        _mark_job_failed(job_id, f"{type(exc).__name__}: {exc}", stream_state)
        return

    with SessionLocal() as db:
        job = db.get(GeneratorFinalizeJob, job_id)
        if job is None:
            return
        now = datetime.now(UTC)
        job.status = "completed"
        job.result_json = result.config.model_dump(mode="json")
        job.model_used = result.model_used
        job.reasoning_content = stream_state["reasoning"]
        job.content_buffer = stream_state["content"]
        job.progress_message = "完整配置已生成，正在返回结果。"
        job.last_event_at = now
        job.completed_at = datetime.now(UTC)
        db.add(job)
        db.commit()
        db.refresh(job)
        _publish_finalize_snapshot(job, event_type="completed", terminal=True)


def _mark_job_failed(job_id: UUID, message: str, stream_state: StreamState) -> None:
    with SessionLocal() as db:
        job = db.get(GeneratorFinalizeJob, job_id)
        if job is None:
            return
        now = datetime.now(UTC)
        job.status = "failed"
        job.error_message = message[:4000]
        job.reasoning_content = stream_state["reasoning"]
        job.content_buffer = stream_state["content"]
        job.progress_message = "完整配置生成失败，已保留收到的流式内容。"
        if stream_state["model"]:
            job.model_used = stream_state["model"]
        job.last_event_at = now
        job.completed_at = now
        db.add(job)
        db.commit()
        db.refresh(job)
        _publish_finalize_snapshot(job, event_type="failed", terminal=True)


def _update_stream_progress(
    job_id: UUID,
    *,
    reasoning: str,
    content: str,
    model: str | None,
    message: str,
) -> None:
    with SessionLocal() as db:
        job = db.get(GeneratorFinalizeJob, job_id)
        if job is None:
            return
        job.reasoning_content = reasoning
        job.content_buffer = content
        job.progress_message = message
        if model:
            job.model_used = model
        job.last_event_at = datetime.now(UTC)
        db.add(job)
        db.commit()
        db.refresh(job)
        _publish_finalize_snapshot(job, event_type="progress", terminal=False)


def _publish_finalize_snapshot(
    job: GeneratorFinalizeJob,
    *,
    event_type: str,
    terminal: bool,
) -> None:
    config = (
        GeneratedGameConfig.model_validate(job.result_json)
        if job.status == "completed" and job.result_json
        else None
    )
    payload = GeneratorFinalizeJobRead(
        id=job.id,
        status=job.status,
        config=config,
        model_used=job.model_used,
        error_message=job.error_message,
        reasoning_content=job.reasoning_content,
        content_buffer=job.content_buffer,
        progress_message=job.progress_message,
        stream_started_at=job.stream_started_at,
        last_event_at=job.last_event_at,
    )
    generator_stream_event_broker.publish(
        job.id,
        {
            "type": event_type,
            "job": payload,
            "terminal": terminal,
        },
    )


def _finalize_progress_message(reasoning: str, content: str) -> str:
    stage_line = _latest_finalize_stage(reasoning)
    if stage_line:
        return stage_line
    if content.strip():
        return f"DeepSeek 正在输出完整配置 JSON，已收到 {len(content)} 字内容。"
    if reasoning.strip():
        return f"DeepSeek 正在思考完整配置，已收到 {len(reasoning)} 字思考过程。"
    return "已连接 DeepSeek Pro，等待流式返回..."


def _latest_finalize_stage(reasoning: str) -> str:
    for line in reversed(reasoning.splitlines()):
        stage = line.strip()
        if stage.startswith("配置生成："):
            return stage
    return ""
