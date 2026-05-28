"""LLM-as-Judge：对单回合 GM 输出按 6 个维度打分。

设计要点：
- 用 Pro 模型（评分需要推理）。可通过 task_model_routes["turn_judge"] 切换。
- 默认 opt-in，不在 maintenance 中自动跑。通过 admin endpoint 或 CLI 触发。
- 每次评分调用本身也是一条 agent_traces 记录（ModelRouter 自动写）。我们再把结果
  汇总到 turn_evaluations 表，并把 trace_id 回填。
"""

from __future__ import annotations

import asyncio
import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.turn import Turn
from app.models.turn_evaluation import TurnEvaluation
from app.services.agent_traces import current_trace_context, set_trace_context
from app.services.deepseek_client import DeepSeekError
from app.services.json_utils import parse_json_object
from app.services.model_router import ModelRouter
from app.services.prompt_loader import load_prompt_template
from app.services.state_v2 import state_v2_view
from app.services.story_settings import build_runtime_story

logger = logging.getLogger(__name__)

TURN_JUDGE_TIMEOUT_SECONDS = 120.0
DIMENSIONS = (
    "canon_fidelity",
    "state_consistency",
    "pacing",
    "prose_quality",
    "freshness",
    "safety",
)


class JudgeResult(BaseModel):
    canon_fidelity: int | None = None
    state_consistency: int | None = None
    pacing: int | None = None
    prose_quality: int | None = None
    freshness: int | None = None
    safety: int | None = None
    overall_score: float | None = None
    rationale: dict[str, str] = Field(default_factory=dict)

    @field_validator(
        "canon_fidelity",
        "state_consistency",
        "pacing",
        "prose_quality",
        "freshness",
        "safety",
        mode="before",
    )
    @classmethod
    def clamp(cls, value: Any) -> int | None:
        if value is None:
            return None
        try:
            v = int(value)
        except (TypeError, ValueError):
            return None
        return max(1, min(5, v))


class TurnJudgeError(RuntimeError):
    pass


class TurnJudge:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    async def judge(self, game: Game, turn: Turn, prev_turn: Turn | None = None) -> JudgeResult:
        payload = self._payload(game, turn, prev_turn)
        messages = [
            {"role": "system", "content": load_prompt_template("turn_judge.md")},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]
        try:
            result = await asyncio.wait_for(
                self.router.use_pro(
                    "turn_judge",
                    messages,
                    json_mode=True,
                    max_tokens=1200,
                ),
                timeout=TURN_JUDGE_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise TurnJudgeError(
                f"Turn judge timed out after {int(TURN_JUDGE_TIMEOUT_SECONDS)}s."
            ) from exc
        except DeepSeekError as exc:
            raise TurnJudgeError(str(exc)) from exc

        try:
            parsed = parse_json_object(result.content)
            judge_result = JudgeResult.model_validate(parsed)
        except (ValueError, ValidationError) as exc:
            raise TurnJudgeError(f"Failed to parse judge output: {exc}") from exc

        # 如果模型没给 overall_score 或给的不对，用 6 维平均值兜底。
        scores = [
            getattr(judge_result, d)
            for d in DIMENSIONS
            if getattr(judge_result, d) is not None
        ]
        overall = judge_result.overall_score
        if scores and (overall is None or not _is_valid_overall(overall)):
            judge_result.overall_score = round(sum(scores) / len(scores), 2)

        return judge_result

    def _payload(self, game: Game, turn: Turn, prev_turn: Turn | None) -> dict[str, Any]:
        state_json = game.state.state_json if game.state else {}
        payload: dict[str, Any] = {
            "game": {
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
            },
            "runtime_story": build_runtime_story(game.config, state_json),
            "current_state_v2": state_v2_view(state_json),
            "turn": {
                "turn_number": turn.turn_number,
                "player_input": turn.player_input,
                "narrative": turn.gm_output,
                "visible_summary": turn.visible_summary,
                "action_options": turn.action_options_json,
            },
        }
        if prev_turn is not None:
            payload["previous_turn"] = {
                "turn_number": prev_turn.turn_number,
                "player_input": prev_turn.player_input,
                "narrative": prev_turn.gm_output,
            }
        return payload


def _is_valid_overall(value: Any) -> bool:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return 1.0 <= v <= 5.0


async def evaluate_turn(
    db: Session,
    turn_id: UUID,
    *,
    judge: TurnJudge | None = None,
) -> TurnEvaluation:
    """对指定 turn 跑 judge，把结果写入 turn_evaluations 并返回。

    无论 judge 成功还是失败都写一行：status="success" 或 "error"。
    """
    turn = db.get(Turn, turn_id)
    if turn is None:
        raise TurnJudgeError(f"Turn {turn_id} not found.")
    game = db.get(Game, turn.game_id)
    if game is None:
        raise TurnJudgeError(f"Game {turn.game_id} not found.")
    prev_turn = (
        db.scalars(
            select(Turn)
            .where(Turn.game_id == turn.game_id, Turn.turn_number == turn.turn_number - 1)
            .limit(1)
        ).first()
        if turn.turn_number > 1
        else None
    )

    judge_impl = judge or TurnJudge()

    # 用一个新的 trace context，让 judge 调用的 agent_trace 归到 job_kind="judge"，
    # 不会被算进原回合的 turn job 视图里。
    set_trace_context("judge", turn.id)

    evaluation = TurnEvaluation(
        turn_id=turn.id,
        game_id=turn.game_id,
    )
    try:
        result = await judge_impl.judge(game, turn, prev_turn)
        evaluation.canon_fidelity = result.canon_fidelity
        evaluation.state_consistency = result.state_consistency
        evaluation.pacing = result.pacing
        evaluation.prose_quality = result.prose_quality
        evaluation.freshness = result.freshness
        evaluation.safety = result.safety
        evaluation.overall_score = (
            Decimal(str(result.overall_score)) if result.overall_score is not None else None
        )
        evaluation.rationale = result.rationale or None
        evaluation.status = "success"
    except TurnJudgeError as exc:
        logger.warning("Turn judge failed for turn %s: %s", turn.id, exc)
        evaluation.status = "error"
        evaluation.error_message = str(exc)[:4000]

    # 关联本次 judge 调用的 trace（最近一次 task_type=turn_judge 的成功调用）
    from app.models.agent_trace import AgentTrace

    last_trace = db.scalars(
        select(AgentTrace)
        .where(AgentTrace.task_type == "turn_judge", AgentTrace.job_id == turn.id)
        .order_by(AgentTrace.created_at.desc())
        .limit(1)
    ).first()
    if last_trace is not None:
        evaluation.trace_id = last_trace.id
        evaluation.judge_model = last_trace.model

    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)

    # 复位 trace context，避免污染调用方后续逻辑
    ctx = current_trace_context()
    if ctx and ctx.job_kind == "judge" and ctx.job_id == turn.id:
        from app.services.agent_traces import clear_trace_context

        clear_trace_context()

    return evaluation
