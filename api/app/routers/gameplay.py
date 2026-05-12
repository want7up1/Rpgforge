import asyncio
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.game import Game
from app.models.generator_job import TurnJob
from app.models.turn import Turn
from app.schemas.turn import TurnCreate, TurnJobCreateResponse, TurnJobRead, TurnRead
from app.services.deepseek_client import DeepSeekAPIError, DeepSeekConfigurationError
from app.services.gameplay import GameplayService, GameplayValidationError, gameplay_game_query
from app.services.job_queue import enqueue_turn_job
from app.services.turn_stream_events import format_sse_event, turn_stream_event_broker

router = APIRouter(prefix="/api/games/{game_id}/turns", tags=["gameplay"])
DB_DEPENDENCY = Depends(get_db)


def gameplay_service() -> GameplayService:
    return GameplayService()


GAMEPLAY_SERVICE_DEPENDENCY = Depends(gameplay_service)
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def get_game_or_404_for_gameplay(db: Session, game_id: UUID) -> Game:
    game = db.scalars(gameplay_game_query(game_id)).first()
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found.")
    return game


def read_turn_job_or_404(db: Session, game_id: UUID, job_id: UUID) -> TurnJobRead:
    job = db.scalars(
        select(TurnJob).where(TurnJob.id == job_id, TurnJob.game_id == game_id)
    ).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turn job not found.")

    turn = (
        db.scalars(select(Turn).where(Turn.id == job.turn_id, Turn.game_id == game_id)).first()
        if job.turn_id
        else None
    )
    return TurnJobRead(
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
        stream_started_at=job.stream_started_at,
        last_event_at=job.last_event_at,
    )


@router.get("", response_model=list[TurnRead])
def list_turns(game_id: UUID, db: Session = DB_DEPENDENCY) -> list[Turn]:
    get_game_or_404_for_gameplay(db, game_id)
    return list(
        db.scalars(
            select(Turn).where(Turn.game_id == game_id).order_by(Turn.turn_number.asc())
        ).all()
    )


@router.post("", response_model=TurnRead, status_code=status.HTTP_201_CREATED)
async def create_turn(
    game_id: UUID,
    payload: TurnCreate,
    db: Session = DB_DEPENDENCY,
    service: GameplayService = GAMEPLAY_SERVICE_DEPENDENCY,
) -> Turn:
    game = get_game_or_404_for_gameplay(db, game_id)
    try:
        return await service.run_turn(db, game, payload)
    except DeepSeekConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except DeepSeekAPIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except GameplayValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GM 输出格式无效：{exc}",
        ) from exc


@router.post(
    "/jobs",
    response_model=TurnJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_turn_job(
    game_id: UUID,
    payload: TurnCreate,
    db: Session = DB_DEPENDENCY,
) -> TurnJobCreateResponse:
    get_game_or_404_for_gameplay(db, game_id)
    job = TurnJob(
        game_id=game_id,
        status="pending",
        request_json=payload.model_dump(mode="json"),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    try:
        enqueue_turn_job(job.id)
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
    return TurnJobCreateResponse(id=job.id, status=job.status)


@router.get("/jobs/active", response_model=TurnJobRead | None)
def get_active_turn_job(game_id: UUID, db: Session = DB_DEPENDENCY) -> TurnJobRead | None:
    get_game_or_404_for_gameplay(db, game_id)
    job = db.scalars(
        select(TurnJob)
        .where(TurnJob.game_id == game_id, TurnJob.status.in_(("pending", "running")))
        .order_by(TurnJob.created_at.desc())
        .limit(1)
    ).first()
    if job is None:
        return None
    return read_turn_job_or_404(db, game_id, job.id)


@router.get("/jobs/{job_id}", response_model=TurnJobRead)
def get_turn_job(game_id: UUID, job_id: UUID, db: Session = DB_DEPENDENCY) -> TurnJobRead:
    get_game_or_404_for_gameplay(db, game_id)
    return read_turn_job_or_404(db, game_id, job_id)


@router.get("/jobs/{job_id}/events")
async def stream_turn_job_events(
    game_id: UUID,
    job_id: UUID,
    request: Request,
    db: Session = DB_DEPENDENCY,
) -> StreamingResponse:
    get_game_or_404_for_gameplay(db, game_id)
    queue = turn_stream_event_broker.subscribe(job_id)
    try:
        initial_job = read_turn_job_or_404(db, game_id, job_id)
    except HTTPException:
        turn_stream_event_broker.unsubscribe(job_id, queue)
        raise

    async def event_stream():
        try:
            yield format_sse_event(
                "snapshot",
                {
                    "type": "snapshot",
                    "job": initial_job,
                    "terminal": initial_job.status in {"completed", "failed"},
                },
            )

            latest_event = turn_stream_event_broker.latest(job_id)
            if latest_event:
                yield format_sse_event(str(latest_event.get("type", "message")), latest_event)
                if latest_event.get("terminal"):
                    return

            if initial_job.status in {"completed", "failed"}:
                return

            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield format_sse_event(
                        "heartbeat",
                        {
                            "type": "heartbeat",
                            "job_id": str(job_id),
                            "sent_at": datetime.now(UTC).isoformat(),
                        },
                    )
                    continue

                event_type = str(event.get("type", "message"))
                yield format_sse_event(event_type, event)
                if event.get("terminal"):
                    return
        finally:
            turn_stream_event_broker.unsubscribe(job_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/{turn_id}", response_model=TurnRead)
def get_turn(game_id: UUID, turn_id: UUID, db: Session = DB_DEPENDENCY) -> Turn:
    get_game_or_404_for_gameplay(db, game_id)
    turn = db.scalars(
        select(Turn).where(Turn.game_id == game_id, Turn.id == turn_id)
    ).first()
    if turn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turn not found.")
    return turn
