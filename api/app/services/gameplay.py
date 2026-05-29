import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
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
from app.services.state_v2 import state_v2_view
from app.services.story_director import StoryDirector, StoryDirectorDecision
from app.services.story_settings import (
    StoryMaterialResult,
    build_runtime_story,
    retrieve_story_materials,
    select_action_style,
)

logger = logging.getLogger(__name__)
GameplayStreamUpdateCallback = Callable[[str, str, str | None], Awaitable[None]]
GameplayProgressCallback = Callable[[str], Awaitable[None]]
GameplayStageCallback = Callable[[str], Awaitable[None]]

# 单次 GM 调用上限。一回合最多两次 GM（初次 + 重写），整体仍由 TURN_JOB_TIMEOUT 兜底。
GM_RUNTIME_TIMEOUT_SECONDS = 360.0
# 重写走"带原稿局部修订"，输出体量通常不超过原稿；上限可以低于初次生成。
GM_REWRITE_MAX_TOKENS = 8000

# 显式 stage id，避免下游用中文文案反推。
STAGE_PREPARE_CONTEXT = "prepare_context"
STAGE_RETRIEVE_MEMORY = "retrieve_memory"
STAGE_STORY_DIRECTOR = "story_director"
STAGE_GM_RUNTIME = "gm_runtime"
STAGE_DRIFT_VALIDATION = "drift_validation"
STAGE_PERSIST_TURN = "persist_turn"
STAGE_COMPLETED = "completed"


async def _emit_stage(callback: GameplayStageCallback | None, stage: str) -> None:
    if callback is not None:
        await callback(stage)


class GameplayValidationError(RuntimeError):
    pass


@dataclass
class TurnTelemetry:
    director_used_fallback: bool = False
    drift_severity: str | None = None
    rewrite_triggered: bool = False
    extractor_failed: bool = False
    director_decision: dict[str, Any] | None = None
    drift_validation: dict[str, Any] | None = None

    def to_runtime_inputs(self) -> dict[str, Any]:
        """传给 maintenance 阶段 StateExtractor 的 hints。"""
        payload: dict[str, Any] = {}
        if self.director_decision:
            payload["director_decision"] = self.director_decision
        if self.drift_validation:
            payload["drift_validation"] = self.drift_validation
        return payload


@dataclass
class TurnRuntimeContext:
    game: Game
    player_input: str
    selected_action_style: dict[str, Any] | None
    recent_turns: list[Turn]
    related_materials: list[StoryMaterialResult]
    summaries: dict[str, Any]
    # 缓存：每回合只构造一次，供 Director/Validator/PromptBuilder 复用
    state_v2: dict[str, Any]
    runtime_story_full: dict[str, Any]
    runtime_story_bare: dict[str, Any]
    telemetry: TurnTelemetry = field(default_factory=TurnTelemetry)


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
        await self._create_state_delta(db, game, turn, telemetry=context.telemetry)
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
            await self._create_state_delta(db, game, turn, telemetry=context.telemetry)
        return turn

    async def load_turn_runtime_context(
        self,
        db: Session,
        game: Game,
        payload: TurnCreate,
        on_progress: GameplayProgressCallback | None = None,
        on_stage: GameplayStageCallback | None = None,
    ) -> TurnRuntimeContext:
        await _emit_stage(on_stage, STAGE_PREPARE_CONTEXT)
        apply_pending_state_deltas(db, game)
        player_input = payload.resolved_player_input
        selected_action_style = select_action_style(game.config, player_input)
        recent_turns = self._recent_turns(db, game.id)
        await _emit_stage(on_stage, STAGE_RETRIEVE_MEMORY)
        if on_progress:
            await on_progress("正在检索相关剧本素材与压缩摘要。")
        related_materials, summaries = self._load_runtime_inputs(
            db=db,
            game=game,
            player_input=player_input,
            selected_action_style=selected_action_style,
            recent_turns=recent_turns,
        )
        state_json = game.state.state_json if game.state else {}
        state_v2 = state_v2_view(state_json)
        runtime_story_full = build_runtime_story(
            game.config,
            state_json,
            selected_action_style=selected_action_style,
            related_materials=related_materials,
        )
        runtime_story_bare = build_runtime_story(game.config, state_json)
        return TurnRuntimeContext(
            game=game,
            player_input=player_input,
            selected_action_style=selected_action_style,
            recent_turns=recent_turns,
            related_materials=related_materials,
            summaries=summaries,
            state_v2=state_v2,
            runtime_story_full=runtime_story_full,
            runtime_story_bare=runtime_story_bare,
        )

    async def generate_turn_runtime_output(
        self,
        context: TurnRuntimeContext,
        on_update: GameplayStreamUpdateCallback | None = None,
        on_progress: GameplayProgressCallback | None = None,
        on_stage: GameplayStageCallback | None = None,
    ) -> tuple[GMRuntimeOutput, str]:
        await _emit_stage(on_stage, STAGE_STORY_DIRECTOR)
        if on_progress:
            await on_progress("正在规划本回合剧情导演决策。")
        director_decision = await self.story_director.plan(
            game=context.game,
            player_input=context.player_input,
            selected_action_style=context.selected_action_style,
            recent_turns=context.recent_turns,
            related_materials=context.related_materials,
            summaries=context.summaries,
            runtime_story=context.runtime_story_full,
            state_v2=context.state_v2,
        )
        context.telemetry.director_used_fallback = director_decision.used_fallback
        # 用代码硬底线约束 Director 的揭露边界：Director 可能漏写禁止项，也可能扩写
        # allowed_reveals；脚本当前幕的白名单/黑名单不允许被 Director 改写。
        self._enforce_director_reveal_boundaries(
            director_decision,
            runtime_story=context.runtime_story_bare,
        )
        # 完整保存供 maintenance 阶段的 StateExtractor 读取（continuity_notes 等）。
        context.telemetry.director_decision = director_decision.model_dump(
            exclude={"used_fallback"}
        )
        await _emit_stage(on_stage, STAGE_GM_RUNTIME)
        if on_progress:
            await on_progress("剧情导演决策已完成，正在调用 GM 书写剧情。")
        messages = self._build_contextual_runtime_messages(
            context=context,
            director_decision=director_decision,
        )

        if on_update is None:
            try:
                result = await asyncio.wait_for(
                    self.router.use_pro("gm_runtime", messages, json_mode=True),
                    timeout=GM_RUNTIME_TIMEOUT_SECONDS,
                )
            except TimeoutError as exc:
                raise GameplayValidationError(
                    f"GM 主调用超过 {int(GM_RUNTIME_TIMEOUT_SECONDS)} 秒。"
                ) from exc
            runtime_output = self._parse_runtime_output(result.content)
            model_used = result.model
        else:
            runtime_output, model_used = await asyncio.wait_for(
                self._collect_runtime_output_stream(messages, on_update=on_update),
                timeout=GM_RUNTIME_TIMEOUT_SECONDS,
            )
        if not self._should_run_drift_validation(
            game=context.game,
            recent_turns=context.recent_turns,
            director_decision=director_decision,
            runtime_output=runtime_output,
            runtime_story=context.runtime_story_bare,
        ):
            if on_progress:
                await on_progress("偏离风险较低，跳过深度校验。")
            return runtime_output, model_used
        await _emit_stage(on_stage, STAGE_DRIFT_VALIDATION)
        if on_progress:
            await on_progress("正在校验剧情是否偏离剧本锚点。")
        runtime_output, model_used = await self._validate_and_maybe_rewrite(
            context=context,
            director_decision=director_decision,
            runtime_output=runtime_output,
            model_used=model_used,
            on_update=on_update,
            on_progress=on_progress,
            on_stage=on_stage,
        )
        return runtime_output, model_used

    def _should_run_drift_validation(
        self,
        *,
        game: Game,
        recent_turns: list[Turn],
        director_decision: StoryDirectorDecision,
        runtime_output: GMRuntimeOutput,
        runtime_story: dict[str, Any] | None = None,
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

        if runtime_story is None:
            state_json = game.state.state_json if game.state else {}
            runtime_story = build_runtime_story(game.config, state_json)
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

    async def _create_state_delta(
        self,
        db: Session,
        game: Game,
        turn: Turn,
        telemetry: TurnTelemetry | None = None,
    ) -> bool:
        director_decision = telemetry.director_decision if telemetry else None
        drift_findings = telemetry.drift_validation if telemetry else None
        try:
            delta_json = await self.state_extractor.extract(
                game,
                turn,
                director_decision=director_decision,
                drift_findings=drift_findings,
            )
        except (DeepSeekError, StateExtractorValidationError) as exc:
            logger.warning("State delta extraction failed for turn %s: %s", turn.id, exc)
            if telemetry is not None:
                telemetry.extractor_failed = True
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
        context: TurnRuntimeContext,
        director_decision: StoryDirectorDecision,
        drift_rewrite_instruction: str | None = None,
        previous_runtime_output: GMRuntimeOutput | None = None,
    ) -> list[dict[str, str]]:
        filtered_materials = self._filter_materials_by_director(
            context.related_materials,
            director_decision.active_material_titles,
        )
        # Director 给出了选材时，重建一份只含选中素材的 runtime_story 供 GM 使用；
        # 没有选材或选材落空时，复用缓存的全量版本。
        if filtered_materials is context.related_materials:
            runtime_story_for_gm = context.runtime_story_full
        else:
            state_json = context.game.state.state_json if context.game.state else {}
            runtime_story_for_gm = build_runtime_story(
                context.game.config,
                state_json,
                selected_action_style=context.selected_action_style,
                related_materials=filtered_materials,
            )
        return self.prompt_builder.build_runtime_messages(
            game=context.game,
            player_input=context.player_input,
            selected_action_style=context.selected_action_style,
            recent_turns=context.recent_turns,
            related_materials=filtered_materials,
            summaries=context.summaries,
            story_director=director_decision.model_dump(exclude={"used_fallback"}),
            drift_rewrite_instruction=drift_rewrite_instruction,
            runtime_story=runtime_story_for_gm,
            state_v2=context.state_v2,
            previous_runtime_output=previous_runtime_output,
        )

    @staticmethod
    def _enforce_director_reveal_boundaries(
        decision: StoryDirectorDecision,
        *,
        runtime_story: dict[str, Any],
    ) -> None:
        GameplayService._clamp_allowed_reveals(decision, runtime_story=runtime_story)
        GameplayService._enforce_hard_forbidden_reveals(
            decision,
            runtime_story=runtime_story,
        )

    @staticmethod
    def _clamp_allowed_reveals(
        decision: StoryDirectorDecision,
        *,
        runtime_story: dict[str, Any],
    ) -> None:
        current_act = runtime_story.get("current_act") if isinstance(runtime_story, dict) else None
        if not isinstance(current_act, dict):
            return
        allowed = current_act.get("allowed_reveals")
        if not isinstance(allowed, list):
            return

        allowed_items = [str(item).strip() for item in allowed if str(item or "").strip()]
        allowed_set = set(allowed_items)
        decision.allowed_reveals = [
            item
            for item in decision.allowed_reveals
            if item.strip() in allowed_set
        ]

    @staticmethod
    def _enforce_hard_forbidden_reveals(
        decision: StoryDirectorDecision,
        *,
        runtime_story: dict[str, Any],
    ) -> None:
        """把脚本里写死的硬底线 merge 进 Director 输出，Director 不能删除这些项。"""
        hard_items: list[str] = []

        # 只 merge"禁止"类语义字段。
        # must_hit_beats（必须发生的剧情节点）属于"必须出现"语义，不能并入 forbidden_reveals
        # —— Round 1 落地时误并，会把"应当发生的事"当成"禁止揭露的事"，反向误杀正常剧情。
        current_act = runtime_story.get("current_act") if isinstance(runtime_story, dict) else None
        if isinstance(current_act, dict):
            value = current_act.get("forbidden_reveals")
            if isinstance(value, list):
                hard_items.extend(str(item) for item in value if str(item or "").strip())

        story_core = runtime_story.get("story_core") if isinstance(runtime_story, dict) else None
        if isinstance(story_core, dict):
            for key in ("forbidden_drift", "must_not_become"):
                value = story_core.get(key)
                if isinstance(value, list):
                    hard_items.extend(str(item) for item in value if str(item or "").strip())

        if not hard_items:
            return

        existing = {item.strip() for item in decision.forbidden_reveals if item.strip()}
        merged = list(decision.forbidden_reveals)
        for item in hard_items:
            text = item.strip()
            if text and text not in existing:
                merged.append(text)
                existing.add(text)
        decision.forbidden_reveals = merged

    @staticmethod
    def _filter_materials_by_director(
        materials: list[StoryMaterialResult],
        active_titles: list[str],
    ) -> list[StoryMaterialResult]:
        if not active_titles:
            return materials
        wanted = {str(title).strip() for title in active_titles if str(title or "").strip()}
        if not wanted:
            return materials
        filtered = [
            result
            for result in materials
            if str(result.material.get("title") or "").strip() in wanted
        ]
        # Director 可能漏掉关键素材或挑错标题；空集时退回全集，避免 GM 失盲。
        return filtered or materials

    async def _validate_and_maybe_rewrite(
        self,
        *,
        context: TurnRuntimeContext,
        director_decision: StoryDirectorDecision,
        runtime_output: GMRuntimeOutput,
        model_used: str,
        on_update: GameplayStreamUpdateCallback | None = None,
        on_progress: GameplayProgressCallback | None = None,
        on_stage: GameplayStageCallback | None = None,
    ) -> tuple[GMRuntimeOutput, str]:
        validation = await self.drift_validator.validate(
            game=context.game,
            player_input=context.player_input,
            recent_turns=context.recent_turns,
            director_decision=director_decision,
            runtime_output=runtime_output,
            runtime_story=context.runtime_story_bare,
            state_v2=context.state_v2,
        )
        context.telemetry.drift_severity = validation.severity
        context.telemetry.drift_validation = validation.model_dump()
        if not self.drift_validator.should_rewrite(validation):
            return runtime_output, model_used

        context.telemetry.rewrite_triggered = True
        rewrite_instruction = self.drift_validator.rewrite_instruction(validation)
        await _emit_stage(on_stage, STAGE_GM_RUNTIME)
        if on_progress:
            await on_progress("偏离校验要求局部修订剧情，正在重写。")
        # 把上一次 GM 输出连同 drift 指令一起喂回 GM，让其做局部修订而非从零重写。
        rewrite_messages = self._build_contextual_runtime_messages(
            context=context,
            director_decision=director_decision,
            drift_rewrite_instruction=rewrite_instruction,
            previous_runtime_output=runtime_output,
        )
        if on_update is None:
            try:
                result = await asyncio.wait_for(
                    self.router.use_pro(
                        "gm_runtime_rewrite",
                        rewrite_messages,
                        json_mode=True,
                        max_tokens=GM_REWRITE_MAX_TOKENS,
                    ),
                    timeout=GM_RUNTIME_TIMEOUT_SECONDS,
                )
            except TimeoutError as exc:
                raise GameplayValidationError(
                    f"GM 重写超过 {int(GM_RUNTIME_TIMEOUT_SECONDS)} 秒。"
                ) from exc
            return self._parse_runtime_output(result.content), result.model

        return await asyncio.wait_for(
            self._collect_runtime_output_stream(
                rewrite_messages,
                on_update=on_update,
                max_tokens=GM_REWRITE_MAX_TOKENS,
            ),
            timeout=GM_RUNTIME_TIMEOUT_SECONDS,
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
        max_tokens: int = 12000,
    ) -> tuple[GMRuntimeOutput, str]:
        reasoning_parts: list[str] = []
        content_parts: list[str] = []
        model_used: str | None = None

        async for chunk in self.router.use_pro_stream(
            "gm_runtime",
            messages,
            json_mode=True,
            max_tokens=max_tokens,
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
