#!/usr/bin/env python
"""给一条 agent_trace 打标签，把它升级为 golden 用例。

标签写到 `extras.label`（good / bad / neutral）和 `extras.note`，
不需要新加表列。后续 admin endpoint 可以按 label 过滤。

用法：
    python -m scripts.label_trace <TRACE_ID> --label good --note "经典调查回合"
    python -m scripts.label_trace <TRACE_ID> --label bad --note "GM 跳过玩家行动"
    python -m scripts.label_trace <TRACE_ID> --clear
"""

from __future__ import annotations

import argparse
import sys
from uuid import UUID

sys.path.insert(0, ".")

from app.db.session import SessionLocal  # noqa: E402
from app.models.agent_trace import AgentTrace  # noqa: E402

ALLOWED_LABELS = {"good", "bad", "neutral"}


def main() -> int:
    p = argparse.ArgumentParser(description="Label an agent_trace as golden.")
    p.add_argument("trace_id", type=str)
    p.add_argument("--label", choices=sorted(ALLOWED_LABELS))
    p.add_argument("--note", type=str, default=None)
    p.add_argument("--clear", action="store_true", help="移除现有 label")
    args = p.parse_args()

    if not args.clear and not args.label:
        print("Provide --label or --clear.", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        trace = db.get(AgentTrace, UUID(args.trace_id))
        if trace is None:
            print(f"trace {args.trace_id} not found", file=sys.stderr)
            return 1
        extras = dict(trace.extras or {})
        if args.clear:
            extras.pop("label", None)
            extras.pop("note", None)
            print(f"cleared label on trace {trace.id}")
        else:
            extras["label"] = args.label
            if args.note:
                extras["note"] = args.note
            print(f"trace {trace.id} agent={trace.agent} label={args.label}")
        trace.extras = extras
        db.add(trace)
        db.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
