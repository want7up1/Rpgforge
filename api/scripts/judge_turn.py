#!/usr/bin/env python
"""手动触发 LLM-as-Judge 对指定回合打分。

用法（docker compose exec api 内）：
    python -m scripts.judge_turn --turn-id <UUID>
    python -m scripts.judge_turn --game-id <UUID> --last 5    # 评最近 5 个回合
    python -m scripts.judge_turn --game-id <UUID> --all       # 评所有回合（慎用，烧 quota）

每次评分消耗一次 Pro LLM 调用。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

from sqlalchemy import select

sys.path.insert(0, ".")

from app.db.session import SessionLocal  # noqa: E402
from app.models.turn import Turn  # noqa: E402
from app.services.turn_judge import TurnJudgeError, evaluate_turn  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Manually evaluate turns with LLM-as-Judge.")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--turn-id", type=str)
    group.add_argument("--game-id", type=str)
    p.add_argument(
        "--last",
        type=int,
        default=1,
        help="--game-id 模式下评最近 N 个回合（默认 1）",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="--game-id 模式下评所有回合（覆盖 --last）",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="跳过确认提示",
    )
    return p.parse_args()


def _resolve_turn_ids(args: argparse.Namespace) -> list[UUID]:
    if args.turn_id:
        return [UUID(args.turn_id)]
    with SessionLocal() as db:
        stmt = (
            select(Turn.id)
            .where(Turn.game_id == UUID(args.game_id))
            .order_by(Turn.turn_number.desc())
        )
        if not args.all:
            stmt = stmt.limit(args.last)
        ids = list(db.scalars(stmt).all())
        return list(reversed(ids))


async def main_async(args: argparse.Namespace) -> int:
    turn_ids = _resolve_turn_ids(args)
    if not turn_ids:
        print("No matching turns.", file=sys.stderr)
        return 1
    print(f"will evaluate {len(turn_ids)} turn(s); this calls DeepSeek Pro per turn.")
    if not args.yes:
        try:
            ans = input("Proceed? [y/N] ").strip().lower()
        except EOFError:
            ans = ""
        if ans != "y":
            print("Aborted.")
            return 0

    for turn_id in turn_ids:
        with SessionLocal() as db:
            try:
                evaluation = await evaluate_turn(db, turn_id)
            except TurnJudgeError as exc:
                print(f"turn {turn_id}: ERROR {exc}")
                continue
        if evaluation.status != "success":
            print(f"turn {turn_id}: status={evaluation.status}  err={evaluation.error_message}")
            continue
        print(
            f"turn {turn_id}: overall={evaluation.overall_score}  "
            f"canon={evaluation.canon_fidelity} state={evaluation.state_consistency} "
            f"pacing={evaluation.pacing} prose={evaluation.prose_quality} "
            f"fresh={evaluation.freshness} safety={evaluation.safety}"
        )

    return 0


def main() -> int:
    return asyncio.run(main_async(_parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
