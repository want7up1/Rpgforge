"""LLM 调用 trace 落库。

设计要点：
- 当前 job 的关联信息（job_kind / job_id）通过 contextvar 传递，避免每个 Agent 都
  显式传 trace_context。RQ worker 用 asyncio.run() 跑单个 async 任务，contextvar
  在同一个 event loop 内自然传播。
- `record_trace` 同步开短事务写库（~3ms），不阻塞流式回复。如果以后写入压力大
  再改异步队列。
- trace 写入失败**不能让主回合失败**。所有异常吞掉只 warning。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.db.session import SessionLocal
from app.models.agent_trace import AgentTrace

logger = logging.getLogger(__name__)

# Agent → 人类可读名字（仅用于 trace 的 agent 字段；task_type 仍保留原 routing key）
AGENT_LABEL: dict[str, str] = {
    "story_director": "story_director",
    "drift_validator": "drift_validator",
    "state_delta_extract": "state_extractor",
    "compress_context": "context_compressor",
    "gm_runtime": "gm_runtime",
    "gm_runtime_rewrite": "gm_runtime_rewrite",
    "generator_interview": "generator_interview",
    "generate_config_outline": "generator_outline",
    "generate_config_section": "generator_section",
    "turn_judge": "turn_judge",
}


@dataclass(frozen=True)
class TraceContext:
    job_kind: str  # "turn" | "generator_chat" | "generator_finalize"
    job_id: UUID


_current: ContextVar[TraceContext | None] = ContextVar("agent_trace_ctx", default=None)


def set_trace_context(job_kind: str, job_id: UUID) -> None:
    """RQ async 任务入口调用一次。无需 reset：worker 任务结束后 contextvar 随之释放。"""
    _current.set(TraceContext(job_kind=job_kind, job_id=job_id))


def clear_trace_context() -> None:
    _current.set(None)


def current_trace_context() -> TraceContext | None:
    return _current.get()


def record_trace(
    *,
    task_type: str,
    model: str | None,
    prompt_messages: list[dict[str, Any]] | None,
    output_text: str | None,
    reasoning_text: str | None,
    latency_ms: int,
    status: str,
    error_message: str | None = None,
    tokens_input: int | None = None,
    tokens_output: int | None = None,
    tokens_reasoning: int | None = None,
    extras: dict[str, Any] | None = None,
) -> None:
    """同步把一次 LLM 调用写入 agent_traces。失败不抛错。"""
    ctx = current_trace_context()
    agent = AGENT_LABEL.get(task_type, task_type)
    try:
        with SessionLocal() as db:
            trace = AgentTrace(
                job_kind=ctx.job_kind if ctx else None,
                job_id=ctx.job_id if ctx else None,
                agent=agent,
                task_type=task_type,
                model=model,
                prompt_messages=prompt_messages,
                output_text=output_text,
                reasoning_text=reasoning_text,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                tokens_reasoning=tokens_reasoning,
                latency_ms=latency_ms,
                status=status,
                error_message=error_message[:4000] if error_message else None,
                extras=extras,
            )
            db.add(trace)
            db.commit()
    except Exception as exc:  # noqa: BLE001
        # trace 失败绝不能影响主回合
        logger.warning("Agent trace write failed (agent=%s, status=%s): %s", agent, status, exc)


def extract_usage(raw: dict[str, Any] | None) -> tuple[int | None, int | None, int | None]:
    """从 DeepSeek 响应 raw dict 抽 token usage。"""
    if not isinstance(raw, dict):
        return (None, None, None)
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        return (None, None, None)
    tokens_input = _int_or_none(usage.get("prompt_tokens"))
    tokens_output = _int_or_none(usage.get("completion_tokens"))
    # DeepSeek 可能把 reasoning tokens 单独放在 completion_tokens_details.reasoning_tokens
    tokens_reasoning: int | None = None
    details = usage.get("completion_tokens_details")
    if isinstance(details, dict):
        tokens_reasoning = _int_or_none(details.get("reasoning_tokens"))
    return (tokens_input, tokens_output, tokens_reasoning)


def extract_cache_usage(raw: dict[str, Any] | None) -> tuple[int | None, int | None]:
    """从 DeepSeek 响应抽 prefix cache 命中/未命中 token（DeepSeek 官方自动缓存特性）。

    命中部分 input 计费约为未命中的 1/10，是省 token 的核心杠杆（见
    docs/PROMPT_ARCHITECTURE_REDESIGN.md 阶段 2）。返回 (cache_hit, cache_miss)。
    """
    if not isinstance(raw, dict):
        return (None, None)
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        return (None, None)
    return (
        _int_or_none(usage.get("prompt_cache_hit_tokens")),
        _int_or_none(usage.get("prompt_cache_miss_tokens")),
    )


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
