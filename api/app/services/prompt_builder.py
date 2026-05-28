import json
from typing import Any

from app.models.game import Game
from app.models.turn import Turn
from app.schemas.turn import GMRuntimeOutput
from app.services.prompt_loader import load_prompt_template
from app.services.state_v2 import state_v2_view
from app.services.story_settings import (
    StoryMaterialResult,
    build_runtime_story,
    generation_parameters_from_config,
)


class PromptBuilder:
    def build_runtime_messages(
        self,
        *,
        game: Game,
        player_input: str,
        selected_action_style: dict[str, Any] | None,
        recent_turns: list[Turn],
        related_materials: list[StoryMaterialResult] | None = None,
        summaries: dict[str, object] | None = None,
        story_director: dict[str, object] | None = None,
        drift_rewrite_instruction: str | None = None,
        runtime_story: dict[str, Any] | None = None,
        state_v2: dict[str, Any] | None = None,
        previous_runtime_output: GMRuntimeOutput | None = None,
    ) -> list[dict[str, str]]:
        config = game.config
        game_state = game.state
        state_json = game_state.state_json if game_state else {}
        generation_parameters = generation_parameters_from_config(config)
        if runtime_story is None:
            runtime_story = build_runtime_story(
                config,
                state_json,
                selected_action_style=selected_action_style,
                related_materials=related_materials or [],
            )
        if state_v2 is None:
            state_v2 = state_v2_view(state_json)

        runtime_payload = {
            "game": {
                "id": str(game.id),
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
            },
            "generation_parameters": generation_parameters,
            "runtime_story": runtime_story,
            "selected_action_style": selected_action_style or {},
            "related_story_materials": [
                self._retrieval_payload(result) for result in (related_materials or [])
            ],
            "current_state_v2": state_v2,
            "memory_summaries": summaries or {},
            "story_director": story_director or {},
            "drift_rewrite_instruction": drift_rewrite_instruction or "",
            "previous_gm_output": (
                previous_runtime_output.model_dump() if previous_runtime_output else None
            ),
            "recent_turns": [
                self._turn_payload(turn, generation_parameters["recent_turn_excerpt_chars"])
                for turn in recent_turns
            ],
            "player_input": player_input,
        }

        return [
            {"role": "system", "content": load_prompt_template("gm_runtime.md")},
            {
                "role": "user",
                "content": json.dumps(runtime_payload, ensure_ascii=False, default=str),
            },
        ]

    def _retrieval_payload(self, result: StoryMaterialResult) -> dict[str, object]:
        payload = dict(result.material)
        payload["retrieval"] = {
            "score": result.score,
            "matched_terms": result.matched_terms,
        }
        return payload

    @staticmethod
    def _turn_payload(turn: Turn, excerpt_chars: int) -> dict[str, object]:
        return {
            "turn_number": turn.turn_number,
            "player_input": turn.player_input,
            "visible_summary": turn.visible_summary,
            "hidden_summary": turn.hidden_summary,
            "gm_output_excerpt": _trim_text(
                turn.gm_output,
                excerpt_chars,
            ),
            "action_options": turn.action_options_json,
        }


def _trim_text(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."
