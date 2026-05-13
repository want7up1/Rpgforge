import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.models.game import Game
from app.models.turn import Turn
from app.services.json_utils import parse_json_object
from app.services.model_router import ModelRouter
from app.services.prompt_builder import PromptBuilder
from app.services.prompt_loader import load_prompt_template
from app.services.story_blueprint import build_story_blueprint


class StateDeltaExtraction(BaseModel):
    time_delta: str | None = None
    time_current: str | None = None
    location_change: str | dict[str, Any] | None = None
    inventory_add: list[Any] = Field(default_factory=list)
    inventory_remove: list[Any] = Field(default_factory=list)
    npc_updates: list[Any] = Field(default_factory=list)
    quest_updates: list[Any] = Field(default_factory=list)
    faction_updates: list[Any] = Field(default_factory=list)
    protagonist_updates: dict[str, Any] = Field(default_factory=dict)
    variable_updates: dict[str, Any] = Field(default_factory=dict)
    new_lore_candidates: list[Any] = Field(default_factory=list)
    new_known_facts: list[Any] = Field(default_factory=list)
    new_hidden_facts: list[Any] = Field(default_factory=list)
    open_thread_updates: list[Any] = Field(default_factory=list)
    xp_events: list[Any] = Field(default_factory=list)
    skill_events: list[Any] = Field(default_factory=list)
    ability_updates: list[Any] = Field(default_factory=list)
    condition_updates: list[Any] = Field(default_factory=list)
    relationship_events: list[Any] = Field(default_factory=list)

    @field_validator(
        "inventory_add",
        "inventory_remove",
        "npc_updates",
        "quest_updates",
        "faction_updates",
        "new_lore_candidates",
        "new_known_facts",
        "new_hidden_facts",
        "open_thread_updates",
        "xp_events",
        "skill_events",
        "ability_updates",
        "condition_updates",
        "relationship_events",
        mode="before",
    )
    @classmethod
    def coerce_list(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]


class StateExtractorValidationError(RuntimeError):
    pass


class StateExtractor:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    async def extract(self, game: Game, turn: Turn) -> dict[str, Any]:
        current_state = game.state.state_json if game.state else {}
        payload = {
            "game": {
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
            },
            "campaign_contract": PromptBuilder._campaign_contract_payload(game.config),
            "story_blueprint": build_story_blueprint(game.config),
            "current_state": current_state,
            "turn": {
                "turn_number": turn.turn_number,
                "player_input": turn.player_input,
                "gm_output": turn.gm_output,
                "visible_summary": turn.visible_summary,
            },
        }
        messages = [
            {"role": "system", "content": load_prompt_template("extract_state_delta.md")},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]
        result = await self.router.use_flash(
            "state_delta_extract",
            messages,
            json_mode=True,
            max_tokens=4096,
            reasoning_effort=None,
            respect_route=False,
        )
        try:
            parsed = parse_json_object(result.content)
            return StateDeltaExtraction.model_validate(parsed).model_dump()
        except (ValueError, ValidationError) as exc:
            raise StateExtractorValidationError(str(exc)) from exc
