import json
from typing import Any

from app.models.game import Game
from app.models.turn import Turn
from app.schemas.turn import GMRuntimeOutput
from app.services.act_pacing import compute_act_pacing
from app.services.prompt_loader import load_prompt_template
from app.services.state_v2 import project_state_for_scene, state_v2_view
from app.services.story_settings import (
    StoryMaterialResult,
    build_runtime_story,
    generation_parameters_from_config,
    gm_hard_constraints,
    redact_runtime_story_for_gm,
)

# system prompt 强约束分节：(分组, key, 标题)。顺序即呈现顺序，与 gm_hard_constraints 对应。
_MUST = "本回合/本幕必须落实（强约束，凌驾于风格与节奏）"
_NOT = "绝对禁止（违反即判失败）"
_CANON = "命名与一致性"

# 宪法层（整局不变）：放 system 最前，保证逐回合字节一致以命中 DeepSeek prefix cache。
# 注意：不含 current_act / current_act_forbidden_reveals —— 那是会随幕推进变化的"幕级"
# 内容，放在 system 末尾的幕级简报里（见 _ACT_BRIEF_LABELS / Round 22c）。
_CONSTITUTION_LABELS: list[tuple[str, str, str]] = [
    (_MUST, "must_follow", "必须遵守（must_follow）"),
    (_MUST, "reveal_rules", "信息揭露规则（reveal_rules）"),
    (_MUST, "continuity_rules", "连续性规则（continuity_rules）"),
    (_MUST, "gm_output_rules", "GM 输出规则（gm_output_rules）"),
    (_MUST, "core_mechanics", "核心机制规则（core_mechanics）"),
    (_NOT, "must_not", "绝对禁止（must_not）"),
    (_NOT, "must_not_become", "本作绝不能演变成（must_not_become）"),
    (_NOT, "forbidden_drift", "禁止的剧情漂移方向（forbidden_drift）"),
    (_CANON, "canon_terms", "专有名词必须严格沿用原文，不得改写、另译或音译（canon_terms）"),
]

# 幕级简报（随幕推进变化）：放 system 末尾，cache 前缀在此之前已稳定命中。
_ACT_BRIEF_LABELS: list[tuple[str, str]] = [
    ("current_act", "当前幕目标（本回合围绕推进；未完成锚点见 current_state_v2 与 runtime_story）"),
    ("current_act_forbidden_reveals", "当前幕禁止提前揭露（forbidden_reveals）"),
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
        # 同时把已提进 system 工艺层的 story_core 工艺字段从 user payload 剥掉（不重复下发）。
        gm_runtime_story = _strip_craft_from_story_core(redact_runtime_story_for_gm(runtime_story))
        # 多段切分（Round 48）：把 runtime_story 的逐回合部分抽到 payload 尾段，让「静态剧本设定」
        # 进 prefix cache 可缓存前缀。GM 信息不丢、只换位置（见 gm_runtime 规则 21/30）。
        static_story, open_anchors = _split_runtime_story_for_cache(gm_runtime_story)

        runtime_payload = {
            # —— 稳定段（整局/幕内不变，进可缓存前缀）——
            "game": {
                "id": str(game.id),
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
            },
            "generation_parameters": generation_parameters,
            "runtime_story": static_story,
            # —— 逐回合快变段（DeepSeek prefix cache 在此之后断裂）——
            "current_act_open_anchors": open_anchors,
            # 本幕节奏压力（确定性，逐回合变）：rising/high 时要求 A/B/C/D 至少留一条推向
            # next_required_anchor 的前进选项，禁止四个全是休整/原地重复（见 gm_runtime 规则 36）。
            "act_pacing": compute_act_pacing(state_v2, runtime_story),
            # GM 只需当前场景相关状态，用场景投影砍掉历史/非在场噪声（省 token）。
            "current_state_v2": project_state_for_scene(state_v2),
            "selected_action_style": selected_action_style or {},
            "related_story_materials": [
                self._retrieval_payload(result) for result in (related_materials or [])
            ],
            "memory_summaries": summaries or {},
            "story_director": _gm_facing_director(story_director),
            "drift_rewrite_instruction": drift_rewrite_instruction or "",
            "previous_gm_output": (
                previous_runtime_output.model_dump() if previous_runtime_output else None
            ),
            # recent_turns 升序（旧→新）；最近 _RECENT_FULL_TURNS 回合附完整正文供承接。
            "recent_turns": [
                self._turn_payload(
                    turn,
                    generation_parameters["recent_turn_excerpt_chars"],
                    full=index >= len(recent_turns) - _RECENT_FULL_TURNS,
                )
                for index, turn in enumerate(recent_turns)
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
        """gm_runtime.md 基础规则 + 宪法层强约束 + 篇幅指引 + 幕级简报（都提进 system prompt）。

        **分层顺序即 DeepSeek prefix cache 友好度的关键**（Round 22c 宪法层字节固化）：
        前面放整局不变的内容（模板 + 宪法层强约束 + 篇幅指引），逐回合字节一致 → 命中缓存；
        会随幕推进变化的"幕级简报"（当前幕目标/未完成锚点/当前幕禁止揭露）放最末尾，
        让缓存断裂点尽量靠后。实测此前断裂在第 ~3467 字符（未完成锚点列表），命中率仅 ~4.5%。

        强约束/篇幅原本埋在 user JSON 里被 current_state_v2 淹没、模型遵守度极低，提进 system
        确保 GM 一定看到；篇幅指标把 generation_parameters 具体数字写死，对应 output_observer 校验。
        """
        template = load_prompt_template("gm_runtime.md")
        constraints = gm_hard_constraints(runtime_story or {})

        sections: list[str] = [template]

        # 1) 宪法层（整局不变）+ 2) 篇幅指引（generation_parameters 整局不变）——稳定前缀。
        constitution = _render_constraint_groups(constraints, _CONSTITUTION_LABELS)
        if constitution:
            sections.append(
                "=== 本剧本不可违反的强约束（宪法层·整局不变·最高优先级）===\n"
                "以下条目来自剧本设定，必须逐条严格落实；与任何其他指令冲突时以本节为准。\n"
                "尤其是「必须落实」组——这些不是可选风格，而是每个相关回合都要在 narrative 中"
                "真实体现的硬性要求。\n\n"
                f"{constitution}"
            )
        # 叙事工艺层（整局静态 story_core 字段）——与合规层对称提进 system 稳定前缀，
        # 让模型在"看得最清"的位置同时看到"怎么把故事写好"，而非只看到"别违规"。
        craft = _narrative_craft_directives(runtime_story or {})
        if craft:
            sections.append(craft)
        directives = _generation_parameter_directives(generation_parameters or {})
        if directives:
            sections.append(directives)

        # 3) 幕级简报（随幕推进变化）—— 放最末尾，缓存前缀在此之前已稳定。
        act_brief_lines: list[str] = []
        for key, label in _ACT_BRIEF_LABELS:
            items = constraints.get(key) or []
            if items:
                lines = "\n".join(f"- {item}" for item in items)
                act_brief_lines.append(f"〔{label}〕\n{lines}")
        if act_brief_lines:
            sections.append(
                "=== 当前幕简报（随剧情推进变化，本回合需围绕推进）===\n"
                + "\n\n".join(act_brief_lines)
            )

        return "\n\n".join(sections)

    def _retrieval_payload(self, result: StoryMaterialResult) -> dict[str, object]:
        payload = dict(result.material)
        payload["retrieval"] = {
            "score": result.score,
            "matched_terms": result.matched_terms,
        }
        return payload

    @staticmethod
    def _turn_payload(turn: Turn, excerpt_chars: int, full: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "turn_number": turn.turn_number,
            "player_input": turn.player_input,
            "visible_summary": turn.visible_summary,
            "hidden_summary": turn.hidden_summary,
            "action_options": turn.action_options_json,
        }
        if full:
            # 最近 _RECENT_FULL_TURNS 回合给完整正文供 GM 承接上一回合结尾；不再附
            # gm_output_excerpt（它是完整正文的前缀子串，纯冗余浪费 token）。
            payload["gm_output"] = _trim_text(turn.gm_output, _RECENT_FULL_CHARS)
        else:
            payload["gm_output_excerpt"] = _trim_text(turn.gm_output, excerpt_chars)
        return payload


def _trim_text(value: str | None, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _render_constraint_groups(
    constraints: dict[str, list[str]],
    labels: list[tuple[str, str, str]],
) -> str:
    """按 (分组, key, 标题) 渲染强约束分节，保持 labels 顺序、按分组聚合。"""
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    for group, key, label in labels:
        items = constraints.get(key) or []
        if not items:
            continue
        if group not in grouped:
            grouped[group] = []
            order.append(group)
        lines = "\n".join(f"- {item}" for item in items)
        grouped[group].append(f"〔{label}〕\n{lines}")
    if not order:
        return ""
    blocks = [f"## {group}\n\n" + "\n\n".join(grouped[group]) for group in order]
    return "\n\n".join(blocks)


# GM 视角丢弃的导演字段：这两项最易被 GM 当成“必须逐条用上并加粗”的填空清单，
# 制造“生搬硬套素材/义务复述线索”（Round 44 审计）。GM 自己读 runtime_story + 召回素材
# 即可保持一致性；这两项仍保留在 StateExtractor 的 director_hints（异步维护）里。
_GM_DROP_DIRECTOR_KEYS = ("continuity_notes", "active_material_titles")

# 最近多少回合在 recent_turns 里附完整正文（供 GM 承接上一回合结尾，治"同地点重述"）。
# 完整正文进不缓存的 user payload、每回合复发，净增约 _RECENT_FULL_TURNS×min(正文,上限) 字/回合。
_RECENT_FULL_TURNS = 2
_RECENT_FULL_CHARS = 1800


def _gm_facing_director(story_director: dict[str, object] | None) -> dict[str, object]:
    """返回去掉清单式字段后的导演决策，仅用于 GM payload。"""
    if not isinstance(story_director, dict):
        return {}
    return {k: v for k, v in story_director.items() if k not in _GM_DROP_DIRECTOR_KEYS}


# 叙事工艺层取自 story_core 的整局静态字段（不随回合/幕变化 → 稳定前缀安全）。
_CRAFT_TEXT_LABELS = (
    ("narrative_style", "叙事文风"),
    ("core_fantasy", "核心幻想 / 想给玩家的体验"),
    ("emotional_arc", "整体情绪弧线"),
)
_CRAFT_LIST_LABELS = (
    ("tone_do", "必须保持的味道"),
    ("tone_dont", "不能滑向的味道"),
    ("pacing_rules", "节奏规则"),
)


def _narrative_craft_directives(runtime_story: dict[str, Any] | None) -> str:
    """把本剧本的文风/情绪基调提进 system（Round 45 叙事工艺层）。

    与合规「宪法层」对称：合规告诉 GM「别违反什么」，工艺层告诉 GM「这局该写成什么味道」，
    让正文像小说而非规则执行报告。只取整局静态字段，全空则返回 ""（不污染 system / cache）。
    """
    story_core = runtime_story.get("story_core") if isinstance(runtime_story, dict) else None
    if not isinstance(story_core, dict):
        return ""

    lines: list[str] = []
    for key, label in _CRAFT_TEXT_LABELS:
        text = str(story_core.get(key) or "").strip()
        if text:
            lines.append(f"- 〔{label}〕{text}")
    for key, label in _CRAFT_LIST_LABELS:
        raw = story_core.get(key)
        if not isinstance(raw, list):
            continue
        items = [str(item).strip() for item in raw if str(item).strip()]
        if items:
            lines.append(f"- 〔{label}〕" + "；".join(items))

    if not lines:
        return ""

    return (
        "=== 本剧本叙事工艺（整局不变·与合规约束同等优先）===\n"
        "下面是本局的文风与情绪基调。你首先是小说家，其次才是规则执行者：每回合都要让正文"
        "真正体现这些味道，用画面、动作、对白和人物内心把故事讲好，而不是机械满足约束。\n"
        "注意：「把故事讲好/像小说」指的是工艺（逻辑、人物、画面），不是要含蓄或得体——"
        "内容强度与露骨/黑暗尺度一律以本剧本设定为准，不要用主流文学惯例自我收口或淡化。\n"
        + "\n".join(lines)
    )


# 已提进 system 工艺层的 story_core 字段——从 GM 的 user payload story_core 中剥掉，避免重复下发。
_CRAFT_STORY_CORE_KEYS = tuple(key for key, _ in (*_CRAFT_TEXT_LABELS, *_CRAFT_LIST_LABELS))


def _strip_craft_from_story_core(runtime_story: dict[str, Any] | None) -> dict[str, Any] | None:
    """返回 story_core 已剥掉工艺字段的 runtime_story 浅拷贝（工艺层已在 system 高优先级注入）。"""
    if not isinstance(runtime_story, dict):
        return runtime_story
    core = runtime_story.get("story_core")
    if not isinstance(core, dict):
        return runtime_story
    stripped = {k: v for k, v in core.items() if k not in _CRAFT_STORY_CORE_KEYS}
    return {**runtime_story, "story_core": stripped}


# runtime_story 里逐回合变化、必须移出可缓存前缀的键（GM 从 payload 尾段 / current_state_v2
# 读到同样信息）：story_progress（state_v2 已带）、行动风格 / 召回素材（尾段已单列）。
_RUNTIME_STORY_VOLATILE_KEYS = (
    "story_progress",
    "selected_action_style",
    "related_story_materials",
)


def _split_runtime_story_for_cache(
    runtime_story: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[Any]]:
    """把 GM runtime_story 拆成「静态（幕内不变，进可缓存前缀）」+「当前幕未完成锚点（逐回合）」。

    抽走逐回合内容：上面的 volatile keys + current_act.completion_anchors（随完成逐回合缩短）。
    返回 (static_runtime_story, open_anchors)。GM 信息不丢，只是换到 payload 尾段（见规则 21/30）。
    """
    if not isinstance(runtime_story, dict):
        return runtime_story, []
    static = {k: v for k, v in runtime_story.items() if k not in _RUNTIME_STORY_VOLATILE_KEYS}
    open_anchors: list[Any] = []
    current_act = static.get("current_act")
    if isinstance(current_act, dict):
        anchors = current_act.get("completion_anchors")
        open_anchors = list(anchors) if isinstance(anchors, list) else []
        static["current_act"] = {
            k: v for k, v in current_act.items() if k != "completion_anchors"
        }
    return static, open_anchors


def _generation_parameter_directives(generation_parameters: dict[str, int] | None) -> str:
    """把篇幅指引写成 system prompt 里的软目标（Round 44 去配额化）。

    旧版（Round 20/21）把“硬下限/字数不足视为偷工 + emphasis 配额”写进 system，实测会把
    低事件回合逼成注水复述、为凑配额假加粗——正是用户反馈的“生硬/生搬硬套”来源之一。改为：
    篇幅按事件信息量自然成文，只留极低地板防敷衍；强调宁缺毋滥。output_observer 仍观测、不视为违规。
    """
    gp = generation_parameters if isinstance(generation_parameters, dict) else {}
    if not gp:
        return ""

    def _int(key: str) -> int | None:
        value = gp.get(key)
        return int(value) if isinstance(value, int) else None

    tmin = _int("narrative_target_min_chars")
    tmax = _int("narrative_target_max_chars")
    pmin = _int("paragraph_min")
    pmax = _int("paragraph_max")
    smax = _int("scene_heading_max")

    floor = 250
    lines: list[str] = []
    natural = f"（自然篇幅一般 {tmin}–{tmax} 字，仅供参考、不是考核）" if tmin and tmax else ""
    lines.append(
        f"- 【篇幅·按信息量自然成文】根据本回合实际发生的事件量决定长度{natural}："
        "事件密集就写充分，事件少（独白、过场、纯对话、玩家只是闲逛或休整）就写得短而精、克制，"
        f"绝不为凑字数注水、反复复述已知设定或空泛铺陈拖长；只有当正文短到约 {floor} 字以下时，"
        "才回头检查是否敷衍、漏写了应有的反应与推进。"
    )
    soft: list[str] = []
    if pmin and pmax:
        soft.append(f"自然段按需 {pmin}–{pmax} 段、长短有致、有呼吸感")
    if smax is not None:
        soft.append(f"场景标题（`###`）一般不超过 {smax} 个、同场景承接时通常 0 个")
    soft.append("`**重点**` 只用于真正关键的线索/物品/异常，宁缺毋滥、没有就不加，绝不为凑数加粗")
    if soft:
        lines.append("- 【格式·软参考·服务叙事·可被剧本覆盖】" + "；".join(soft) + "。")
    if soft:
        lines.append(
            "- 【优先级】凡 hard_rules / core_mechanics 要求“完整/详细描写”的场景"
            "（如[剧情规则]、战斗色情化、[剧情规则]、性征刻画、日常调教等），必须优先写完整；"
            "此时段落数、强调数与篇幅上限一律让位于剧本要求，不受上述软参考限制（但仍不得低于硬下限）。"
        )
    if not lines:
        return ""

    return "=== 本回合输出篇幅指引 ===\n" + "\n".join(lines)
