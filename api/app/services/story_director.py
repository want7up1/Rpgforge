from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.models.game import Game
from app.models.mode import Mode
from app.models.turn import Turn
from app.services.deepseek_client import DeepSeekError
from app.services.json_utils import parse_json_object
from app.services.lore_retriever import LoreRetrievalResult
from app.services.model_router import ModelRouter
from app.services.prompt_builder import PromptBuilder
from app.services.prompt_loader import load_prompt_template
from app.services.state_v2 import state_v2_view

logger = logging.getLogger(__name__)


class StoryDirectorDecision(BaseModel):
    player_intent: str = ""
    current_act: str = ""
    scene_objective: str = ""
    mode_recommendation: str = ""
    active_lore_titles: list[str] = Field(default_factory=list)
    allowed_reveals: list[str] = Field(default_factory=list)
    forbidden_reveals: list[str] = Field(default_factory=list)
    pacing_limit: str = ""
    continuity_notes: list[str] = Field(default_factory=list)
    gm_instruction: str = ""

    @field_validator(
        "active_lore_titles",
        "allowed_reveals",
        "forbidden_reveals",
        "continuity_notes",
        mode="before",
    )
    @classmethod
    def coerce_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value if str(item or "").strip()]
        return [str(value)]


class StoryDirector:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    async def plan(
        self,
        *,
        game: Game,
        player_input: str,
        selected_mode: Mode | None,
        recent_turns: list[Turn],
        related_lore: list[LoreRetrievalResult],
        summaries: dict[str, Any],
    ) -> StoryDirectorDecision:
        payload = self._payload(
            game=game,
            player_input=player_input,
            selected_mode=selected_mode,
            recent_turns=recent_turns,
            related_lore=related_lore,
            summaries=summaries,
        )
        messages = [
            {"role": "system", "content": load_prompt_template("story_director.md")},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]
        try:
            result = await self.router.use_flash(
                "story_director",
                messages,
                json_mode=True,
                max_tokens=1800,
            )
            parsed = parse_json_object(result.content)
            return StoryDirectorDecision.model_validate(parsed)
        except (DeepSeekError, ValueError, ValidationError) as exc:
            logger.warning("Story director fell back for game %s: %s", game.id, exc)
            return self._fallback_decision(game, player_input, selected_mode)

    def _payload(
        self,
        *,
        game: Game,
        player_input: str,
        selected_mode: Mode | None,
        recent_turns: list[Turn],
        related_lore: list[LoreRetrievalResult],
        summaries: dict[str, Any],
    ) -> dict[str, Any]:
        config = game.config
        return {
            "game": {
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
            },
            "campaign_contract": PromptBuilder._campaign_contract_payload(config),
            "worldview": config.worldview if config else {},
            "script_outline": config.script_outline if config else {},
            "selected_mode": self._mode_payload(selected_mode),
            "current_state_v2": state_v2_view(game.state.state_json if game.state else {}),
            "memory_summaries": summaries,
            "recent_turns": [self._turn_payload(turn) for turn in recent_turns],
            "related_lore": [
                {
                    "title": result.entry.title,
                    "type": result.entry.type,
                    "usage_note": result.entry.usage_note,
                    "retrieval": {
                        "score": result.score,
                        "matched_terms": result.matched_terms,
                    },
                }
                for result in related_lore
            ],
            "player_input": player_input,
        }

    @staticmethod
    def _mode_payload(mode: Mode | None) -> dict[str, Any] | None:
        if mode is None:
            return None
        return {
            "name": mode.name,
            "priority": mode.priority,
            "injection": mode.injection,
            "triggers": mode.triggers,
        }

    @staticmethod
    def _turn_payload(turn: Turn) -> dict[str, Any]:
        return {
            "turn_number": turn.turn_number,
            "player_input": turn.player_input,
            "gm_output": turn.gm_output,
            "visible_summary": turn.visible_summary,
            "action_options": turn.action_options_json,
        }

    @staticmethod
    def _fallback_decision(
        game: Game,
        player_input: str,
        selected_mode: Mode | None,
    ) -> StoryDirectorDecision:
        contract = PromptBuilder._campaign_contract_payload(game.config)
        return StoryDirectorDecision(
            player_intent=player_input,
            current_act=str(contract.get("current_act") or ""),
            scene_objective=str(contract.get("premise") or ""),
            mode_recommendation=selected_mode.name if selected_mode else "",
            pacing_limit="保持当前幕节奏，不提前引入未铺垫的大型势力、Boss 或终局真相。",
            gm_instruction="先回应玩家本次行动的直接结果，再推进当前幕目标。",
        )
