from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.lore import LoreEntry
from app.models.turn import Turn
from app.schemas.game import ContextDiagnosticRead, LoreDiagnosticRead, ModeRead
from app.services.context_compressor import ContextCompressor
from app.services.lore_retriever import LoreRetrievalResult, LoreRetriever
from app.services.mode_matcher import select_mode
from app.services.prompt_builder import PromptBuilder
from app.services.story_blueprint import build_story_blueprint


class ContextDiagnosticService:
    def __init__(
        self,
        lore_retriever: LoreRetriever | None = None,
        context_compressor: ContextCompressor | None = None,
    ) -> None:
        self.lore_retriever = lore_retriever or LoreRetriever()
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
        selected_mode = select_mode(turn.player_input, game.modes)
        related_lore = self.lore_retriever.retrieve(
            db=db,
            game=game,
            player_input=turn.player_input,
            selected_mode=selected_mode,
            recent_turns=recent_turns,
        )
        summaries = self.context_compressor.load_prompt_summaries(db, game.id)
        always_on_lore = PromptBuilder._select_always_on_lore(game.lore_entries)

        return ContextDiagnosticRead(
            turn_id=turn.id,
            turn_number=turn.turn_number,
            player_input=turn.player_input,
            selected_mode=ModeRead.model_validate(selected_mode) if selected_mode else None,
            recent_turn_numbers=[recent_turn.turn_number for recent_turn in recent_turns],
            memory_summaries=summaries,
            campaign_contract=PromptBuilder._campaign_contract_payload(game.config),
            story_blueprint=build_story_blueprint(game.config),
            always_on_lore=[self._lore_payload(entry) for entry in always_on_lore],
            related_lore=[self._retrieval_payload(result) for result in related_lore],
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
    def _lore_payload(entry: LoreEntry) -> LoreDiagnosticRead:
        return LoreDiagnosticRead(
            id=entry.id,
            title=entry.title,
            type=entry.type,
            priority=entry.priority,
            always_on=entry.always_on,
            keywords=entry.keywords,
            trigger_words=entry.trigger_words,
            usage_note=entry.usage_note,
        )

    def _retrieval_payload(self, result: LoreRetrievalResult) -> LoreDiagnosticRead:
        payload = self._lore_payload(result.entry).model_dump()
        payload.update(
            {
                "score": result.score,
                "keyword_score": result.keyword_score,
                "vector_score": result.vector_score,
                "matched_terms": result.matched_terms,
            }
        )
        return LoreDiagnosticRead.model_validate(payload)


def memory_summary_payload(summaries: dict[str, Any]) -> dict[str, Any]:
    return summaries
