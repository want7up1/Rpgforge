from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.game import Game
from app.models.summary import Summary
from app.models.turn import Turn
from app.services.deepseek_client import DeepSeekError
from app.services.game_activity import touch_game
from app.services.json_utils import parse_json_object
from app.services.model_router import ModelRouter
from app.services.prompt_builder import PromptBuilder
from app.services.prompt_loader import load_prompt_template
from app.services.story_blueprint import build_story_blueprint

logger = logging.getLogger(__name__)


class ContextCompressionOutput(BaseModel):
    turn_visible_summary: str | None = None
    turn_hidden_summary: str | None = None
    chapter_summary: str | None = None
    long_term_summary: str | None = None
    important_facts: dict[str, Any] = Field(default_factory=dict)


class ContextCompressor:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    def load_prompt_summaries(self, db: Session, game_id: UUID) -> dict[str, Any]:
        long_term = self._latest_summary(db, game_id, "long_term")
        chapter = self._latest_summary(db, game_id, "chapter")
        recent_turns = list(
            db.scalars(
                select(Summary)
                .where(Summary.game_id == game_id, Summary.type == "turn")
                .order_by(Summary.range_end_turn.desc())
                .limit(5)
            ).all()
        )
        return {
            "long_term": self._summary_payload(long_term),
            "chapter": self._summary_payload(chapter),
            "recent_turn_summaries": [
                self._summary_payload(summary) for summary in reversed(recent_turns)
            ],
        }

    def ensure_bootstrap_summaries(self, db: Session, game: Game) -> None:
        if self._latest_summary(db, game.id, "long_term") is not None:
            return

        turns = list(
            db.scalars(
                select(Turn).where(Turn.game_id == game.id).order_by(Turn.turn_number.asc())
            ).all()
        )
        if not turns and not (game.state and game.state.summary):
            return

        important_facts = self._state_important_facts(game)
        long_term_content = game.state.summary if game.state and game.state.summary else ""
        if not long_term_content:
            long_term_content = _trim_text(
                "\n".join(
                    f"第 {turn.turn_number} 回："
                    f"{turn.visible_summary or _trim_text(turn.gm_output, 220)}"
                    for turn in turns
                ),
                5000,
            )
        latest_turn_number = turns[-1].turn_number if turns else game.state.current_turn
        chapter_start = max(1, latest_turn_number - 9)
        chapter_content = _trim_text(
            "\n".join(
                f"第 {turn.turn_number} 回："
                f"{turn.visible_summary or _trim_text(turn.gm_output, 220)}"
                for turn in turns
                if turn.turn_number >= chapter_start
            )
            or long_term_content,
            2600,
        )

        self._upsert_summary(
            db,
            game_id=game.id,
            summary_type="long_term",
            range_start_turn=1,
            range_end_turn=latest_turn_number,
            content=long_term_content,
            important_facts=important_facts,
        )
        self._upsert_summary(
            db,
            game_id=game.id,
            summary_type="chapter",
            range_start_turn=chapter_start,
            range_end_turn=latest_turn_number,
            content=chapter_content,
            important_facts=important_facts,
        )
        for turn in turns[-5:]:
            self._upsert_summary(
                db,
                game_id=game.id,
                summary_type="turn",
                range_start_turn=turn.turn_number,
                range_end_turn=turn.turn_number,
                content=turn.visible_summary or _trim_text(turn.gm_output, 360),
                important_facts={},
            )
        db.commit()

    def rebuild_from_history(self, db: Session, game: Game) -> list[Summary]:
        turns = list(
            db.scalars(
                select(Turn).where(Turn.game_id == game.id).order_by(Turn.turn_number.asc())
            ).all()
        )
        db.execute(delete(Summary).where(Summary.game_id == game.id))

        important_facts = self._state_important_facts(game)
        if not turns and not (game.state and game.state.summary):
            db.commit()
            return []

        latest_turn_number = turns[-1].turn_number if turns else game.state.current_turn
        long_term_content = self._long_term_content(game, turns)
        self._upsert_summary(
            db,
            game_id=game.id,
            summary_type="long_term",
            range_start_turn=1,
            range_end_turn=latest_turn_number,
            content=long_term_content,
            important_facts=important_facts,
        )

        chapter_groups: dict[int, list[Turn]] = {}
        for turn in turns:
            chapter_start = ((turn.turn_number - 1) // 10) * 10 + 1
            chapter_groups.setdefault(chapter_start, []).append(turn)

        if chapter_groups:
            for chapter_start, chapter_turns in chapter_groups.items():
                chapter_content = _trim_text(
                    "\n".join(self._turn_summary_line(turn, limit=280) for turn in chapter_turns),
                    2600,
                )
                self._upsert_summary(
                    db,
                    game_id=game.id,
                    summary_type="chapter",
                    range_start_turn=chapter_start,
                    range_end_turn=chapter_turns[-1].turn_number,
                    content=chapter_content,
                    important_facts=important_facts,
                )
        else:
            self._upsert_summary(
                db,
                game_id=game.id,
                summary_type="chapter",
                range_start_turn=1,
                range_end_turn=latest_turn_number,
                content=long_term_content,
                important_facts=important_facts,
            )

        for turn in turns:
            self._upsert_summary(
                db,
                game_id=game.id,
                summary_type="turn",
                range_start_turn=turn.turn_number,
                range_end_turn=turn.turn_number,
                content=self._turn_summary_content(turn),
                important_facts={},
            )

        db.commit()
        return list(
            db.scalars(
                select(Summary)
                .where(Summary.game_id == game.id)
                .order_by(Summary.range_end_turn.asc().nullsfirst(), Summary.type.asc())
            ).all()
        )

    async def update_after_turn(
        self,
        db: Session,
        game: Game,
        turn: Turn,
        state_delta_json: dict[str, Any],
    ) -> None:
        existing_summaries = self.load_prompt_summaries(db, game.id)
        output = await self._compress_with_fallback(
            game=game,
            turn=turn,
            state_delta_json=state_delta_json,
            existing_summaries=existing_summaries,
        )

        if output.turn_visible_summary:
            turn.visible_summary = output.turn_visible_summary
        turn.hidden_summary = output.turn_hidden_summary or turn.hidden_summary

        turn_content = "\n".join(
            part
            for part in [
                f"玩家可见：{turn.visible_summary or _trim_text(turn.gm_output, 360)}",
                f"GM 幕后：{turn.hidden_summary}" if turn.hidden_summary else "",
            ]
            if part
        )
        self._upsert_summary(
            db,
            game_id=game.id,
            summary_type="turn",
            range_start_turn=turn.turn_number,
            range_end_turn=turn.turn_number,
            content=turn_content,
            important_facts=output.important_facts,
        )
        if output.chapter_summary:
            chapter_start = ((turn.turn_number - 1) // 10) * 10 + 1
            self._upsert_summary(
                db,
                game_id=game.id,
                summary_type="chapter",
                range_start_turn=chapter_start,
                range_end_turn=turn.turn_number,
                content=output.chapter_summary,
                important_facts=output.important_facts,
            )
        if output.long_term_summary:
            self._upsert_summary(
                db,
                game_id=game.id,
                summary_type="long_term",
                range_start_turn=1,
                range_end_turn=turn.turn_number,
                content=output.long_term_summary,
                important_facts=output.important_facts,
            )
            if game.state is not None:
                game.state.summary = output.long_term_summary
                db.add(game.state)

        db.add(turn)
        touch_game(db, game.id)
        db.commit()
        db.refresh(turn)

    async def _compress_with_fallback(
        self,
        *,
        game: Game,
        turn: Turn,
        state_delta_json: dict[str, Any],
        existing_summaries: dict[str, Any],
    ) -> ContextCompressionOutput:
        try:
            return await self._compress_with_model(
                game=game,
                turn=turn,
                state_delta_json=state_delta_json,
                existing_summaries=existing_summaries,
            )
        except (DeepSeekError, ValidationError, ValueError) as exc:
            logger.warning("Context compression fell back for turn %s: %s", turn.id, exc)
            return self._fallback_summary(turn, state_delta_json, existing_summaries)

    async def _compress_with_model(
        self,
        *,
        game: Game,
        turn: Turn,
        state_delta_json: dict[str, Any],
        existing_summaries: dict[str, Any],
    ) -> ContextCompressionOutput:
        payload = {
            "game": {
                "id": str(game.id),
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
            },
            "campaign_contract": PromptBuilder._campaign_contract_payload(game.config),
            "story_blueprint": build_story_blueprint(
                game.config,
                game.state.state_json if game.state else {},
            ),
            "current_state": game.state.state_json if game.state else {},
            "previous_summaries": existing_summaries,
            "turn": {
                "turn_number": turn.turn_number,
                "player_input": turn.player_input,
                "gm_output": turn.gm_output,
                "visible_summary": turn.visible_summary,
            },
            "state_delta": state_delta_json,
        }
        result = await self.router.use_flash(
            "compress_context",
            [
                {"role": "system", "content": load_prompt_template("compress_context.md")},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False, default=str),
                },
            ],
            json_mode=True,
            max_tokens=3000,
            reasoning_effort="high",
            respect_route=False,
        )
        parsed = parse_json_object(result.content)
        output = ContextCompressionOutput.model_validate(parsed)
        if not any(
            [
                output.turn_visible_summary,
                output.turn_hidden_summary,
                output.chapter_summary,
                output.long_term_summary,
            ]
        ):
            raise ValueError("Context compression output is empty.")
        return output

    def _fallback_summary(
        self,
        turn: Turn,
        state_delta_json: dict[str, Any],
        existing_summaries: dict[str, Any],
    ) -> ContextCompressionOutput:
        visible_summary = turn.visible_summary or _trim_text(turn.gm_output, 360)
        known_facts = _string_list(state_delta_json.get("new_known_facts"))
        hidden_facts = _string_list(state_delta_json.get("new_hidden_facts"))
        open_threads = _string_list(state_delta_json.get("open_thread_updates"))
        important_facts = {
            "known_facts": known_facts,
            "hidden_facts": hidden_facts,
            "open_threads": open_threads,
        }

        previous_chapter = (existing_summaries.get("chapter") or {}).get("content") or ""
        previous_long_term = (existing_summaries.get("long_term") or {}).get("content") or ""
        chapter_summary = _trim_text(
            "\n".join(
                part
                for part in [
                    previous_chapter,
                    f"第 {turn.turn_number} 回：{visible_summary}",
                    f"新线索：{'；'.join(known_facts)}" if known_facts else "",
                    f"待解事项：{'；'.join(open_threads)}" if open_threads else "",
                ]
                if part
            ),
            2600,
        )
        long_term_summary = _trim_text(
            "\n".join(
                part
                for part in [
                    previous_long_term,
                    f"玩家已知：{'；'.join(known_facts)}" if known_facts else "",
                    f"GM 幕后：{'；'.join(hidden_facts)}" if hidden_facts else "",
                    f"未解伏笔：{'；'.join(open_threads)}" if open_threads else "",
                ]
                if part
            )
            or visible_summary,
            3200,
        )
        return ContextCompressionOutput(
            turn_visible_summary=visible_summary,
            turn_hidden_summary=(
                "；".join(hidden_facts) if hidden_facts else "本回合暂无新增幕后摘要。"
            ),
            chapter_summary=chapter_summary,
            long_term_summary=long_term_summary,
            important_facts=important_facts,
        )

    def _upsert_summary(
        self,
        db: Session,
        *,
        game_id: UUID,
        summary_type: str,
        range_start_turn: int,
        range_end_turn: int,
        content: str,
        important_facts: dict[str, Any],
    ) -> Summary:
        query = select(Summary).where(
            Summary.game_id == game_id,
            Summary.type == summary_type,
            Summary.range_start_turn == range_start_turn,
        )
        if summary_type == "turn":
            query = query.where(Summary.range_end_turn == range_end_turn)
        summary = db.scalars(query).first()
        if summary is None:
            summary = Summary(
                game_id=game_id,
                type=summary_type,
                range_start_turn=range_start_turn,
                range_end_turn=range_end_turn,
                content=content,
                important_facts=important_facts,
            )
        else:
            summary.range_end_turn = range_end_turn
            summary.content = content
            summary.important_facts = important_facts
        db.add(summary)
        return summary

    @staticmethod
    def _latest_summary(db: Session, game_id: UUID, summary_type: str) -> Summary | None:
        return db.scalars(
            select(Summary)
            .where(Summary.game_id == game_id, Summary.type == summary_type)
            .order_by(Summary.range_end_turn.desc().nullslast(), Summary.created_at.desc())
            .limit(1)
        ).first()

    @staticmethod
    def _summary_payload(summary: Summary | None) -> dict[str, Any] | None:
        if summary is None:
            return None
        return {
            "type": summary.type,
            "range_start_turn": summary.range_start_turn,
            "range_end_turn": summary.range_end_turn,
            "content": summary.content,
            "important_facts": summary.important_facts,
        }

    @staticmethod
    def _state_important_facts(game: Game) -> dict[str, Any]:
        state_json = game.state.state_json if game.state else {}
        return {
            "known_facts": _string_list(state_json.get("known_facts")),
            "hidden_facts": _string_list(state_json.get("hidden_facts")),
            "open_threads": _string_list(state_json.get("open_threads")),
        }

    @staticmethod
    def _long_term_content(game: Game, turns: list[Turn]) -> str:
        state_summary = game.state.summary if game.state and game.state.summary else ""
        if state_summary:
            history = "\n".join(
                ContextCompressor._turn_summary_line(turn, limit=220) for turn in turns[-30:]
            )
            return _trim_text("\n".join(part for part in [state_summary, history] if part), 5000)
        return _trim_text(
            "\n".join(ContextCompressor._turn_summary_line(turn, limit=260) for turn in turns),
            5000,
        )

    @staticmethod
    def _turn_summary_line(turn: Turn, *, limit: int) -> str:
        summary = turn.visible_summary or _trim_text(turn.gm_output, limit)
        return f"第 {turn.turn_number} 回：{summary}"

    @staticmethod
    def _turn_summary_content(turn: Turn) -> str:
        parts = [
            f"玩家行动：{_trim_text(turn.player_input, 240)}",
            f"玩家可见：{turn.visible_summary or _trim_text(turn.gm_output, 420)}",
        ]
        if turn.hidden_summary:
            parts.append(f"GM 幕后：{turn.hidden_summary}")
        return "\n".join(parts)


def _trim_text(text: str, limit: int) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1]}…"


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
