#!/usr/bin/env python
"""重放 agent_traces 中的历史 LLM 调用，对比旧/新输出。

用法（在 api/ 目录或 docker compose exec api 内执行）：

    python -m scripts.replay_trace --trace-id <UUID>
    python -m scripts.replay_trace --turn-job-id <UUID>
    python -m scripts.replay_trace --turn-job-id <UUID> --agent gm_runtime

设计：
- 直接读 agent_traces 的 prompt_messages，用当前 ModelRouter 重发请求。
- replay 的新调用本身也会被 ModelRouter 写入 agent_traces，但归到一个独立的
  job_kind="replay" UUID 下，方便后续过滤。
- 流式调用不支持重放（DeepSeek API 端无幂等概念，且 stream 没有 token usage）；
  脚本只重放非流式 status="success" 的 trace。GM 流式调用的 trace 也能跑，会用
  非流式接口重新请求。
- 输出：unified diff（旧 vs 新 output_text）+ 长度/latency/token 对比表。

不烧 quota 提示：每次 replay 会向 DeepSeek 发真实请求。重放前会显示 trace 数量
和 task_type 分布让你确认。
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import sys
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select

# 允许直接 python -m scripts.replay_trace 或 python scripts/replay_trace.py
sys.path.insert(0, ".")

from app.db.session import SessionLocal  # noqa: E402
from app.models.agent_trace import AgentTrace  # noqa: E402
from app.services.agent_traces import set_trace_context  # noqa: E402
from app.services.deepseek_client import DeepSeekClient, DeepSeekError  # noqa: E402
from app.services.model_router import ModelRouter  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay historical agent_traces.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--trace-id", type=str, help="重放单条 trace")
    group.add_argument("--turn-job-id", type=str, help="重放一个回合下所有成功的 trace")
    parser.add_argument(
        "--agent",
        type=str,
        default=None,
        help="只重放某个 agent（如 gm_runtime / drift_validator）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多重放多少条（防止误操作）",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="跳过确认提示",
    )
    return parser.parse_args()


def _load_traces(args: argparse.Namespace) -> list[AgentTrace]:
    with SessionLocal() as db:
        stmt = select(AgentTrace).where(AgentTrace.status == "success")
        if args.trace_id:
            stmt = stmt.where(AgentTrace.id == UUID(args.trace_id))
        elif args.turn_job_id:
            stmt = stmt.where(
                AgentTrace.job_kind == "turn",
                AgentTrace.job_id == UUID(args.turn_job_id),
            )
        if args.agent:
            stmt = stmt.where(AgentTrace.agent == args.agent)
        stmt = stmt.order_by(AgentTrace.created_at.asc())
        if args.limit:
            stmt = stmt.limit(args.limit)
        return list(db.scalars(stmt).all())


def _summarize(traces: list[AgentTrace]) -> str:
    agents: dict[str, int] = {}
    for t in traces:
        agents[t.agent] = agents.get(t.agent, 0) + 1
    parts = [f"{k}={v}" for k, v in sorted(agents.items())]
    return f"{len(traces)} traces: {', '.join(parts)}"


async def _replay_one(trace: AgentTrace) -> dict[str, Any]:
    """对一条 trace 用非流式接口重发请求，返回对比信息。"""
    if not trace.prompt_messages:
        return {"trace_id": trace.id, "status": "skipped", "reason": "no prompt"}
    router = ModelRouter()
    start = monotonic()
    try:
        # 使用非流式调用复现：即使原始是流式（GM）也能拿到完整 output，便于对比。
        if trace.task_type in {"gm_runtime", "gm_runtime_rewrite"}:
            result = await router.use_pro(
                trace.task_type,
                trace.prompt_messages,
                json_mode=True,
                max_tokens=(trace.extras or {}).get("max_tokens") or 12000,
            )
        else:
            result = await router.use_flash(
                trace.task_type,
                trace.prompt_messages,
                json_mode=True,
                max_tokens=(trace.extras or {}).get("max_tokens") or 4096,
            )
    except DeepSeekError as exc:
        return {
            "trace_id": trace.id,
            "agent": trace.agent,
            "status": "error",
            "error": str(exc),
            "latency_ms": int((monotonic() - start) * 1000),
        }
    new_latency = int((monotonic() - start) * 1000)
    new_text = result.content
    old_text = trace.output_text or ""

    diff = "\n".join(
        difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            lineterm="",
            fromfile=f"old@{trace.id}",
            tofile="new",
            n=2,
        )
    )

    return {
        "trace_id": str(trace.id),
        "agent": trace.agent,
        "task_type": trace.task_type,
        "old_len": len(old_text),
        "new_len": len(new_text),
        "old_latency_ms": trace.latency_ms,
        "new_latency_ms": new_latency,
        "old_model": trace.model,
        "new_model": result.model,
        "status": "ok",
        "diff": diff if diff else "(identical)",
    }


def _print_result(result: dict[str, Any]) -> None:
    print("=" * 72)
    print(f"trace {result['trace_id']}  agent={result.get('agent')}")
    if result.get("status") == "error":
        print(f"  ERROR: {result['error']}")
        return
    if result.get("status") == "skipped":
        print(f"  SKIPPED: {result.get('reason')}")
        return
    print(
        f"  model: {result['old_model']} -> {result['new_model']}"
        f"   latency: {result['old_latency_ms']}ms -> {result['new_latency_ms']}ms"
        f"   length: {result['old_len']} -> {result['new_len']} chars"
    )
    if result["diff"] == "(identical)":
        print("  diff: identical")
    else:
        print("  diff (preview, first 60 lines):")
        for line in result["diff"].splitlines()[:60]:
            print(f"    {line}")
        extra = max(0, len(result["diff"].splitlines()) - 60)
        if extra:
            print(f"    ... and {extra} more lines")


async def main_async(args: argparse.Namespace) -> int:
    traces = _load_traces(args)
    if not traces:
        print("No matching traces.", file=sys.stderr)
        return 1
    print(_summarize(traces))
    if not args.yes:
        try:
            ans = input("Send these replays to DeepSeek? [y/N] ").strip().lower()
        except EOFError:
            ans = ""
        if ans != "y":
            print("Aborted.")
            return 0

    # replay 的所有新 trace 都归到一个独立的 replay session 下，避免污染生产数据视图。
    replay_session = uuid4()
    set_trace_context("replay", replay_session)
    print(f"replay session: {replay_session}")

    for trace in traces:
        result = await _replay_one(trace)
        _print_result(result)

    return 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
