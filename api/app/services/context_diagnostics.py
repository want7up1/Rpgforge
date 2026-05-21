from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.turn import Turn
from app.schemas.game import ContextDiagnosticRead
from app.services.context_compressor import ContextCompressor
from app.services.story_settings import (
    StoryMaterialResult,
    build_runtime_story,
    retrieve_story_materials,
    select_action_style,
)


class ContextDiagnosticService:
    def __init__(
        self,
        context_compressor: ContextCompressor | None = None,
    ) -> None:
        self.context_compressor = context_compressor or ContextCompressor()

    def build_for_turn(
        self,
        db: Session,
        game: Game,
        turn_id: UUID | None = None,
    ) -> ContextDiagnosticRead | None:
        turn = self._resolve_turn(db, game, turn_id)
        if turn is None:
            return None

        recent_turns = self._recent_turns_before(db, game.id, turn.turn_number)
        selected_action_style = select_action_style(game.config, turn.player_input)
        related_materials = retrieve_story_materials(
            game.config,
            player_input=turn.player_input,
            selected_action_style=selected_action_style,
            state_json=game.state.state_json if game.state else {},
            recent_turns=recent_turns,
        )
        summaries = self.context_compressor.load_prompt_summaries(db, game.id)

        return ContextDiagnosticRead(
            turn_id=turn.id,
            turn_number=turn.turn_number,
            player_input=turn.player_input,
            selected_action_style=selected_action_style,
            recent_turn_numbers=[recent_turn.turn_number for recent_turn in recent_turns],
            memory_summaries=summaries,
            runtime_story=build_runtime_story(
                game.config,
                game.state.state_json if game.state else {},
                selected_action_style=selected_action_style,
                related_materials=related_materials,
            ),
            related_story_materials=[
                self._retrieval_payload(result) for result in related_materials
            ],
        )

    def _resolve_turn(self, db: Session, game: Game, turn_id: UUID | None) -> Turn | None:
        if turn_id is not None:
            turn = db.scalar(
                select(Turn).where(Turn.id == turn_id, Turn.game_id == game.id).limit(1)
            )
            if turn is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Turn not found.",
                )
            return turn
        return game.turns[-1] if game.turns else None

    @staticmethod
    def _recent_turns_before(
        db: Session,
        game_id: UUID,
        turn_number: int,
        limit: int = 6,
    ) -> list[Turn]:
        turns = list(
            db.scalars(
                select(Turn)
                .where(Turn.game_id == game_id, Turn.turn_number < turn_number)
                .order_by(Turn.turn_number.desc())
                .limit(limit)
            ).all()
        )
        return list(reversed(turns))

    @staticmethod
    def _retrieval_payload(result: StoryMaterialResult) -> dict[str, Any]:
        return {
            **result.material,
            "retrieval": {
                "score": result.score,
                "matched_terms": result.matched_terms,
            },
        }


def memory_summary_payload(summaries: dict[str, Any]) -> dict[str, Any]:
    return summaries
