import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.game import Game
from app.models.turn import Turn
from app.schemas.turn import GMRuntimeOutput, TurnCreate
from app.services.context_compressor import ContextCompressor
from app.services.deepseek_client import DeepSeekError
from app.services.drift_validator import DriftValidator
from app.services.game_activity import touch_game
from app.services.json_utils import parse_json_object
from app.services.model_router import ModelRouter
from app.services.prompt_builder import PromptBuilder
from app.services.state_delta_auto_apply import apply_pending_state_deltas
from app.services.state_extractor import StateExtractor, StateExtractorValidationError
from app.services.state_rebuilder import approve_turn_state_delta, rebuild_game_state
from app.services.story_settings import (
    StoryMaterialResult,
    build_runtime_story,
    retrieve_story_materials,
    select_action_style,
)
from app.services.story_director import StoryDirector, StoryDirectorDecision

logger = logging.getLogger(__name__)
GameplayStreamUpdateCallback = Callable[[str, str, str | None], Awaitable[None]]
GameplayProgressCallback = Callable[[str], Awaitable[None]]


class GameplayValidationError(RuntimeError):
    pass


@dataclass
class TurnRuntimeContext:
    game: Game
    player_input: str
    selected_action_style: dict[str, Any] | None
    recent_turns: list[Turn]
    related_materials: list[StoryMaterialResult]
    summaries: dict[str, Any]


class GameplayService:
    def __init__(
        self,
        router: ModelRouter | None = None,
        prompt_builder: PromptBuilder | None = None,
        state_extractor: StateExtractor | None = None,
        context_compressor: ContextCompressor | None = None,
        story_director: StoryDirector | None = None,
        drift_validator: DriftValidator | None = None,
    ) -> None:
        self.router = router or ModelRouter()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.state_extractor = state_extractor or StateExtractor(router=self.router)
        self.context_compressor = context_compressor or ContextCompressor(router=self.router)
        self.story_director = story_director or StoryDirector(router=self.router)
        self.drift_validator = drift_validator or DriftValidator(router=self.router)

    async def run_turn(self, db: Session, game: Game, payload: TurnCreate) -> Turn:
        context = await self.load_turn_runtime_context(db, game, payload)
        runtime_output, model_used = await self.generate_turn_runtime_output(context)
        turn = self.persist_runtime_turn(
            db,
            game_id=game.id,
            player_input=context.player_input,
            runtime_output=runtime_output,
            model_used=model_used,
        )
        await self._create_state_delta(db, game, turn)
        return turn

    async def run_turn_stream(
        self,
        db: Session,
        game: Game,
        payload: TurnCreate,
        on_update: GameplayStreamUpdateCallback | None = None,
        on_progress: GameplayProgressCallback | None = None,
        extract_state: bool = True,
    ) -> Turn:
        context = await self.load_turn_runtime_context(db, game, payload, on_progress=on_progress)
        runtime_output, model_used = await self.generate_turn_runtime_output(
            context,
            on_update=on_update,
            on_progress=on_progress,
        )
        if on_progress:
            await on_progress("GM 回复已完成，正在写入回合。")

        turn = self.persist_runtime_turn(
            db,
            game_id=game.id,
            player_input=context.player_input,
            runtime_output=runtime_output,
            model_used=model_used,
        )

        if extract_state:
            if on_progress:
                await on_progress("正在调用 DeepSeek Flash 提取状态变更。")
            await self._create_state_delta(db, game, turn)
        return turn

    async def load_turn_runtime_context(
        self,
        db: Session,
        game: Game,
        payload: TurnCreate,
        on_progress: GameplayProgressCallback | None = None,
    ) -> TurnRuntimeContext:
        apply_pending_state_deltas(db, game)
        player_input = payload.resolved_player_input
        selected_action_style = select_action_style(game.config, player_input)
        recent_turns = self._recent_turns(db, game.id)
        if on_progress:
            await on_progress("正在检索相关剧本素材与压缩摘要。")
        related_materials, summaries = self._load_runtime_inputs(
            db=db,
            game=game,
            player_input=player_input,
            selected_action_style=selected_action_style,
            recent_turns=recent_turns,
        )
        return TurnRuntimeContext(
            game=game,
            player_input=player_input,
            selected_action_style=selected_action_style,
            recent_turns=recent_turns,
            related_materials=related_materials,
            summaries=summaries,
        )

    async def generate_turn_runtime_output(
        self,
        context: TurnRuntimeContext,
        on_update: GameplayStreamUpdateCallback | None = None,
        on_progress: GameplayProgressCallback | None = None,
    ) -> tuple[GMRuntimeOutput, str]:
        if on_progress:
            await on_progress("正在规划本回合剧情导演决策。")
        director_decision = await self.story_director.plan(
            game=context.game,
            player_input=context.player_input,
            selected_action_style=context.selected_action_style,
            recent_turns=context.recent_turns,
            related_materials=context.related_materials,
            summaries=context.summaries,
        )
        if on_progress:
            await on_progress("剧情导演决策已完成，正在调用 GM 书写剧情。")
        messages = self._build_contextual_runtime_messages(
            game=context.game,
            player_input=context.player_input,
            selected_action_style=context.selected_action_style,
            recent_turns=context.recent_turns,
            related_materials=context.related_materials,
            summaries=context.summaries,
            director_decision=director_decision,
        )

        if on_update is None:
            result = await self.router.use_pro("gm_runtime", messages, json_mode=True)
            runtime_output = self._parse_runtime_output(result.content)
            model_used = result.model
        else:
            runtime_output, model_used = await self._collect_runtime_output_stream(
                messages,
                on_update=on_update,
            )
        if not self._should_run_drift_validation(
            game=context.game,
            recent_turns=context.recent_turns,
            director_decision=director_decision,
            runtime_output=runtime_output,
        ):
            if on_progress:
                await on_progress("偏离风险较低，跳过深度校验。")
            return runtime_output, model_used
        if on_progress:
            await on_progress("正在校验剧情是否偏离剧本锚点。")
        runtime_output, model_used = await self._validate_and_maybe_rewrite(
            game=context.game,
            player_input=context.player_input,
            selected_action_style=context.selected_action_style,
            recent_turns=context.recent_turns,
            related_materials=context.related_materials,
            summaries=context.summaries,
            director_decision=director_decision,
            runtime_output=runtime_output,
            model_used=model_used,
            on_update=on_update,
            on_progress=on_progress,
        )
        return runtime_output, model_used

    def _should_run_drift_validation(
        self,
        *,
        game: Game,
        recent_turns: list[Turn],
        director_decision: StoryDirectorDecision,
        runtime_output: GMRuntimeOutput,
    ) -> bool:
        next_turn_number = (recent_turns[-1].turn_number + 1) if recent_turns else 1
        if next_turn_number == 1 or next_turn_number % 3 == 0:
            return True

        output_text = "\n".join(
            [
                runtime_output.narrative,
                "\n".join(runtime_output.visible_clues),
                "\n".join(option.label for option in runtime_output.action_options),
            ]
        )
        normalized_output = output_text.lower()
        high_risk_terms = (
            "终局",
            "最终真相",
            "全部真相",
            "幕后黑手",
            "幕后组织",
            "真正身份",
            "新组织",
            "新势力",
            "boss",
            "新 boss",
            "世界级危机",
            "秘密基地",
            "核心秘密",
            "神明",
            "灭世",
        )
        if any(term in normalized_output for term in high_risk_terms):
            return True

        for reveal in director_decision.forbidden_reveals:
            reveal_text = reveal.strip()
            if len(reveal_text) >= 4 and reveal_text in output_text:
                return True

        runtime_story = build_runtime_story(game.config, game.state.state_json if game.state else {})
        core = runtime_story.get("story_core") if isinstance(runtime_story, dict) else {}
        if not isinstance(core, dict):
            core = {}
        for forbidden in core.get("forbidden_drift") or []:
            forbidden_text = str(forbidden).strip()
            if len(forbidden_text) >= 4 and forbidden_text in output_text:
                return True

        return False

    def persist_runtime_turn(
        self,
        db: Session,
        *,
        game_id,
        player_input: str,
        runtime_output: GMRuntimeOutput,
        model_used: str,
    ) -> Turn:
        next_turn_number = self._next_turn_number(db, game_id)
        turn = Turn(
            game_id=game_id,
            turn_number=next_turn_number,
            player_input=player_input,
            gm_output=runtime_output.narrative,
            visible_summary="\n".join(runtime_output.visible_clues),
            hidden_summary=None,
            state_delta_json={},
            action_options_json=[option.model_dump() for option in runtime_output.action_options],
            model_used=model_used,
        )
        db.add(turn)
        touch_game(db, game_id)
        db.commit()
        db.refresh(turn)
        return turn

    async def _create_state_delta(self, db: Session, game: Game, turn: Turn) -> bool:
        try:
            delta_json = await self.state_extractor.extract(game, turn)
        except (DeepSeekError, StateExtractorValidationError) as exc:
            logger.warning("State delta extraction failed for turn %s: %s", turn.id, exc)
            await self._update_context_after_turn(db, game, turn, {})
            return False

        turn.state_delta_json = delta_json
        if game.state is not None:
            approve_turn_state_delta(
                db,
                game=game,
                turn=turn,
                delta_json=delta_json,
                approved_at=datetime.now(UTC),
            )
            rebuild_game_state(db, game)
        touch_game(db, game.id)
        db.add(turn)
        db.commit()
        db.refresh(turn)
        await self._update_context_after_turn(db, game, turn, delta_json)
        return True

    def _load_runtime_inputs(
        self,
        *,
        db: Session,
        game: Game,
        player_input: str,
        selected_action_style: dict[str, Any] | None,
        recent_turns: list[Turn],
    ) -> tuple[list[StoryMaterialResult], dict[str, Any]]:
        related_materials = retrieve_story_materials(
            game.config,
            player_input=player_input,
            selected_action_style=selected_action_style,
            state_json=game.state.state_json if game.state else {},
            recent_turns=recent_turns,
        )
        self.context_compressor.ensure_bootstrap_summaries(db, game)
        summaries = self.context_compressor.load_prompt_summaries(db, game.id)
        return related_materials, summaries

    def _build_contextual_runtime_messages(
        self,
        *,
        game: Game,
        player_input: str,
        selected_action_style: dict[str, Any] | None,
        recent_turns: list[Turn],
        related_materials: list[StoryMaterialResult],
        summaries: dict[str, Any],
        director_decision: StoryDirectorDecision,
        drift_rewrite_instruction: str | None = None,
    ) -> list[dict[str, str]]:
        return self.prompt_builder.build_runtime_messages(
            game=game,
            player_input=player_input,
            selected_action_style=selected_action_style,
            recent_turns=recent_turns,
            related_materials=related_materials,
            summaries=summaries,
            story_director=director_decision.model_dump(),
            drift_rewrite_instruction=drift_rewrite_instruction,
        )

    async def _validate_and_maybe_rewrite(
        self,
        *,
        game: Game,
        player_input: str,
        selected_action_style: dict[str, Any] | None,
        recent_turns: list[Turn],
        related_materials: list[StoryMaterialResult],
        summaries: dict[str, Any],
        director_decision: StoryDirectorDecision,
        runtime_output: GMRuntimeOutput,
        model_used: str,
        on_update: GameplayStreamUpdateCallback | None = None,
        on_progress: GameplayProgressCallback | None = None,
    ) -> tuple[GMRuntimeOutput, str]:
        validation = await self.drift_validator.validate(
            game=game,
            player_input=player_input,
            recent_turns=recent_turns,
            director_decision=director_decision,
            runtime_output=runtime_output,
        )
        if not self.drift_validator.should_rewrite(validation):
            return runtime_output, model_used

        rewrite_instruction = self.drift_validator.rewrite_instruction(validation)
        if on_progress:
            await on_progress("偏离校验要求重写剧情，正在重新生成。")
        rewrite_messages = self._build_contextual_runtime_messages(
            game=game,
            player_input=player_input,
            selected_action_style=selected_action_style,
            recent_turns=recent_turns,
            related_materials=related_materials,
            summaries=summaries,
            director_decision=director_decision,
            drift_rewrite_instruction=rewrite_instruction,
        )
        if on_update is None:
            result = await self.router.use_pro(
                "gm_runtime_rewrite",
                rewrite_messages,
                json_mode=True,
            )
            return self._parse_runtime_output(result.content), result.model

        return await self._collect_runtime_output_stream(
            rewrite_messages,
            on_update=on_update,
        )

    async def _update_context_after_turn(
        self,
        db: Session,
        game: Game,
        turn: Turn,
        delta_json: dict,
    ) -> None:
        try:
            await self.context_compressor.update_after_turn(db, game, turn, delta_json)
        except Exception as exc:
            logger.warning("Context summary update failed for turn %s: %s", turn.id, exc)

    @staticmethod
    def _parse_runtime_output(content: str) -> GMRuntimeOutput:
        try:
            payload = parse_json_object(content)
            return GMRuntimeOutput.model_validate(payload)
        except Exception as exc:
            raise GameplayValidationError(str(exc)) from exc

    async def _collect_runtime_output_stream(
        self,
        messages: list[dict[str, str]],
        on_update: GameplayStreamUpdateCallback | None,
    ) -> tuple[GMRuntimeOutput, str]:
        reasoning_parts: list[str] = []
        content_parts: list[str] = []
        model_used: str | None = None

        async for chunk in self.router.use_pro_stream(
            "gm_runtime",
            messages,
            json_mode=True,
            max_tokens=12000,
            reasoning_effort="high",
        ):
            if chunk.model:
                model_used = chunk.model
            if chunk.reasoning_delta:
                reasoning_parts.append(chunk.reasoning_delta)
            if chunk.content_delta:
                content_parts.append(chunk.content_delta)
            if on_update and (chunk.reasoning_delta or chunk.content_delta):
                await on_update(
                    "".join(reasoning_parts),
                    "".join(content_parts),
                    model_used,
                )

        content = "".join(content_parts).strip()
        if not content:
            raise GameplayValidationError("DeepSeek API 流式返回了空 GM 内容。")
        return self._parse_runtime_output(content), model_used or "unknown"

    @staticmethod
    def _next_turn_number(db: Session, game_id) -> int:
        latest = db.scalar(select(func.max(Turn.turn_number)).where(Turn.game_id == game_id))
        return int(latest or 0) + 1

    @staticmethod
    def _recent_turns(db: Session, game_id, limit: int = 6) -> list[Turn]:
        turns = list(
            db.scalars(
                select(Turn)
                .where(Turn.game_id == game_id)
                .order_by(Turn.turn_number.desc())
                .limit(limit)
            ).all()
        )
        return list(reversed(turns))


def gameplay_game_query(game_id):
    return (
        select(Game)
        .options(
            selectinload(Game.config),
            selectinload(Game.state),
            selectinload(Game.summaries),
        )
        .where(Game.id == game_id)
    )
