"""Admin-only read endpoints.

需要 `X-Settings-Admin-Token` header 才能访问（生产模式如果未配置 token 会拒绝）。
当前只暴露 LLM trace 查询，方便排查 AI 链路问题。

注意：本模块**不要**加 `from __future__ import annotations`。它会让 FastAPI 依赖参数
（Query 等）的注解变成字符串，既触发 ruff B008，也可能让 FastAPI 误解析（参见
progress.py 的 204 历史 bug）。
"""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.agent_trace import AgentTrace
from app.models.generator_job import TurnJob
from app.models.turn_evaluation import TurnEvaluation
from app.routers.settings import verify_settings_token
from app.services.turn_judge import TurnJudgeError, evaluate_turn

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(verify_settings_token)],
)
DB_DEPENDENCY = Depends(get_db)


class AgentTraceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_kind: str | None
    job_id: UUID | None
    agent: str
    task_type: str
    model: str | None
    prompt_messages: list[dict[str, Any]] | None
    output_text: str | None
    reasoning_text: str | None
    tokens_input: int | None
    tokens_output: int | None
    tokens_reasoning: int | None
    latency_ms: int
    status: str
    error_message: str | None
    extras: dict[str, Any] | None
    created_at: datetime


class AgentTraceSummary(BaseModel):
    """轻量版（不带 prompt/output 全文），用于列表查询。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_kind: str | None
    job_id: UUID | None
    agent: str
    task_type: str
    model: str | None
    tokens_input: int | None
    tokens_output: int | None
    tokens_reasoning: int | None
    latency_ms: int
    status: str
    error_message: str | None
    created_at: datetime


@router.get("/traces", response_model=list[AgentTraceSummary])
def list_traces(
    db: Session = DB_DEPENDENCY,
    job_id: Annotated[UUID | None, Query(description="按上游 job_id 过滤")] = None,
    job_kind: Annotated[str | None, Query(description="job 类型过滤")] = None,
    agent: Annotated[str | None, Query(description="按 agent 名字过滤")] = None,
    status_eq: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[AgentTrace]:
    """返回最近 N 条 trace 的轻量列表（不含 prompt/output 全文）。"""
    stmt = select(AgentTrace).order_by(AgentTrace.created_at.desc()).limit(limit)
    if job_id is not None:
        stmt = stmt.where(AgentTrace.job_id == job_id)
    if job_kind is not None:
        stmt = stmt.where(AgentTrace.job_kind == job_kind)
    if agent is not None:
        stmt = stmt.where(AgentTrace.agent == agent)
    if status_eq is not None:
        stmt = stmt.where(AgentTrace.status == status_eq)
    return list(db.scalars(stmt).all())


@router.get("/traces/{trace_id}", response_model=AgentTraceRead)
def get_trace(trace_id: UUID, db: Session = DB_DEPENDENCY) -> AgentTrace:
    """单条 trace 详情，含 prompt_messages 和 output 全文。"""
    trace = db.get(AgentTrace, trace_id)
    if trace is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Trace not found.",
        )
    return trace


@router.get("/turn-jobs/{job_id}/traces", response_model=list[AgentTraceRead])
def get_turn_job_traces(job_id: UUID, db: Session = DB_DEPENDENCY) -> list[AgentTrace]:
    """一个回合的所有 LLM 调用 trace（带完整 prompt/output），按时间正序。"""
    stmt = (
        select(AgentTrace)
        .where(AgentTrace.job_kind == "turn", AgentTrace.job_id == job_id)
        .order_by(AgentTrace.created_at.asc())
    )
    return list(db.scalars(stmt).all())


class TurnEvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    turn_id: UUID
    game_id: UUID
    canon_fidelity: int | None
    state_consistency: int | None
    pacing: int | None
    prose_quality: int | None
    freshness: int | None
    safety: int | None
    # DB 列是 Numeric(3,2)（Decimal）；用 float 让 JSON 序列化为 number 而非 string，
    # 与前端 TurnEvaluationRead.overall_score: number 一致。Pydantic v2 lax 模式
    # 会把 Decimal coerce 成 float。
    overall_score: float | None
    rationale: dict[str, Any] | None
    judge_model: str | None
    trace_id: UUID | None
    status: str
    error_message: str | None
    created_at: datetime


@router.post("/turns/{turn_id}/evaluate", response_model=TurnEvaluationRead)
async def trigger_turn_evaluation(
    turn_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> TurnEvaluation:
    """对指定回合手动触发 LLM-as-Judge 评分。

    评分本身会消耗 LLM quota；只有显式调用此接口才会跑，不会在 maintenance 中自动触发。
    """
    try:
        return await evaluate_turn(db, turn_id)
    except TurnJudgeError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get("/turns/{turn_id}/evaluations", response_model=list[TurnEvaluationRead])
def list_turn_evaluations(
    turn_id: UUID,
    db: Session = DB_DEPENDENCY,
) -> list[TurnEvaluation]:
    """一个 turn 的所有历史评分（一个 turn 可以多次评，便于对比 prompt 改动）。"""
    stmt = (
        select(TurnEvaluation)
        .where(TurnEvaluation.turn_id == turn_id)
        .order_by(TurnEvaluation.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.get("/games/{game_id}/evaluations", response_model=list[TurnEvaluationRead])
def list_game_evaluations(
    game_id: UUID,
    db: Session = DB_DEPENDENCY,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[TurnEvaluation]:
    """一个游戏最近 N 次评分（按 created_at 倒序）。"""
    stmt = (
        select(TurnEvaluation)
        .where(TurnEvaluation.game_id == game_id)
        .order_by(TurnEvaluation.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


class RecentTurnStats(BaseModel):
    """最近 N 回合的 telemetry + 评分聚合。"""

    sample_size: int
    director_fallback_count: int
    director_fallback_rate: float
    rewrite_count: int
    rewrite_rate: float
    extractor_failed_count: int
    extractor_failed_rate: float
    drift_severity_distribution: dict[str, int]
    avg_overall_score: float | None
    evaluations_count: int
    avg_latency_ms_by_agent: dict[str, float]


@router.get("/stats/recent-turns", response_model=RecentTurnStats)
def stats_recent_turns(
    db: Session = DB_DEPENDENCY,
    limit: int = Query(default=100, ge=1, le=500),
) -> RecentTurnStats:
    """聚合最近 N 个已完成 turn job 的 telemetry，以及对应回合的评分均值。"""
    # 1. 最近 N 个 completed turn job
    jobs = list(
        db.scalars(
            select(TurnJob)
            .where(TurnJob.status == "completed")
            .order_by(TurnJob.created_at.desc())
            .limit(limit)
        ).all()
    )
    sample_size = len(jobs)
    if sample_size == 0:
        return RecentTurnStats(
            sample_size=0,
            director_fallback_count=0,
            director_fallback_rate=0.0,
            rewrite_count=0,
            rewrite_rate=0.0,
            extractor_failed_count=0,
            extractor_failed_rate=0.0,
            drift_severity_distribution={},
            avg_overall_score=None,
            evaluations_count=0,
            avg_latency_ms_by_agent={},
        )

    director_fallback = sum(1 for j in jobs if j.director_used_fallback)
    rewrite = sum(1 for j in jobs if j.rewrite_triggered)
    extractor_failed = sum(1 for j in jobs if j.extractor_failed)

    severity_dist: dict[str, int] = {}
    for j in jobs:
        key = j.drift_severity or "skipped"
        severity_dist[key] = severity_dist.get(key, 0) + 1

    # 2. 对应回合的评分均值
    turn_ids = [j.turn_id for j in jobs if j.turn_id]
    avg_score: float | None = None
    evaluations_count = 0
    if turn_ids:
        score_row = db.execute(
            select(
                func.avg(TurnEvaluation.overall_score),
                func.count(TurnEvaluation.id),
            ).where(
                TurnEvaluation.turn_id.in_(turn_ids),
                TurnEvaluation.status == "success",
            )
        ).first()
        if score_row is not None:
            avg_raw, count_raw = score_row
            evaluations_count = int(count_raw or 0)
            avg_score = float(avg_raw) if avg_raw is not None else None

    # 3. 这些 turn job 关联的 LLM 调用 latency 均值（按 agent）
    job_ids = [j.id for j in jobs]
    latency_rows = db.execute(
        select(
            AgentTrace.agent,
            func.avg(AgentTrace.latency_ms),
        ).where(
            AgentTrace.job_kind == "turn",
            AgentTrace.job_id.in_(job_ids),
            AgentTrace.status == "success",
        ).group_by(AgentTrace.agent)
    ).all()
    avg_latency: dict[str, float] = {
        agent: round(float(avg or 0), 1) for agent, avg in latency_rows
    }

    return RecentTurnStats(
        sample_size=sample_size,
        director_fallback_count=director_fallback,
        director_fallback_rate=round(director_fallback / sample_size, 4),
        rewrite_count=rewrite,
        rewrite_rate=round(rewrite / sample_size, 4),
        extractor_failed_count=extractor_failed,
        extractor_failed_rate=round(extractor_failed / sample_size, 4),
        drift_severity_distribution=severity_dist,
        avg_overall_score=round(avg_score, 3) if avg_score is not None else None,
        evaluations_count=evaluations_count,
        avg_latency_ms_by_agent=avg_latency,
    )


@router.get("/golden", response_model=list[AgentTraceSummary])
def list_golden_traces(
    db: Session = DB_DEPENDENCY,
    label: str | None = Query(default=None, description="good/bad/neutral，空=全部"),
    agent: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AgentTrace]:
    """返回已被 `scripts/label_trace.py` 标记的 golden 集合。

    label / note 写在 `extras` JSONB 字段，所以用 JSON 操作符查询。
    """
    stmt = select(AgentTrace).order_by(AgentTrace.created_at.desc()).limit(limit)
    # extras->>'label' IS NOT NULL  /  extras->>'label' = :label
    if label is not None:
        stmt = stmt.where(AgentTrace.extras["label"].astext == label)
    else:
        stmt = stmt.where(AgentTrace.extras["label"].astext.isnot(None))
    if agent is not None:
        stmt = stmt.where(AgentTrace.agent == agent)
    return list(db.scalars(stmt).all())
