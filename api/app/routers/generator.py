from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.models.generator_job import GeneratorChatJob, GeneratorFinalizeJob
from app.routers.games import game_detail_response, get_game_or_404
from app.schemas.generator import (
    GeneratedGameConfig,
    GeneratorChatJobCreateResponse,
    GeneratorChatJobRead,
    GeneratorChatRequest,
    GeneratorChatResponse,
    GeneratorCreateGameRequest,
    GeneratorCreateGameResponse,
    GeneratorFinalizeJobCreateResponse,
    GeneratorFinalizeJobRead,
    GeneratorFinalizeRequest,
    GeneratorFinalizeResponse,
)
from app.services.deepseek_client import DeepSeekAPIError, DeepSeekConfigurationError
from app.services.game_creator import create_game_from_config
from app.services.game_generator import GameGeneratorService, ModelOutputValidationError
from app.services.generator_stream_events import generator_stream_event_broker
from app.services.job_queue import enqueue_chat_job, enqueue_finalize_job
from app.services.turn_stream_events import TurnStreamEvent, format_sse_event

router = APIRouter(prefix="/api/generator", tags=["generator"])
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
SSE_DB_SNAPSHOT_INTERVAL_SECONDS = 1.5


def generator_service() -> GameGeneratorService:
    return GameGeneratorService()


DB_DEPENDENCY = Depends(get_db)
GENERATOR_SERVICE_DEPENDENCY = Depends(generator_service)


@router.post("/chat", response_model=GeneratorChatResponse)
async def generator_chat(
    payload: GeneratorChatRequest,
    service: GameGeneratorService = GENERATOR_SERVICE_DEPENDENCY,
) -> GeneratorChatResponse:
    try:
        return await service.interview(payload)
    except DeepSeekConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except DeepSeekAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except (ValueError, ModelOutputValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"规则生成器返回格式无效：{exc}",
        ) from exc


@router.post(
    "/chat-jobs",
    response_model=GeneratorChatJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_chat_job(
    payload: GeneratorChatRequest,
    db: Session = DB_DEPENDENCY,
) -> GeneratorChatJobCreateResponse:
    job = GeneratorChatJob(
        status="pending",
        request_json=payload.model_dump(mode="json"),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        enqueue_chat_job(job.id)
    except Exception as exc:
        now = datetime.now(UTC)
        job.status = "failed"
        job.error_message = f"任务队列不可用：{exc}"
        job.progress_message = "任务队列不可用，请检查 Redis/RQ worker。"
        job.completed_at = now
        job.last_event_at = now
        db.add(job)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务队列不可用，请检查 Redis/RQ worker。",
        ) from exc
    return GeneratorChatJobCreateResponse(id=job.id, status=job.status)


@router.get("/chat-jobs/active", response_model=GeneratorChatJobRead | None)
def get_active_chat_job(db: Session = DB_DEPENDENCY) -> GeneratorChatJobRead | None:
    job = db.scalars(
        select(GeneratorChatJob)
        .where(GeneratorChatJob.status.in_(("pending", "running")))
        .order_by(GeneratorChatJob.created_at.desc())
        .limit(1)
    ).first()
    if job is None:
        return None
    return _chat_job_read(job)


@router.get("/chat-jobs/{job_id}", response_model=GeneratorChatJobRead)
def get_chat_job(job_id: UUID, db: Session = DB_DEPENDENCY) -> GeneratorChatJobRead:
    job = db.scalars(select(GeneratorChatJob).where(GeneratorChatJob.id == job_id)).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat job not found.")

    return _chat_job_read(job)


@router.get("/chat-jobs/{job_id}/events")
async def stream_chat_job_events(
    job_id: UUID,
    request: Request,
) -> StreamingResponse:
    latest_stream_entry = generator_stream_event_broker.latest_stream_entry(job_id)
    latest_stream_event = latest_stream_entry[1] if latest_stream_entry is not None else None
    stream_cursor = latest_stream_entry[0] if latest_stream_entry is not None else "0-0"
    initial_job = _load_chat_job_snapshot(job_id)
    if initial_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat job not found.",
        )

    return _stream_generator_job_events(
        job_id=job_id,
        request=request,
        stream_cursor=stream_cursor,
        latest_stream_event=latest_stream_event,
        initial_job=initial_job,
        load_job_snapshot=lambda: _load_chat_job_snapshot(job_id),
    )


@router.post("/finalize", response_model=GeneratorFinalizeResponse)
async def generator_finalize(
    payload: GeneratorFinalizeRequest,
    service: GameGeneratorService = GENERATOR_SERVICE_DEPENDENCY,
) -> GeneratorFinalizeResponse:
    try:
        return await service.finalize(payload)
    except DeepSeekConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except DeepSeekAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except (ValueError, ModelOutputValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"游戏配置生成结果无效：{exc}",
        ) from exc


@router.post(
    "/finalize-jobs",
    response_model=GeneratorFinalizeJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_finalize_job(
    payload: GeneratorFinalizeRequest,
    db: Session = DB_DEPENDENCY,
) -> GeneratorFinalizeJobCreateResponse:
    job = GeneratorFinalizeJob(
        status="pending",
        request_json=payload.model_dump(mode="json"),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        enqueue_finalize_job(job.id)
    except Exception as exc:
        now = datetime.now(UTC)
        job.status = "failed"
        job.error_message = f"任务队列不可用：{exc}"
        job.progress_message = "任务队列不可用，请检查 Redis/RQ worker。"
        job.completed_at = now
        job.last_event_at = now
        db.add(job)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务队列不可用，请检查 Redis/RQ worker。",
        ) from exc
    return GeneratorFinalizeJobCreateResponse(id=job.id, status=job.status)


@router.get("/finalize-jobs/active", response_model=GeneratorFinalizeJobRead | None)
def get_active_finalize_job(db: Session = DB_DEPENDENCY) -> GeneratorFinalizeJobRead | None:
    job = db.scalars(
        select(GeneratorFinalizeJob)
        .where(GeneratorFinalizeJob.status.in_(("pending", "running")))
        .order_by(GeneratorFinalizeJob.created_at.desc())
        .limit(1)
    ).first()
    if job is None:
        return None
    return _finalize_job_read(job)


@router.get("/finalize-jobs/{job_id}", response_model=GeneratorFinalizeJobRead)
def get_finalize_job(job_id: UUID, db: Session = DB_DEPENDENCY) -> GeneratorFinalizeJobRead:
    job = db.scalars(select(GeneratorFinalizeJob).where(GeneratorFinalizeJob.id == job_id)).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finalize job not found.")

    return _finalize_job_read(job)


@router.get("/finalize-jobs/{job_id}/events")
async def stream_finalize_job_events(
    job_id: UUID,
    request: Request,
) -> StreamingResponse:
    latest_stream_entry = generator_stream_event_broker.latest_stream_entry(job_id)
    latest_stream_event = latest_stream_entry[1] if latest_stream_entry is not None else None
    stream_cursor = latest_stream_entry[0] if latest_stream_entry is not None else "0-0"
    initial_job = _load_finalize_job_snapshot(job_id)
    if initial_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Finalize job not found.",
        )

    return _stream_generator_job_events(
        job_id=job_id,
        request=request,
        stream_cursor=stream_cursor,
        latest_stream_event=latest_stream_event,
        initial_job=initial_job,
        load_job_snapshot=lambda: _load_finalize_job_snapshot(job_id),
    )


@router.post(
    "/create-game",
    response_model=GeneratorCreateGameResponse,
    status_code=status.HTTP_201_CREATED,
)
def generator_create_game(
    payload: GeneratorCreateGameRequest,
    db: Session = DB_DEPENDENCY,
) -> GeneratorCreateGameResponse:
    game = create_game_from_config(db, payload.generated_config)
    return GeneratorCreateGameResponse(game=game_detail_response(get_game_or_404(db, game.id)))


def _chat_job_read(job: GeneratorChatJob) -> GeneratorChatJobRead:
    response = (
        GeneratorChatResponse.model_validate(job.result_json)
        if job.status == "completed" and job.result_json
        else None
    )
    return GeneratorChatJobRead(
        id=job.id,
        status=job.status,
        response=response,
        model_used=job.model_used,
        error_message=job.error_message,
        reasoning_content=job.reasoning_content,
        content_buffer=job.content_buffer,
        progress_message=job.progress_message,
        stream_started_at=job.stream_started_at,
        last_event_at=job.last_event_at,
    )


def _finalize_job_read(job: GeneratorFinalizeJob) -> GeneratorFinalizeJobRead:
    config = (
        GeneratedGameConfig.model_validate(job.result_json)
        if job.status == "completed" and job.result_json
        else None
    )
    return GeneratorFinalizeJobRead(
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


def _load_chat_job_snapshot(job_id: UUID) -> GeneratorChatJobRead | None:
    with SessionLocal() as db:
        job = db.scalars(select(GeneratorChatJob).where(GeneratorChatJob.id == job_id)).first()
        return _chat_job_read(job) if job else None


def _load_finalize_job_snapshot(job_id: UUID) -> GeneratorFinalizeJobRead | None:
    with SessionLocal() as db:
        job = db.scalars(
            select(GeneratorFinalizeJob).where(GeneratorFinalizeJob.id == job_id)
        ).first()
        return _finalize_job_read(job) if job else None


def _stream_generator_job_events(
    *,
    job_id: UUID,
    request: Request,
    stream_cursor: str,
    latest_stream_event: TurnStreamEvent | None,
    initial_job: GeneratorChatJobRead | GeneratorFinalizeJobRead,
    load_job_snapshot: Callable[[], GeneratorChatJobRead | GeneratorFinalizeJobRead | None],
) -> StreamingResponse:
    async def event_stream():
        last_snapshot_signature = _generator_job_signature(initial_job)
        last_stream_id = stream_cursor
        yield format_sse_event(
            "snapshot",
            {
                "type": "snapshot",
                "job": initial_job,
                "terminal": initial_job.status in {"completed", "failed"},
            },
        )

        if initial_job.status in {"completed", "failed"}:
            return

        if latest_stream_event is not None:
            event_type = str(latest_stream_event.get("type", "message"))
            event_job = latest_stream_event.get("job")
            if event_job is not None:
                last_snapshot_signature = _generator_job_signature(event_job)
            yield format_sse_event(event_type, latest_stream_event)
            if latest_stream_event.get("terminal"):
                return

        while True:
            if await request.is_disconnected():
                return

            stream_event = await generator_stream_event_broker.read_stream_event(
                job_id,
                last_stream_id,
                timeout_seconds=SSE_DB_SNAPSHOT_INTERVAL_SECONDS,
            )
            if stream_event is not None:
                last_stream_id, event = stream_event
                event_type = str(event.get("type", "message"))
                event_job = event.get("job")
                if event_job is not None:
                    last_snapshot_signature = _generator_job_signature(event_job)
                yield format_sse_event(event_type, event)
                if event.get("terminal"):
                    return

            fresh_job = load_job_snapshot()
            if fresh_job is None:
                return
            terminal = fresh_job.status in {"completed", "failed"}
            fresh_signature = _generator_job_signature(fresh_job)
            if terminal or fresh_signature != last_snapshot_signature:
                last_snapshot_signature = fresh_signature
                yield format_sse_event(
                    "snapshot",
                    {
                        "type": "snapshot",
                        "job": fresh_job,
                        "terminal": terminal,
                    },
                )
                if terminal:
                    return
            yield format_sse_event(
                "heartbeat",
                {
                    "type": "heartbeat",
                    "job_id": str(job_id),
                    "sent_at": datetime.now(UTC).isoformat(),
                },
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def _generator_job_signature(job: object) -> tuple[object, ...]:
    return (
        getattr(job, "status", None),
        getattr(job, "model_used", None),
        getattr(job, "error_message", None),
        getattr(job, "progress_message", None),
        getattr(job, "stream_started_at", None),
        getattr(job, "last_event_at", None),
        len(getattr(job, "reasoning_content", "") or ""),
        len(getattr(job, "content_buffer", "") or ""),
    )
