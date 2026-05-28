from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.models.game import Game
from app.models.turn import Turn
from app.schemas.turn import GMRuntimeOutput
from app.services.deepseek_client import DeepSeekError
from app.services.json_utils import parse_json_object
from app.services.model_router import ModelRouter
from app.services.prompt_loader import load_prompt_template
from app.services.state_v2 import state_v2_view
from app.services.story_director import StoryDirectorDecision
from app.services.story_settings import build_runtime_story

logger = logging.getLogger(__name__)

DRIFT_VALIDATOR_TIMEOUT_SECONDS = 90.0


class DriftValidationResult(BaseModel):
    approved: bool = True
    severity: str = "none"
    issues: list[str] = Field(default_factory=list)
    contract_violations: list[str] = Field(default_factory=list)
    state_conflicts: list[str] = Field(default_factory=list)
    rewrite_instruction: str = ""

    @field_validator("issues", "contract_violations", "state_conflicts", mode="before")
    @classmethod
    def coerce_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value if str(item or "").strip()]
        return [str(value)]


class DriftValidator:
    REWRITE_SEVERITIES = {"major", "critical"}

    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    async def validate(
        self,
        *,
        game: Game,
        player_input: str,
        recent_turns: list[Turn],
        director_decision: StoryDirectorDecision,
        runtime_output: GMRuntimeOutput,
        runtime_story: dict[str, Any] | None = None,
        state_v2: dict[str, Any] | None = None,
    ) -> DriftValidationResult:
        state_json = game.state.state_json if game.state else {}
        if runtime_story is None:
            runtime_story = build_runtime_story(game.config, state_json)
        if state_v2 is None:
            state_v2 = state_v2_view(state_json)
        payload = {
            "game": {
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
            },
            "runtime_story": runtime_story,
            "current_state_v2": state_v2,
            "recent_turns": [
                {
                    "turn_number": turn.turn_number,
                    "player_input": turn.player_input,
                    "gm_output": turn.gm_output,
                    "visible_summary": turn.visible_summary,
                }
                for turn in recent_turns
            ],
            "player_input": player_input,
            "story_director": director_decision.model_dump(exclude={"used_fallback"}),
            "gm_output": runtime_output.model_dump(),
        }
        messages = [
            {"role": "system", "content": load_prompt_template("drift_validator.md")},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]
        try:
            result = await asyncio.wait_for(
                self.router.use_flash(
                    "drift_validator",
                    messages,
                    json_mode=True,
                    max_tokens=1600,
                ),
                timeout=DRIFT_VALIDATOR_TIMEOUT_SECONDS,
            )
            parsed = parse_json_object(result.content)
            return DriftValidationResult.model_validate(parsed)
        except TimeoutError:
            logger.warning(
                "Drift validator timed out after %.0fs for game %s; releasing GM output.",
                DRIFT_VALIDATOR_TIMEOUT_SECONDS,
                game.id,
            )
            # approved=False + severity=unknown：不触发重写（should_rewrite 仅在
            # major/critical 时返回 True），但 telemetry 能真实反映这次校验降级。
            return DriftValidationResult(
                approved=False,
                severity="unknown",
                issues=["偏离校验超时，未能完成判定。"],
            )
        except (DeepSeekError, ValueError, ValidationError) as exc:
            logger.warning("Drift validator fell back for game %s: %s", game.id, exc)
            return DriftValidationResult(
                approved=False,
                severity="unknown",
                issues=["偏离校验失败，未能完成判定。"],
            )

    def should_rewrite(self, result: DriftValidationResult) -> bool:
        return (not result.approved) and result.severity in self.REWRITE_SEVERITIES

    @staticmethod
    def rewrite_instruction(result: DriftValidationResult) -> str:
        if result.rewrite_instruction.strip():
            return result.rewrite_instruction.strip()
        issues = result.contract_violations or result.state_conflicts or result.issues
        return "；".join(issues)
