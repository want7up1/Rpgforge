#!/usr/bin/env python
"""对比两条历史 trace 的 prompt / output。不发新请求，不烧 API quota。

典型用法：
    # 改 prompt 前跑一遍取得 trace A，改 prompt 后跑取得 trace B，对比：
    python -m scripts.diff_traces --left <UUID_A> --right <UUID_B>

    # 按 agent 取最近两条，看是否漂移：
    python -m scripts.diff_traces --agent drift_validator --last 2
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from uuid import UUID

from sqlalchemy import select

sys.path.insert(0, ".")

from app.db.session import SessionLocal  # noqa: E402
from app.models.agent_trace import AgentTrace  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Diff two historical agent_traces.")
    p.add_argument("--left", type=str, help="左侧 trace_id")
    p.add_argument("--right", type=str, help="右侧 trace_id")
    p.add_argument(
        "--agent",
        type=str,
        help="取该 agent 最近 N 条按时间正序对比（与 --last 配合）",
    )
    p.add_argument("--last", type=int, default=2, help="--agent 模式下取最近几条")
    p.add_argument(
        "--show-prompt",
        action="store_true",
        help="也输出 prompt_messages diff（默认只比 output）",
    )
    return p.parse_args()


def _by_id(trace_id: str) -> AgentTrace:
    with SessionLocal() as db:
        row = db.get(AgentTrace, UUID(trace_id))
        if row is None:
            raise SystemExit(f"trace {trace_id} not found")
        return row


def _last_by_agent(agent: str, n: int) -> list[AgentTrace]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(AgentTrace)
                .where(AgentTrace.agent == agent, AgentTrace.status == "success")
                .order_by(AgentTrace.created_at.desc())
                .limit(n)
            ).all()
        )[::-1]


def _diff(a: str, b: str, label_a: str, label_b: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            (a or "").splitlines(),
            (b or "").splitlines(),
            fromfile=label_a,
            tofile=label_b,
            lineterm="",
            n=2,
        )
    )


def _diff_two(left: AgentTrace, right: AgentTrace, show_prompt: bool) -> None:
    print(f"left  : {left.id}  {left.created_at}  {left.model}  agent={left.agent}")
    print(f"right : {right.id}  {right.created_at}  {right.model}  agent={right.agent}")
    print(
        f"latency: {left.latency_ms}ms -> {right.latency_ms}ms"
        f"   tokens(in/out): "
        f"{left.tokens_input or '-'}/{left.tokens_output or '-'} -> "
        f"{right.tokens_input or '-'}/{right.tokens_output or '-'}"
    )

    if show_prompt:
        print("\n--- prompt_messages diff ---")
        left_p = json.dumps(left.prompt_messages or [], ensure_ascii=False, indent=2)
        right_p = json.dumps(right.prompt_messages or [], ensure_ascii=False, indent=2)
        prompt_diff = _diff(left_p, right_p, "left.prompt", "right.prompt")
        print(prompt_diff or "(identical)")

    print("\n--- output_text diff ---")
    out_diff = _diff(left.output_text or "", right.output_text or "", "left.out", "right.out")
    if not out_diff:
        print("(identical)")
        return
    for line in out_diff.splitlines()[:200]:
        print(line)
    extra = max(0, len(out_diff.splitlines()) - 200)
    if extra:
        print(f"... and {extra} more lines")


def main() -> int:
    args = _parse_args()
    if args.left and args.right:
        left = _by_id(args.left)
        right = _by_id(args.right)
        _diff_two(left, right, args.show_prompt)
        return 0
    if args.agent:
        traces = _last_by_agent(args.agent, args.last)
        if len(traces) < 2:
            print(f"need at least 2 traces for agent={args.agent}", file=sys.stderr)
            return 1
        for i in range(len(traces) - 1):
            print(f"\n==== pair {i + 1} ====")
            _diff_two(traces[i], traces[i + 1], args.show_prompt)
        return 0
    print("Provide --left/--right or --agent.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
