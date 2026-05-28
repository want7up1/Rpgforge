import asyncio
import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.models.game import Game
from app.models.turn import Turn
from app.services.json_utils import parse_json_object
from app.services.model_router import ModelRouter
from app.services.prompt_loader import load_prompt_template
from app.services.story_settings import build_runtime_story

STATE_EXTRACTOR_TIMEOUT_SECONDS = 150.0


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
    story_progress_update: dict[str, Any] = Field(default_factory=dict)

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

    @field_validator("story_progress_update", mode="before")
    @classmethod
    def coerce_mapping(cls, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}


class StateExtractorValidationError(RuntimeError):
    pass


class StateExtractor:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    async def extract(
        self,
        game: Game,
        turn: Turn,
        director_decision: dict[str, Any] | None = None,
        drift_findings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current_state = game.state.state_json if game.state else {}
        payload: dict[str, Any] = {
            "game": {
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
            },
            "runtime_story": build_runtime_story(game.config, current_state),
            "current_state": current_state,
            "turn": {
                "turn_number": turn.turn_number,
                "player_input": turn.player_input,
                "gm_output": turn.gm_output,
                "visible_summary": turn.visible_summary,
            },
        }
        # 上游 Director / Drift 的提示信号：让 extractor 重点关注它们提到的连续性/冲突项。
        director_hints = _director_hints(director_decision)
        if director_hints:
            payload["director_hints"] = director_hints
        drift_hints = _drift_hints(drift_findings)
        if drift_hints:
            payload["drift_hints"] = drift_hints
        messages = [
            {"role": "system", "content": load_prompt_template("extract_state_delta.md")},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]
        try:
            result = await asyncio.wait_for(
                self.router.use_flash(
                    "state_delta_extract",
                    messages,
                    json_mode=True,
                    max_tokens=4096,
                    reasoning_effort=None,
                    respect_route=False,
                ),
                timeout=STATE_EXTRACTOR_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise StateExtractorValidationError(
                f"状态提取超过 {int(STATE_EXTRACTOR_TIMEOUT_SECONDS)} 秒。"
            ) from exc
        try:
            parsed = parse_json_object(result.content)
            return StateDeltaExtraction.model_validate(parsed).model_dump()
        except (ValueError, ValidationError) as exc:
            raise StateExtractorValidationError(str(exc)) from exc


def _director_hints(decision: dict[str, Any] | None) -> dict[str, Any]:
    """从 director_decision 抽 extractor 实际能用上的提示字段。"""
    if not isinstance(decision, dict):
        return {}
    hints: dict[str, Any] = {}
    for key in ("continuity_notes", "active_material_titles", "forbidden_reveals"):
        value = decision.get(key)
        if isinstance(value, list) and value:
            hints[key] = value
    for key in ("scene_objective", "current_act", "pacing_limit"):
        value = decision.get(key)
        if isinstance(value, str) and value.strip():
            hints[key] = value
    return hints


def _drift_hints(findings: dict[str, Any] | None) -> dict[str, Any]:
    """从 drift_validation 抽 extractor 需要关注的状态冲突。"""
    if not isinstance(findings, dict):
        return {}
    hints: dict[str, Any] = {}
    for key in ("state_conflicts", "contract_violations", "issues"):
        value = findings.get(key)
        if isinstance(value, list) and value:
            hints[key] = value
    severity = findings.get("severity")
    if isinstance(severity, str) and severity.strip():
        hints["severity"] = severity
    return hints
