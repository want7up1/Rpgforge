import asyncio
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.models.game import Game
from app.models.generator_job import TurnJob
from app.models.turn import Turn
from app.schemas.turn import TurnCreate, TurnJobCreateResponse, TurnJobRead, TurnRead
from app.services.deepseek_client import DeepSeekAPIError, DeepSeekConfigurationError
from app.services.gameplay import GameplayService, GameplayValidationError, gameplay_game_query
from app.services.job_queue import enqueue_turn_job, reconcile_turn_job_liveness
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
SSE_DB_SNAPSHOT_INTERVAL_SECONDS = 1.5
ACTIVE_JOB_STATUSES = ("pending", "running")
ACTIVE_MAINTENANCE_STATUSES = ("pending", "running")
STATE_EXTRACT_BLOCKING_TIMEOUT_SECONDS = 3 * 60


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
    if reconcile_turn_job_liveness(db, job):
        db.commit()
        db.refresh(job)

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
        maintenance_status=job.maintenance_status,
        maintenance_stage=job.maintenance_stage,
        maintenance_message=job.maintenance_message,
        maintenance_error=job.maintenance_error,
        maintenance_started_at=job.maintenance_started_at,
        maintenance_completed_at=job.maintenance_completed_at,
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
    if (
        _active_turn_job(db, game_id) is not None
        or _active_turn_maintenance_job(db, game_id) is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="已有回合任务或状态维护正在运行，请等待完成后再继续。",
        )
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
    blocking_job = _active_turn_job(db, game_id)
    if blocking_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="已有回合生成任务正在运行，请等待完成后再继续。",
        )
    maintenance_job = _active_turn_maintenance_job(db, game_id)
    if maintenance_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="上一回合状态维护仍在进行，请等待状态提取完成后再继续。",
        )
    job = TurnJob(
        game_id=game_id,
        status="pending",
        request_json=payload.model_dump(mode="json"),
        maintenance_status="pending",
        maintenance_stage="state_extract",
        maintenance_message="等待回合生成完成后执行状态维护。",
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
    job = _active_turn_job(db, game_id) or _active_turn_maintenance_job(db, game_id)
    if job is None:
        return None
    return read_turn_job_or_404(db, game_id, job.id)


def _active_turn_job(db: Session, game_id: UUID) -> TurnJob | None:
    job = db.scalars(
        select(TurnJob)
        .where(TurnJob.game_id == game_id, TurnJob.status.in_(ACTIVE_JOB_STATUSES))
        .order_by(TurnJob.created_at.desc())
        .limit(1)
    ).first()
    if job is not None and reconcile_turn_job_liveness(db, job):
        db.commit()
        return None
    return job


def _active_turn_maintenance_job(db: Session, game_id: UUID) -> TurnJob | None:
    job = db.scalars(
        select(TurnJob)
        .where(
            TurnJob.game_id == game_id,
            TurnJob.status == "completed",
            TurnJob.maintenance_status.in_(ACTIVE_MAINTENANCE_STATUSES),
            TurnJob.maintenance_stage == "state_extract",
        )
        .order_by(TurnJob.created_at.desc())
        .limit(1)
    ).first()
    if job is not None and _is_state_extract_stale(job):
        _mark_state_extract_stale(db, job)
        return None
    return job


def _is_state_extract_stale(job: TurnJob) -> bool:
    anchor = job.last_event_at or job.maintenance_started_at or job.updated_at or job.created_at
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    return (datetime.now(UTC) - anchor).total_seconds() > STATE_EXTRACT_BLOCKING_TIMEOUT_SECONDS


def _mark_state_extract_stale(db: Session, job: TurnJob) -> None:
    now = datetime.now(UTC)
    message = "状态提取超过 3 分钟，已自动解除阻塞；本回合结算可能稍后重试。"
    job.maintenance_status = "failed"
    job.maintenance_message = message
    job.maintenance_error = message
    job.maintenance_completed_at = now
    job.last_event_at = now
    db.add(job)
    db.commit()


@router.get("/jobs/{job_id}", response_model=TurnJobRead)
def get_turn_job(game_id: UUID, job_id: UUID, db: Session = DB_DEPENDENCY) -> TurnJobRead:
    get_game_or_404_for_gameplay(db, game_id)
    return read_turn_job_or_404(db, game_id, job_id)


@router.get("/jobs/{job_id}/events")
async def stream_turn_job_events(
    game_id: UUID,
    job_id: UUID,
    request: Request,
) -> StreamingResponse:
    queue = turn_stream_event_broker.subscribe(job_id)
    try:
        initial_job = _load_turn_job_snapshot(game_id, job_id)
        if initial_job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Turn job not found.")
    except HTTPException:
        turn_stream_event_broker.unsubscribe(job_id, queue)
        raise

    async def event_stream():
        last_snapshot_signature = _turn_job_signature(initial_job)
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
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=SSE_DB_SNAPSHOT_INTERVAL_SECONDS,
                    )
                except TimeoutError:
                    fresh_job = _load_turn_job_snapshot(game_id, job_id)
                    if fresh_job is None:
                        return
                    terminal = fresh_job.status in {"completed", "failed"}
                    fresh_signature = _turn_job_signature(fresh_job)
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
                    continue

                event_type = str(event.get("type", "message"))
                event_job = event.get("job")
                if event_job is not None:
                    last_snapshot_signature = _turn_job_signature(event_job)
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


def _load_turn_job_snapshot(game_id: UUID, job_id: UUID) -> TurnJobRead | None:
    with SessionLocal() as db:
        try:
            return read_turn_job_or_404(db, game_id, job_id)
        except HTTPException:
            return None


def _turn_job_signature(job: object) -> tuple[object, ...]:
    return (
        getattr(job, "status", None),
        getattr(job, "turn_id", None),
        getattr(job, "model_used", None),
        getattr(job, "error_message", None),
        getattr(job, "progress_message", None),
        getattr(job, "stage", None),
        getattr(job, "stage_label", None),
        getattr(job, "stage_index", None),
        getattr(job, "stage_total", None),
        getattr(job, "stage_started_at", None),
        getattr(job, "maintenance_status", None),
        getattr(job, "maintenance_stage", None),
        getattr(job, "maintenance_message", None),
        getattr(job, "maintenance_error", None),
        getattr(job, "stream_started_at", None),
        getattr(job, "last_event_at", None),
        len(getattr(job, "reasoning_content", "") or ""),
        len(getattr(job, "content_buffer", "") or ""),
        len(getattr(job, "narrative_buffer", "") or ""),
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
