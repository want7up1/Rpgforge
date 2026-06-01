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
    gm_hard_constraints,
    redact_runtime_story_for_gm,
)

# system prompt 强约束分节：(分组, key, 标题)。顺序即呈现顺序，与 gm_hard_constraints 对应。
# 必须类在前（玩家"想看却没看到"的强约束），禁止类居中，命名一致最后。
_MUST = "本回合/本幕必须落实（强约束，凌驾于风格与节奏）"
_NOT = "绝对禁止（违反即判失败）"
_CANON = "命名与一致性"
_HARD_CONSTRAINT_LABELS: list[tuple[str, str, str]] = [
    (_MUST, "current_act", "当前幕目标与未完成锚点（本回合必须围绕推进）"),
    (_MUST, "must_follow", "必须遵守（must_follow）"),
    (_MUST, "reveal_rules", "信息揭露规则（reveal_rules）"),
    (_MUST, "continuity_rules", "连续性规则（continuity_rules）"),
    (_MUST, "gm_output_rules", "GM 输出规则（gm_output_rules）"),
    (_MUST, "core_mechanics", "核心机制规则（core_mechanics）"),
    (_NOT, "must_not", "绝对禁止（must_not）"),
    (_NOT, "current_act_forbidden_reveals", "当前幕禁止提前揭露（forbidden_reveals）"),
    (_NOT, "must_not_become", "本作绝不能演变成（must_not_become）"),
    (_NOT, "forbidden_drift", "禁止的剧情漂移方向（forbidden_drift）"),
    (_CANON, "canon_terms", "专有名词必须严格沿用原文，不得改写、另译或音译（canon_terms）"),
]


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

        # 在裁剪前抽取硬红线（裁剪不动 hard_rules/story_core/current_act，但顺序上先抽更稳）。
        system_content = self._build_system_content(runtime_story, generation_parameters)
        # GM 不应看到完整的未来幕剧情（next_act 细节 / 未来幕主线节点），从源头裁掉。
        gm_runtime_story = redact_runtime_story_for_gm(runtime_story)

        runtime_payload = {
            "game": {
                "id": str(game.id),
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
            },
            "generation_parameters": generation_parameters,
            "runtime_story": gm_runtime_story,
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
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": json.dumps(runtime_payload, ensure_ascii=False, default=str),
            },
        ]

    @staticmethod
    def _build_system_content(
        runtime_story: dict[str, Any] | None,
        generation_parameters: dict[str, int] | None = None,
    ) -> str:
        """gm_runtime.md 基础规则 + 本剧本强约束 + 输出篇幅硬指标（都提进 system prompt）。

        强约束/篇幅参数原本埋在 user JSON 里、占比 <4% 且被 current_state_v2 淹没，
        模型遵守度极低。提到 system 末尾，确保 GM 一定看到。篇幅指标把 generation_parameters
        的具体数字直接写死进 system（而非让 GM 去 user JSON 深处找），对应 output_observer 的校验。
        """
        template = load_prompt_template("gm_runtime.md")
        constraints = gm_hard_constraints(runtime_story or {})

        # 按分组聚合各分节，保持 _HARD_CONSTRAINT_LABELS 的顺序。
        grouped: dict[str, list[str]] = {}
        order: list[str] = []
        for group, key, label in _HARD_CONSTRAINT_LABELS:
            items = constraints.get(key) or []
            if not items:
                continue
            if group not in grouped:
                grouped[group] = []
                order.append(group)
            lines = "\n".join(f"- {item}" for item in items)
            grouped[group].append(f"〔{label}〕\n{lines}")

        sections: list[str] = [template]

        if order:
            blocks = [f"## {group}\n\n" + "\n\n".join(grouped[group]) for group in order]
            body = "\n\n".join(blocks)
            sections.append(
                "=== 本剧本不可违反的强约束（最高优先级，凌驾于上文一切风格与节奏要求）===\n"
                "以下条目来自剧本设定，必须逐条严格落实；与任何其他指令冲突时以本节为准。\n"
                "尤其是「必须落实」组——这些不是可选风格，而是每个相关回合都要在 narrative 中"
                "真实体现的硬性要求。\n\n"
                f"{body}"
            )

        directives = _generation_parameter_directives(generation_parameters or {})
        if directives:
            sections.append(directives)

        return "\n\n".join(sections)

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


def _generation_parameter_directives(generation_parameters: dict[str, int] | None) -> str:
    """把 generation_parameters 的篇幅约束写成 system prompt 里的明确数字指令。

    Round 20 观测层实测：GM 长期字数不达硬下限（~70%）、段落/强调频繁越界——因为这些
    数量约束埋在 user JSON 的 generation_parameters 里，模型不遵守。这里把具体数字直接
    提进 system，对应 output_observer 的 generation 校验。
    """
    gp = generation_parameters if isinstance(generation_parameters, dict) else {}
    if not gp:
        return ""

    def _int(key: str) -> int | None:
        value = gp.get(key)
        return int(value) if isinstance(value, int) else None

    nmin = _int("narrative_min_chars")
    tmin = _int("narrative_target_min_chars")
    tmax = _int("narrative_target_max_chars")
    pmin = _int("paragraph_min")
    pmax = _int("paragraph_max")
    smax = _int("scene_heading_max")
    emin = _int("emphasis_min")
    emax = _int("emphasis_max")

    lines: list[str] = []
    if nmin:
        target = f"（目标 {tmin}–{tmax} 字）" if tmin and tmax else ""
        lines.append(
            f"- narrative 正文不少于 {nmin} 字{target}；字数不足视为偷工，"
            "宁可补充感官细节、NPC 反应、场景推进，也不要草草收尾。"
        )
    if pmin and pmax:
        lines.append(f"- 自然段控制在 {pmin}–{pmax} 段；不要碎成几十个短段，也不要堆成一大坨。")
    if smax is not None:
        lines.append(f"- 场景标题（`###`/`####`）本回合最多 {smax} 个；同场景承接时通常 0 个。")
    if emin is not None and emax:
        lines.append(f"- 重点强调（`**`）控制在 {emin}–{emax} 处；不要滥用加粗。")
    if not lines:
        return ""

    return (
        "=== 本回合输出篇幅硬指标（必须满足，系统会逐项校验）===\n" + "\n".join(lines)
    )
