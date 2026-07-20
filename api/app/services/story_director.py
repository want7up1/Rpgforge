from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.models.game import Game
from app.models.turn import Turn
from app.services.act_pacing import compute_act_pacing
from app.services.deepseek_client import DeepSeekError
from app.services.json_utils import parse_json_object
from app.services.model_router import ModelRouter
from app.services.prompt_loader import load_prompt_template
from app.services.state_v2 import state_v2_view
from app.services.story_settings import StoryMaterialResult, build_runtime_story

logger = logging.getLogger(__name__)

STORY_DIRECTOR_TIMEOUT_SECONDS = 90.0
STORY_DIRECTOR_MAX_TOKENS = 3000
# 喂给 Director 的近期回合 gm_output 截断长度。Director 只需要"上一回合发生了什么"
# 的摘要，完整 narrative 已经被 GM 用过，没必要再给 Director 看一次。
DIRECTOR_RECENT_TURN_EXCERPT_CHARS = 320


class StoryDirectorDecision(BaseModel):
    player_intent: str = ""
    current_act: str = ""
    scene_objective: str = ""
    mode_recommendation: str = ""
    active_material_titles: list[str] = Field(default_factory=list)
    allowed_reveals: list[str] = Field(default_factory=list)
    forbidden_reveals: list[str] = Field(default_factory=list)
    pacing_limit: str = ""
    continuity_notes: list[str] = Field(default_factory=list)
    gm_instruction: str = ""
    # 纯叙事化定性赌注（替代已删的 d20 action_check）：有不确定性的行动，Director 用文字
    # 点出本场风险点与失败代价，GM 据此按故事逻辑决定成败——无骰子、无数值。
    # 纯对话/叙述/继续时留空，GM 自由发挥。
    risk_note: str = ""
    cost_if_fails: str = ""
    # Telemetry only: 表示本次决策是否走了本地 fallback，不参与 GM 提示词。
    used_fallback: bool = False

    @field_validator(
        "active_material_titles",
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
        selected_action_style: dict[str, Any] | None,
        recent_turns: list[Turn],
        related_materials: list[StoryMaterialResult],
        summaries: dict[str, Any],
        runtime_story: dict[str, Any] | None = None,
        state_v2: dict[str, Any] | None = None,
    ) -> StoryDirectorDecision:
        payload = self._payload(
            game=game,
            player_input=player_input,
            selected_action_style=selected_action_style,
            recent_turns=recent_turns,
            related_materials=related_materials,
            summaries=summaries,
            runtime_story=runtime_story,
            state_v2=state_v2,
        )
        messages = [
            {"role": "system", "content": load_prompt_template("story_director.md")},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]
        try:
            result = await asyncio.wait_for(
                self.router.use_flash(
                    "story_director",
                    messages,
                    json_mode=True,
                    max_tokens=STORY_DIRECTOR_MAX_TOKENS,
                    reasoning_effort=None,
                ),
                timeout=STORY_DIRECTOR_TIMEOUT_SECONDS,
            )
            parsed = parse_json_object(result.content)
            decision = StoryDirectorDecision.model_validate(parsed)
            decision.used_fallback = False
            return decision
        except TimeoutError:
            logger.warning(
                "Story director timed out after %.0fs for game %s; using fallback decision.",
                STORY_DIRECTOR_TIMEOUT_SECONDS,
                game.id,
            )
            return self._fallback_decision(game, player_input, selected_action_style)
        except (DeepSeekError, ValueError, ValidationError) as exc:
            logger.warning("Story director fell back for game %s: %s", game.id, exc)
            return self._fallback_decision(game, player_input, selected_action_style)

    def _payload(
        self,
        *,
        game: Game,
        player_input: str,
        selected_action_style: dict[str, Any] | None,
        recent_turns: list[Turn],
        related_materials: list[StoryMaterialResult],
        summaries: dict[str, Any],
        runtime_story: dict[str, Any] | None = None,
        state_v2: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state_json = game.state.state_json if game.state else {}
        if runtime_story is None:
            runtime_story = build_runtime_story(
                game.config,
                state_json,
                selected_action_style=selected_action_style,
                related_materials=related_materials,
            )
        if state_v2 is None:
            state_v2 = state_v2_view(state_json)
        return {
            "game": {
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
            },
            "runtime_story": runtime_story,
            # 本幕节奏压力（确定性算出，非 LLM 估算）：驱动 scene_objective 在停留过久时
            # 主动把戏推向 next_required_anchor（见 story_director.md 规则 13）。
            "act_pacing": compute_act_pacing(state_v2, runtime_story),
            "selected_action_style": selected_action_style or {},
            "current_state_v2": state_v2,
            "memory_summaries": summaries,
            "recent_turns": [self._turn_payload(turn) for turn in recent_turns],
            "related_story_materials": [
                {
                    "title": result.material.get("title"),
                    "type": result.material.get("type"),
                    "usage": result.material.get("usage"),
                    "retrieval": {
                        "score": result.score,
                        "matched_terms": result.matched_terms,
                    },
                }
                for result in related_materials
            ],
            "player_input": player_input,
        }

    @staticmethod
    def _turn_payload(turn: Turn) -> dict[str, Any]:
        return {
            "turn_number": turn.turn_number,
            "player_input": turn.player_input,
            # Director 不需要完整 narrative，给摘要 + 截断片段即可。
            "gm_output_excerpt": _trim_text(turn.gm_output, DIRECTOR_RECENT_TURN_EXCERPT_CHARS),
            "visible_summary": turn.visible_summary,
            "action_options": turn.action_options_json,
        }

    @classmethod
    def _fallback_decision(
        cls,
        game: Game,
        player_input: str,
        selected_action_style: dict[str, Any] | None,
    ) -> StoryDirectorDecision:
        runtime_story = build_runtime_story(
            game.config,
            game.state.state_json if game.state else {},
            selected_action_style=selected_action_style,
        )
        core = runtime_story.get("story_core") if isinstance(runtime_story, dict) else {}
        if not isinstance(core, dict):
            core = {}
        current_act = runtime_story.get("current_act") if isinstance(runtime_story, dict) else {}
        if not isinstance(current_act, dict):
            current_act = {}
        return StoryDirectorDecision(
            used_fallback=True,
            player_intent=player_input,
            current_act=str(
                current_act.get("id")
                or current_act.get("name")
                or core.get("current_act")
                or ""
            ),
            scene_objective=str(
                current_act.get("objective")
                or current_act.get("dramatic_question")
                or core.get("main_goal")
                or core.get("premise")
                or ""
            ),
            mode_recommendation=str((selected_action_style or {}).get("name") or ""),
            allowed_reveals=_string_list(current_act.get("allowed_reveals")),
            forbidden_reveals=_string_list(current_act.get("forbidden_reveals")),
            pacing_limit=str(
                current_act.get("escalation_limit")
                or "保持当前幕节奏，不提前引入未铺垫的大型势力、Boss 或终局真相。"
            ),
            gm_instruction="先回应玩家本次行动的直接结果，再推进当前幕目标。",
        )


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item or "").strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _trim_text(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."
