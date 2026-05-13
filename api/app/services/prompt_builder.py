import json
from typing import Any

from app.models.game import Game, GameConfig
from app.models.lore import LoreEntry
from app.models.mode import Mode
from app.models.turn import Turn
from app.services.lore_retriever import LoreRetrievalResult
from app.services.prompt_loader import load_prompt_template
from app.services.state_v2 import state_v2_view
from app.services.story_blueprint import (
    build_campaign_contract_payload,
    build_story_blueprint,
)

RECENT_TURN_GM_OUTPUT_EXCERPT_CHARS = 420


class PromptBuilder:
    def build_runtime_messages(
        self,
        *,
        game: Game,
        player_input: str,
        selected_mode: Mode | None,
        recent_turns: list[Turn],
        related_lore: list[LoreRetrievalResult] | None = None,
        summaries: dict[str, object] | None = None,
        story_director: dict[str, object] | None = None,
        drift_rewrite_instruction: str | None = None,
    ) -> list[dict[str, str]]:
        config = game.config
        game_state = game.state
        always_on_lore = self._select_always_on_lore(game.lore_entries)

        runtime_payload = {
            "game": {
                "id": str(game.id),
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
            },
            "system_prompt": config.system_prompt if config else "",
            "worldview": config.worldview if config else {},
            "campaign_contract": self._campaign_contract_payload(config),
            "story_blueprint": build_story_blueprint(config),
            "selected_mode": self._mode_payload(selected_mode),
            "always_on_lore": [self._lore_payload(entry) for entry in always_on_lore],
            "related_lore": [
                self._retrieval_payload(result) for result in (related_lore or [])
            ],
            "current_state_v2": state_v2_view(game_state.state_json if game_state else {}),
            "memory_summaries": summaries or {},
            "story_director": story_director or {},
            "drift_rewrite_instruction": drift_rewrite_instruction or "",
            "recent_turns": [self._turn_payload(turn) for turn in recent_turns],
            "player_input": player_input,
        }

        return [
            {"role": "system", "content": load_prompt_template("gm_runtime.md")},
            {
                "role": "user",
                "content": json.dumps(runtime_payload, ensure_ascii=False, default=str),
            },
        ]

    @staticmethod
    def _select_always_on_lore(entries: list[LoreEntry]) -> list[LoreEntry]:
        priority = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        always_on = [
            entry for entry in entries if entry.always_on and getattr(entry, "is_active", True)
        ]
        return sorted(
            always_on,
            key=lambda entry: priority.get(entry.priority or "medium", 2),
            reverse=True,
        )[:8]

    @staticmethod
    def _campaign_contract_payload(config: GameConfig | None) -> dict[str, Any]:
        return build_campaign_contract_payload(config)

    @staticmethod
    def _lore_payload(entry: LoreEntry) -> dict[str, object]:
        return {
            "title": entry.title,
            "type": entry.type,
            "keywords": entry.keywords,
            "trigger_words": entry.trigger_words,
            "priority": entry.priority,
            "visibility": entry.visibility,
            "public_info": entry.public_info,
            "gm_secret": entry.gm_secret,
            "content": entry.content,
            "usage_note": entry.usage_note,
        }

    def _retrieval_payload(self, result: LoreRetrievalResult) -> dict[str, object]:
        payload = self._lore_payload(result.entry)
        payload["retrieval"] = {
            "score": result.score,
            "keyword_score": result.keyword_score,
            "vector_score": result.vector_score,
            "matched_terms": result.matched_terms,
        }
        return payload

    @staticmethod
    def _mode_payload(mode: Mode | None) -> dict[str, object] | None:
        if mode is None:
            return None
        return {
            "name": mode.name,
            "injection": mode.injection,
            "priority": mode.priority,
            "triggers": mode.triggers,
        }

    @staticmethod
    def _turn_payload(turn: Turn) -> dict[str, object]:
        return {
            "turn_number": turn.turn_number,
            "player_input": turn.player_input,
            "visible_summary": turn.visible_summary,
            "hidden_summary": turn.hidden_summary,
            "gm_output_excerpt": _trim_text(
                turn.gm_output,
                RECENT_TURN_GM_OUTPUT_EXCERPT_CHARS,
            ),
            "action_options": turn.action_options_json,
        }


def _trim_text(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."
