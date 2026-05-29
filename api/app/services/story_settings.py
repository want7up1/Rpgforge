from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.game import GameConfig
from app.models.turn import Turn
from app.services.generation_parameters import normalize_generation_parameters
from app.services.text_vectorizer import extract_terms

STORY_SETTINGS_FORMAT_VERSION = "rpgforge.story.v2"
ACT_LIMIT = 8
ANCHOR_LIMIT = 16
MATERIAL_LIMIT = 12
CHARACTER_LIMIT = 24
QUEST_LIMIT = 16


@dataclass(frozen=True)
class StoryMaterialResult:
    material: dict[str, Any]
    score: float
    matched_terms: list[str]


def default_story_settings(
    title: str,
    genre: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    return normalize_story_settings(
        {
            "format_version": STORY_SETTINGS_FORMAT_VERSION,
            "game_profile": {
                "title": title,
                "genre": genre or "",
                "description": description or "",
                "tone": "",
            },
            "worldview": {
                "summary": description or "",
                "public_facts": [],
                "hidden_facts": [],
            },
            "story_core": {
                "premise": description or "",
                "core_fantasy": "",
                "central_mystery": "",
                "main_goal": "",
                "current_act": "act_1",
                "must_preserve": [],
                "must_not_become": [],
                "forbidden_drift": [],
                "canon_terms": [],
            },
            "core_characters": [],
            "act_plan": [],
            "main_quest_path": [],
            "core_mechanics": [],
            "action_style_rules": [],
            "story_material_library": [],
            "home_base": {},
            "hard_rules": {
                "must_follow": [],
                "must_not": [],
                "reveal_rules": [],
                "continuity_rules": [],
            },
            "generation_parameters": normalize_generation_parameters({}),
        }
    )


def normalize_story_settings(settings: Any) -> dict[str, Any]:
    if not isinstance(settings, dict):
        raise ValueError("story_settings 必须是 JSON 对象。")
    source = dict(settings)
    profile = _record(source.get("game_profile"))
    core = _record(source.get("story_core"))
    hard_rules = _record(source.get("hard_rules"))

    normalized = {
        "format_version": STORY_SETTINGS_FORMAT_VERSION,
        "game_profile": _object_with_extra(
            {
                "title": _text(profile.get("title")) or "未命名游戏",
                "genre": _text(profile.get("genre")),
                "description": _text(profile.get("description")),
                "tone": _text(profile.get("tone")),
                "logline": _text(profile.get("logline")),
            },
            profile,
        ),
        "worldview": _record(source.get("worldview")),
        "story_core": _object_with_extra(
            {
                "premise": _text(core.get("premise")),
                "core_fantasy": _text(core.get("core_fantasy")),
                "central_mystery": _text(
                    core.get("central_mystery") or core.get("central_question")
                ),
                "main_goal": _text(core.get("main_goal")),
                "emotional_arc": _text(core.get("emotional_arc")),
                "narrative_style": _text(core.get("narrative_style")),
                "current_act": _text(core.get("current_act")) or "act_1",
                "must_preserve": _strings(core.get("must_preserve")),
                "must_not_become": _strings(core.get("must_not_become")),
                "forbidden_drift": _strings(core.get("forbidden_drift")),
                "canon_terms": _strings(core.get("canon_terms")),
            },
            core,
        ),
        "core_characters": [
            _character(item) for item in _records(source.get("core_characters"))
        ],
        "act_plan": [
            _act(item, index)
            for index, item in enumerate(_records(source.get("act_plan")))
        ],
        "main_quest_path": [
            _quest(item, index)
            for index, item in enumerate(_records(source.get("main_quest_path")))
        ],
        "core_mechanics": [
            _named_record(item, "未命名机制")
            for item in _records(source.get("core_mechanics"))
        ],
        "action_style_rules": [
            _action_style(item)
            for item in _records(source.get("action_style_rules"))
        ],
        "story_material_library": [
            _material(item)
            for item in _records(source.get("story_material_library"))
        ],
        "home_base": _record(source.get("home_base")),
        "hard_rules": _object_with_extra(
            {
                "must_follow": _strings(hard_rules.get("must_follow")),
                "must_not": _strings(hard_rules.get("must_not")),
                "reveal_rules": _strings(hard_rules.get("reveal_rules")),
                "continuity_rules": _strings(hard_rules.get("continuity_rules")),
            },
            hard_rules,
        ),
        "generation_parameters": normalize_generation_parameters(
            source.get("generation_parameters")
        ),
    }
    return normalized


def story_settings_from_config(config: GameConfig | None) -> dict[str, Any]:
    if config is None:
        return default_story_settings("未命名游戏")
    try:
        return normalize_story_settings(config.story_settings or {})
    except ValueError:
        return default_story_settings("未命名游戏")


def game_profile(settings: dict[str, Any]) -> dict[str, str]:
    story = normalize_story_settings(settings)
    profile = _record(story.get("game_profile"))
    return {
        "title": _text(profile.get("title")) or "未命名游戏",
        "genre": _text(profile.get("genre")),
        "description": _text(profile.get("description")),
    }


def generation_parameters_from_config(config: GameConfig | None) -> dict[str, int]:
    story = story_settings_from_config(config)
    return normalize_generation_parameters(story.get("generation_parameters"))


def build_runtime_story(
    config: GameConfig | None,
    state_json: dict[str, Any] | None,
    *,
    selected_action_style: dict[str, Any] | None = None,
    related_materials: list[StoryMaterialResult] | None = None,
) -> dict[str, Any]:
    story = story_settings_from_config(config)
    progress = story_progress_from_state(state_json)
    current_act_id = _runtime_current_act_id(story, progress)
    current_act = _current_act(story, current_act_id)
    completed_anchors = set(_strings(progress.get("completed_anchors")))
    open_anchors = [
        anchor
        for anchor in _records(current_act.get("completion_anchors"))
        if _text(anchor.get("id")) not in completed_anchors
    ]
    next_act = _next_act(story, current_act)

    runtime_current_act = dict(current_act)
    runtime_current_act["completion_anchors"] = open_anchors[:ANCHOR_LIMIT]

    return _drop_empty(
        {
            "format_version": STORY_SETTINGS_FORMAT_VERSION,
            "priority_order": [
                "hard_rules",
                "story_core",
                "worldview",
                "act_plan.current_act",
                "main_quest_path",
                "core_characters",
                "home_base",
                "core_mechanics",
                "action_style_rules",
                "story_material_library",
                "generation_parameters",
                "current_state_v2",
                "recent_turns",
            ],
            "game_profile": story["game_profile"],
            "hard_rules": story["hard_rules"],
            "story_core": story["story_core"],
            "worldview": story["worldview"],
            "current_act": runtime_current_act,
            "next_act": next_act,
            "story_progress": {
                "current_act": current_act_id,
                "completed_acts": progress.get("completed_acts", []),
                "completed_anchors": progress.get("completed_anchors", []),
                "ready_for_next_act": progress.get("ready_for_next_act", False),
                "last_advance_turn": progress.get("last_advance_turn"),
                "last_advance_reason": progress.get("last_advance_reason", ""),
                "last_anchor_update_turn": progress.get("last_anchor_update_turn"),
            },
            "main_quest_path": story["main_quest_path"][:QUEST_LIMIT],
            "core_characters": story["core_characters"][:CHARACTER_LIMIT],
            "home_base": story["home_base"],
            "core_mechanics": story["core_mechanics"],
            "selected_action_style": selected_action_style or {},
            "related_story_materials": [
                {
                    **result.material,
                    "retrieval": {
                        "score": result.score,
                        "matched_terms": result.matched_terms,
                    },
                }
                for result in (related_materials or [])[:MATERIAL_LIMIT]
            ],
            "generation_parameters": story["generation_parameters"],
        }
    )


def redact_runtime_story_for_gm(runtime_story: dict[str, Any]) -> dict[str, Any]:
    """裁剪掉只该让 Director/DriftValidator 看、不该提前喂给 GM 的未来剧情。

    GM 写当前幕时，runtime_story 里完整的 next_act（objective/dramatic_question/
    allowed_reveals/completion_anchors）和未来幕的 main_quest_path 节点
    （player_visible/objective/completion_signal）就是"提前揭露"的弹药库——把答案
    递给模型再用 prompt 求它装不知道并不可靠。这里从源头砍掉：

    - next_act 只保留 id + title（供柔和转场方向判断，rule 29/32），删除会剧透
      结局/真相的 objective、dramatic_question、allowed_reveals、completion_anchors。
    - main_quest_path 中非当前幕的节点（过去或未来）只保留 id/title/act_id，删除
      player_visible/objective/completion_signal 等含未来真相的字段；当前幕节点保留全文。

    不修改 hard_rules / story_core / current_act / worldview —— 这些是 GM 必须看全的约束。
    返回新 dict，不改原对象（Director/DriftValidator 仍用未裁剪版）。
    """
    if not isinstance(runtime_story, dict):
        return runtime_story

    redacted = dict(runtime_story)

    next_act = runtime_story.get("next_act")
    if isinstance(next_act, dict) and next_act:
        slim_next: dict[str, Any] = {}
        if next_act.get("id"):
            slim_next["id"] = next_act["id"]
        if next_act.get("title"):
            slim_next["title"] = next_act["title"]
        redacted["next_act"] = slim_next

    current_act = runtime_story.get("current_act")
    current_id = _text(current_act.get("id")) if isinstance(current_act, dict) else ""
    quests = runtime_story.get("main_quest_path")
    if isinstance(quests, list) and current_id:
        slimmed: list[dict[str, Any]] = []
        for quest in quests:
            if not isinstance(quest, dict):
                continue
            act_id = _text(quest.get("act_id") or quest.get("act"))
            if act_id == current_id:
                slimmed.append(quest)
                continue
            node: dict[str, Any] = {}
            if quest.get("id"):
                node["id"] = quest["id"]
            if quest.get("title"):
                node["title"] = quest["title"]
            if act_id:
                node["act_id"] = act_id
            slimmed.append(node)
        redacted["main_quest_path"] = slimmed

    return redacted


def gm_hard_constraints(runtime_story: dict[str, Any]) -> dict[str, list[str]]:
    """从 runtime_story 抽出最该被 GM 严格遵守的强约束，供提升进 system prompt。

    这些约束本来就在 runtime_story JSON 里，但埋在深层数组、与大量"参考信息"平级，
    又被体积庞大的 current_state_v2（实测可占 user prompt 40%+）淹没，模型遵守度极低。
    抽出来显式列进 system prompt（最高权重、不被 user JSON 噪声冲淡），从传递层根治
    "剧本强约束在剧情里大部分看不到"。

    既含"禁止类"（must_not / forbidden_*），也含"必须类"（must_follow / 各 *_rules /
    当前幕目标与未完成锚点 / 核心机制规则）——后者是玩家"想看却没看到"的主要部分。
    """
    if not isinstance(runtime_story, dict):
        return {}

    hard_rules = _record(runtime_story.get("hard_rules"))
    story_core = _record(runtime_story.get("story_core"))
    current_act = _record(runtime_story.get("current_act"))

    # 当前幕目标 + 未完成必需锚点（build_runtime_story 已把 completion_anchors 过滤为未完成项）。
    act_lines: list[str] = []
    objective = _text(current_act.get("objective"))
    if objective:
        act_lines.append(f"本幕目标：{objective}")
    dramatic_question = _text(current_act.get("dramatic_question"))
    if dramatic_question:
        act_lines.append(f"核心戏剧问题：{dramatic_question}")
    for anchor in _records(current_act.get("completion_anchors")):
        required = "必需" if _bool(anchor.get("required"), True) else "可选"
        label = _text(anchor.get("title")) or _text(anchor.get("completion_signal"))
        if label and label != "未命名锚点":
            act_lines.append(f"[{required}锚点] {label}")

    # 核心机制规则（rule 文本，去掉纯展示用字段）。
    mechanic_lines: list[str] = []
    for mechanic in _records(runtime_story.get("core_mechanics")):
        rule = _text(mechanic.get("rule"))
        if not rule:
            continue
        name = _text(mechanic.get("name"))
        mechanic_lines.append(f"{name}：{rule}" if name else rule)

    return {
        "current_act": act_lines,
        "must_follow": _strings(hard_rules.get("must_follow")),
        "reveal_rules": _strings(hard_rules.get("reveal_rules")),
        "continuity_rules": _strings(hard_rules.get("continuity_rules")),
        "gm_output_rules": _strings(hard_rules.get("gm_output_rules")),
        "core_mechanics": mechanic_lines,
        "must_not": _strings(hard_rules.get("must_not")),
        "current_act_forbidden_reveals": _strings(current_act.get("forbidden_reveals")),
        "must_not_become": _strings(story_core.get("must_not_become")),
        "forbidden_drift": _strings(story_core.get("forbidden_drift")),
        "canon_terms": _strings(story_core.get("canon_terms")),
    }


def select_action_style(
    config: GameConfig | None,
    player_input: str,
) -> dict[str, Any] | None:
    story = story_settings_from_config(config)
    text = player_input.lower()
    candidates: list[tuple[float, int, int, dict[str, Any]]] = []
    for index, style in enumerate(_records(story.get("action_style_rules"))):
        if style.get("enabled") is False:
            continue
        score = 0.0
        for trigger in _strings(style.get("triggers")):
            trigger_lower = trigger.lower()
            if trigger_lower and trigger_lower in text:
                score += 2.0 if len(trigger_lower) >= 4 else 1.0
        name = _text(style.get("name"))
        if name and name.lower() in text:
            score += 1.5
        if score > 0:
            candidates.append((score, _priority_weight(style.get("priority")), -index, style))
    if candidates:
        return max(candidates, key=lambda item: (item[0], item[1], item[2]))[3]
    enabled = [
        style
        for style in _records(story.get("action_style_rules"))
        if style.get("enabled") is not False
    ]
    return enabled[0] if enabled else None


def retrieve_story_materials(
    config: GameConfig | None,
    *,
    player_input: str,
    selected_action_style: dict[str, Any] | None,
    state_json: dict[str, Any] | None,
    recent_turns: list[Turn],
    limit: int = MATERIAL_LIMIT,
) -> list[StoryMaterialResult]:
    story = story_settings_from_config(config)
    query_parts = [
        player_input,
        _text(_record(story["game_profile"]).get("title")),
        _text(_record(story["game_profile"]).get("genre")),
        _text(_record(story["story_core"]).get("main_goal")),
        _text(_record(story["story_core"]).get("central_mystery")),
        _text(_record(selected_action_style or {}).get("name")),
        _text(_record(selected_action_style or {}).get("rule")),
    ]
    state = _record(state_json)
    query_parts.extend(_strings(_record(state.get("location")).get("current")))
    for turn in recent_turns[-3:]:
        query_parts.extend([turn.player_input, turn.visible_summary or ""])
    query = "\n".join(part for part in query_parts if part)
    query_terms = set(_meaningful_terms(query))
    query_lower = query.lower()

    results: list[StoryMaterialResult] = []
    for material in _records(story.get("story_material_library")):
        if material.get("enabled") is False:
            continue
        score, matched = _material_score(material, query_terms, query_lower)
        always_on = bool(material.get("always_on"))
        if always_on:
            score += 10.0
        if score > 0 or always_on:
            results.append(
                StoryMaterialResult(
                    material=material,
                    score=round(score, 4),
                    matched_terms=matched[:12],
                )
            )
    return sorted(results, key=lambda result: result.score, reverse=True)[:limit]


def initial_story_progress(config: GameConfig | None) -> dict[str, Any]:
    story = story_settings_from_config(config)
    current_act = _text(_record(story.get("story_core")).get("current_act")) or _act_identity(
        _record(_list(story.get("act_plan"))[0] if story.get("act_plan") else {})
    )
    return {
        "current_act": current_act or "act_1",
        "completed_acts": [],
        "completed_anchors": [],
        "ready_for_next_act": False,
        "last_advance_turn": None,
        "last_advance_reason": "",
        "last_anchor_update_turn": None,
        "act_history": [],
        "anchor_history": [],
    }


def story_progress_from_state(state_json: dict[str, Any] | None) -> dict[str, Any]:
    state = _record(state_json)
    progress = _record(state.get("story_progress"))
    if not progress:
        progress = _record(_record(state.get("v2")).get("story_progress"))
    return {
        "current_act": _text(progress.get("current_act") or progress.get("act")),
        "completed_acts": _unique(_strings(progress.get("completed_acts"))),
        "completed_anchors": _unique(_strings(progress.get("completed_anchors"))),
        "ready_for_next_act": _bool(progress.get("ready_for_next_act"), False),
        "last_advance_turn": progress.get("last_advance_turn"),
        "last_advance_reason": _text(progress.get("last_advance_reason")),
        "last_anchor_update_turn": progress.get("last_anchor_update_turn"),
    }


def completion_anchor_ids_for_act(
    config: GameConfig | None,
    act_id: str,
    *,
    required_only: bool = True,
) -> list[str]:
    story = story_settings_from_config(config)
    act = _current_act(story, act_id)
    ids: list[str] = []
    for anchor in _records(act.get("completion_anchors")):
        if required_only and not _bool(anchor.get("required"), True):
            continue
        anchor_id = _text(anchor.get("id"))
        if anchor_id and anchor_id not in ids:
            ids.append(anchor_id)
    return ids


def transition_target_for_act(config: GameConfig | None, act_id: str) -> str:
    story = story_settings_from_config(config)
    act = _current_act(story, act_id)
    transition = _record(act.get("transition_to_next_act"))
    target = _text(
        transition.get("target_act")
        or transition.get("to_act")
        or transition.get("act_id")
        or transition.get("id")
    )
    if target:
        return target
    return _act_identity(_next_act(story, act))


def story_settings_search_fragments(
    config: GameConfig | None,
    state_json: dict[str, Any] | None = None,
) -> list[str]:
    runtime = build_runtime_story(config, state_json)
    fragments: list[str] = []
    for section in (
        "game_profile",
        "hard_rules",
        "story_core",
        "worldview",
        "current_act",
        "next_act",
        "home_base",
    ):
        fragments.extend(_flatten_text(runtime.get(section))[:20])
    for item in _records(runtime.get("main_quest_path"))[:6]:
        fragments.extend(_flatten_text(item)[:12])
    for item in _records(runtime.get("core_characters"))[:8]:
        fragments.extend(_flatten_text(item)[:10])
    return _unique([fragment for fragment in fragments if fragment])


def validate_story_settings(settings: Any) -> dict[str, Any]:
    story = normalize_story_settings(settings)
    if story.get("format_version") != STORY_SETTINGS_FORMAT_VERSION:
        raise ValueError("story_settings.format_version 必须是 rpgforge.story.v2。")
    character_names: set[str] = set()
    for index, character in enumerate(_records(story.get("core_characters"))):
        name = _text(character.get("name"))
        if not name:
            raise ValueError(f"core_characters[{index}].name 不能为空。")
        if name in character_names:
            raise ValueError(f"core_characters[{index}].name 重复：{name}")
        character_names.add(name)
    act_ids: set[str] = set()
    anchor_ids: set[str] = set()
    for index, act in enumerate(_records(story.get("act_plan"))):
        act_id = _act_identity(act)
        if not act_id:
            raise ValueError(f"act_plan[{index}].id 不能为空。")
        if act_id in act_ids:
            raise ValueError(f"act_plan[{index}].id 重复：{act_id}")
        act_ids.add(act_id)
        for anchor_index, anchor in enumerate(_records(act.get("completion_anchors"))):
            anchor_id = _text(anchor.get("id"))
            if not anchor_id:
                raise ValueError(
                    f"act_plan[{index}].completion_anchors[{anchor_index}].id "
                    "不能为空。"
                )
            if anchor_id in anchor_ids:
                raise ValueError(f"完成锚点 id 重复：{anchor_id}")
            anchor_ids.add(anchor_id)
    return story


def _runtime_current_act_id(story: dict[str, Any], progress: dict[str, Any]) -> str:
    state_act = _text(progress.get("current_act"))
    if state_act and _act_exists(story, state_act):
        return state_act
    configured = _text(_record(story.get("story_core")).get("current_act"))
    if configured and _act_exists(story, configured):
        return configured
    first = _record(_list(story.get("act_plan"))[0] if story.get("act_plan") else {})
    return _act_identity(first) or configured or state_act or "act_1"


def _current_act(story: dict[str, Any], act_id: str) -> dict[str, Any]:
    acts = _records(story.get("act_plan"))
    for act in acts:
        if act_id in _act_identifiers(act):
            return act
    return acts[0] if acts else {}


def _next_act(story: dict[str, Any], current_act: dict[str, Any]) -> dict[str, Any]:
    acts = _records(story.get("act_plan"))
    if not current_act:
        return {}
    current_ids = set(_act_identifiers(current_act))
    for index, act in enumerate(acts):
        if current_ids.intersection(_act_identifiers(act)):
            return _record(acts[index + 1]) if index + 1 < len(acts) else {}
    return {}


def _act_exists(story: dict[str, Any], act_id: str) -> bool:
    return any(act_id in _act_identifiers(act) for act in _records(story.get("act_plan")))


def _act_identity(act: dict[str, Any]) -> str:
    identifiers = _act_identifiers(act)
    return identifiers[0] if identifiers else ""


def _act_identifiers(act: dict[str, Any]) -> list[str]:
    identifiers = [
        _text(act.get("id")),
        _text(act.get("key")),
        _text(act.get("name")),
        _text(act.get("title")),
    ]
    return [identifier for identifier in identifiers if identifier]


def _act(item: dict[str, Any], index: int) -> dict[str, Any]:
    act_id = _text(item.get("id") or item.get("key")) or f"act_{index + 1}"
    base = {
        "id": act_id,
        "title": _text(item.get("title") or item.get("name")) or f"Act {index + 1}",
        "objective": _text(item.get("objective") or item.get("goal")),
        "dramatic_question": _text(item.get("dramatic_question")),
        "must_hit_beats": _list(item.get("must_hit_beats")),
        "allowed_reveals": _list(item.get("allowed_reveals")),
        "forbidden_reveals": _list(item.get("forbidden_reveals")),
        "completion_anchors": [
            _anchor(anchor, act_id, anchor_index)
            for anchor_index, anchor in enumerate(_records(item.get("completion_anchors")))
        ],
        "transition_to_next_act": _record(item.get("transition_to_next_act")),
    }
    return _object_with_extra(base, item)


def _anchor(item: dict[str, Any], act_id: str, index: int) -> dict[str, Any]:
    return _object_with_extra(
        {
            "id": _text(item.get("id")) or f"{act_id}_anchor_{index + 1}",
            "title": _text(item.get("title") or item.get("name")) or "未命名锚点",
            "required": _bool(item.get("required"), True),
            "description": _text(item.get("description") or item.get("goal")),
            "completion_signal": _text(item.get("completion_signal") or item.get("signal")),
        },
        item,
    )


def _quest(item: dict[str, Any], index: int) -> dict[str, Any]:
    return _object_with_extra(
        {
            "id": _text(item.get("id")) or f"main_quest_{index + 1}",
            "title": _text(item.get("title") or item.get("name")) or "未命名主线节点",
            "act_id": _text(item.get("act_id") or item.get("act")),
            "objective": _text(item.get("objective") or item.get("goal")),
            "player_visible": _text(item.get("player_visible")),
            "completion_signal": _text(item.get("completion_signal")),
            "optional": _bool(item.get("optional"), False),
        },
        item,
    )


def _material(item: dict[str, Any]) -> dict[str, Any]:
    return _object_with_extra(
        {
            "id": _text(item.get("id") or item.get("key")),
            "title": _text(item.get("title") or item.get("name")) or "未命名素材",
            "type": _text(item.get("type")) or "story_material",
            "keywords": _strings(item.get("keywords")),
            "triggers": _strings(item.get("triggers") or item.get("trigger_words")),
            "priority": _text(item.get("priority")) or "medium",
            "always_on": _bool(item.get("always_on"), False),
            "visibility": _text(item.get("visibility")) or "mixed",
            "public_info": _text(item.get("public_info")),
            "gm_secret": _text(item.get("gm_secret")),
            "content": _text(item.get("content") or item.get("description")),
            "usage": _text(item.get("usage") or item.get("usage_note")),
            "enabled": _bool(item.get("enabled"), True),
        },
        item,
    )


def _action_style(item: dict[str, Any]) -> dict[str, Any]:
    return _object_with_extra(
        {
            "id": _text(item.get("id") or item.get("key")),
            "name": _text(item.get("name") or item.get("title")) or "默认行动风格",
            "triggers": _strings(item.get("triggers") or item.get("trigger_words")),
            "rule": _text(item.get("rule") or item.get("instruction")),
            "priority": _text(item.get("priority")) or "medium",
            "enabled": _bool(item.get("enabled"), True),
        },
        item,
    )


def _character(item: dict[str, Any]) -> dict[str, Any]:
    return _object_with_extra(
        {
            "id": _text(item.get("id") or item.get("key")),
            "name": _text(item.get("name")) or "未命名角色",
            "aliases": _strings(item.get("aliases")),
            "role": _text(item.get("role")) or "npc",
            "identity": _text(item.get("identity")),
            "description": _text(item.get("description")),
            "appearance": _text(item.get("appearance")),
            "dramatic_function": _text(item.get("dramatic_function")),
            "desire": _text(item.get("desire")),
            "fear": _text(item.get("fear")),
            "leverage": _text(item.get("leverage")),
            "relationship_arc": _text(item.get("relationship_arc")),
            "public_limit": _text(item.get("public_limit")),
            "portrait_prompt": _text(item.get("portrait_prompt")),
            "visibility": _text(item.get("visibility")) or "visible",
        },
        item,
    )


def _named_record(item: dict[str, Any], fallback_name: str) -> dict[str, Any]:
    return _object_with_extra(
        {
            "id": _text(item.get("id") or item.get("key")),
            "name": _text(item.get("name") or item.get("title")) or fallback_name,
            "rule": _text(item.get("rule") or item.get("description")),
            "visibility": _text(item.get("visibility")) or "mixed",
        },
        item,
    )


def _material_score(
    material: dict[str, Any],
    query_terms: set[str],
    query_lower: str,
) -> tuple[float, list[str]]:
    score = 0.0
    matched: set[str] = set()
    title = _text(material.get("title")).lower()
    if title and title in query_lower:
        score += 4.0
        matched.add(title)
    for term in _strings(material.get("triggers")):
        lower = term.lower()
        if lower and lower in query_lower:
            score += 4.0
            matched.add(term)
    for term in _strings(material.get("keywords")):
        lower = term.lower()
        if lower and (lower in query_lower or lower in query_terms):
            score += 3.0
            matched.add(term)
    material_terms = set(_meaningful_terms("\n".join(_flatten_text(material))))
    overlap = sorted(query_terms & material_terms)
    if overlap:
        score += min(3.0, len(overlap) * 0.4)
        matched.update(overlap[:8])
    score += _priority_weight(material.get("priority")) * 0.2
    return score, sorted(matched)


def _meaningful_terms(text: str) -> list[str]:
    return [
        term
        for term in extract_terms(text)
        if term and term not in {"剧情", "线索", "任务", "当前", "玩家", "行动", "世界"}
    ]


def _priority_weight(value: Any) -> int:
    return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(_text(value), 2)


def _object_with_extra(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    result = dict(extra)
    result.update(base)
    return _drop_empty(result)


def _drop_empty(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if value not in (None, "", [], {})
    }


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in _list(value) if isinstance(item, dict)]


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, "", {}):
        return []
    return [value]


def _strings(value: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in _list(value):
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return default


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is not None and not isinstance(value, (dict, list)):
        return str(value).strip()
    return ""


def _flatten_text(value: Any) -> list[str]:
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_flatten_text(item))
        return result
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_flatten_text(item))
        return result
    text = _text(value)
    return [text] if text else []
