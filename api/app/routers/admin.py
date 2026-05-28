"""Admin-only read endpoints.

需要 `X-Settings-Admin-Token` header 才能访问（生产模式如果未配置 token 会拒绝）。
当前只暴露 LLM trace 查询，方便排查 AI 链路问题。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.agent_trace import AgentTrace
from app.routers.settings import verify_settings_token

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
    *,
    job_id: UUID | None = Query(default=None, description="按上游 job_id 过滤"),
    job_kind: str | None = Query(default=None, description="turn / generator_chat / generator_finalize"),
    agent: str | None = Query(default=None, description="按 agent 名字过滤"),
    status_eq: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
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
        from fastapi import HTTPException, status as http_status

        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Trace not found.")
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
