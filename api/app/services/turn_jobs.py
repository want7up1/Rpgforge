import asyncio
from datetime import UTC, datetime
from time import monotonic
from typing import TypedDict
from uuid import UUID

from pydantic import ValidationError

from app.db.session import SessionLocal
from app.models.generator_job import TurnJob
from app.models.turn import Turn
from app.schemas.turn import TurnCreate, TurnJobRead
from app.services.deepseek_client import DeepSeekError
from app.services.gameplay import GameplayService, GameplayValidationError, gameplay_game_query
from app.services.turn_stream_events import turn_stream_event_broker

TURN_JOB_TIMEOUT_SECONDS = 14 * 60
STREAM_WRITE_INTERVAL_SECONDS = 0.8
STREAM_WRITE_MIN_CHARS = 512


class StreamState(TypedDict):
    reasoning: str
    content: str
    narrative: str
    model: str | None


async def run_turn_job(job_id: UUID) -> None:
    stream_state: StreamState = {
        "reasoning": "",
        "content": "",
        "narrative": "",
        "model": None,
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
        job.stream_started_at = now
        job.last_event_at = now
        db.add(job)
        db.commit()

    try:
        with SessionLocal() as db:
            job = db.get(TurnJob, job_id)
            if job is None:
                return
            game = db.scalars(gameplay_game_query(job.game_id)).first()
            if game is None:
                _mark_job_failed(job_id, "Game not found.", stream_state)
                return
            request = TurnCreate.model_validate(job.request_json)

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
                        reasoning
                        if reset_buffers
                        else reasoning[last_published_reasoning_length:]
                    ),
                    content_delta=(
                        content if reset_buffers else content[last_published_content_length:]
                    ),
                    reasoning_length=len(reasoning),
                    content_length=len(content),
                    narrative=narrative,
                    model=model,
                    message=_turn_progress_message(reasoning, content, narrative),
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
                    reset_buffers=reset_buffers,
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
                )
                _update_progress_message(
                    job_id,
                    message=message,
                    model=stream_state["model"],
                    reasoning=stream_state["reasoning"],
                    content=stream_state["content"],
                    narrative=stream_state["narrative"],
                )

            turn = await asyncio.wait_for(
                GameplayService().run_turn_stream(
                    db,
                    game,
                    request,
                    on_update=on_update,
                    on_progress=on_progress,
                    extract_state=False,
                ),
                timeout=TURN_JOB_TIMEOUT_SECONDS,
            )
    except TimeoutError:
        _mark_job_failed(
            job_id,
            "回合生成超过 14 分钟，已停止。请缩短输入或稍后重试。",
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
        job.progress_message = "剧情已生成，状态变更正在后台写入。"
        job.last_event_at = now
        job.completed_at = now
        db.add(job)
        db.commit()
        db.refresh(job)
        persisted_turn = db.get(Turn, turn.id)
        _publish_turn_snapshot(job, persisted_turn, event_type="completed", terminal=True)

    await _extract_state_delta_after_completion(job_id, turn.id)


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
        if stream_state["model"]:
            job.model_used = stream_state["model"]
        job.last_event_at = now
        job.completed_at = now
        db.add(job)
        db.commit()
        db.refresh(job)
        _publish_turn_snapshot(job, None, event_type="failed", terminal=True)


def _update_stream_progress(
    job_id: UUID,
    *,
    reasoning: str,
    content: str,
    narrative: str,
    model: str | None,
    message: str,
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
) -> None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return
        job.reasoning_content = reasoning
        job.content_buffer = content
        job.narrative_buffer = narrative
        job.progress_message = message
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
    reset_buffers: bool,
) -> None:
    turn_stream_event_broker.publish(
        job_id,
        {
            "type": "delta",
            "status": status,
            "model_used": model,
            "progress_message": message,
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
) -> None:
    turn_stream_event_broker.publish(
        job_id,
        {
            "type": "progress",
            "status": status,
            "model_used": model,
            "progress_message": message,
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


async def _extract_state_delta_after_completion(job_id: UUID, turn_id: UUID) -> None:
    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return
        game = db.scalars(gameplay_game_query(job.game_id)).first()
        if game is None:
            return
        turn = db.get(Turn, turn_id)
        if turn is None:
            return
        await GameplayService()._create_state_delta(db, game, turn)

    with SessionLocal() as db:
        job = db.get(TurnJob, job_id)
        if job is None:
            return
        job.progress_message = "剧情已生成，状态变更已写入。"
        job.last_event_at = datetime.now(UTC)
        db.add(job)
        db.commit()


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
