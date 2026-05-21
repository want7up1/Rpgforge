import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.schemas.generator import (
    GeneratedGameConfig,
    GeneratorChatRequest,
    GeneratorChatResponse,
    GeneratorFinalizeRequest,
    GeneratorFinalizeResponse,
)
from app.services.json_utils import parse_json_object
from app.services.model_router import ModelRouter
from app.services.prompt_loader import load_prompt_template
from app.services.story_settings import (
    STORY_SETTINGS_FORMAT_VERSION,
    normalize_story_settings,
    validate_story_settings,
)


class ModelOutputValidationError(RuntimeError):
    pass


StreamUpdateCallback = Callable[[str, str, str | None], Awaitable[None]]

FINALIZE_OUTLINE_RETRIES = 1
FINALIZE_OUTLINE_MAX_TOKENS = 12000
FINALIZE_SECTION_RETRIES = 1
FINALIZE_SECTION_CONCURRENCY = 4


@dataclass(frozen=True)
class FinalizeSectionSpec:
    key: str
    label: str
    max_tokens: int
    kind: str


@dataclass
class FinalizeStreamBuffer:
    label: str
    reasoning: str = ""
    content: str = ""


FINALIZE_SECTION_SPECS: tuple[FinalizeSectionSpec, ...] = (
    FinalizeSectionSpec("core_characters", "核心人物", 4500, "list"),
    FinalizeSectionSpec("act_plan", "五幕主线", 6000, "list"),
    FinalizeSectionSpec("main_quest_path", "主线轨迹", 3500, "list"),
    FinalizeSectionSpec("core_mechanics", "核心机制", 3500, "list"),
    FinalizeSectionSpec("action_style_rules", "行动风格规则", 3500, "list"),
    FinalizeSectionSpec("story_material_library", "剧本素材库", 6500, "list"),
    FinalizeSectionSpec("home_base", "破晓基地", 3000, "object"),
    FinalizeSectionSpec("hard_rules", "强制规则", 3000, "object"),
    FinalizeSectionSpec("initial_state", "初始状态", 5500, "object"),
)


class GameGeneratorService:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    async def interview(self, request: GeneratorChatRequest) -> GeneratorChatResponse:
        prompt = load_prompt_template("generator_interview.md")
        messages = self._build_interview_messages(prompt, request)
        result = await self.router.use_pro(
            "generator_interview",
            messages,
            json_mode=True,
            max_tokens=4096,
            reasoning_effort="high",
        )
        payload = parse_json_object(result.content)
        payload["confirmed_requirements"] = _normalize_confirmed_requirements(
            _mapping(payload.get("confirmed_requirements")),
            request.user_input,
        )
        payload["model_used"] = result.model
        try:
            return GeneratorChatResponse.model_validate(payload)
        except ValidationError as exc:
            raise ModelOutputValidationError(str(exc)) from exc

    async def interview_stream(
        self,
        request: GeneratorChatRequest,
        on_update: StreamUpdateCallback | None = None,
    ) -> GeneratorChatResponse:
        prompt = load_prompt_template("generator_interview.md")
        messages = self._build_interview_messages(prompt, request)
        payload, model_used = await self._collect_streamed_json(
            task_type="generator_interview",
            messages=messages,
            max_tokens=4096,
            on_update=on_update,
        )
        payload["confirmed_requirements"] = _normalize_confirmed_requirements(
            _mapping(payload.get("confirmed_requirements")),
            request.user_input,
        )
        payload["model_used"] = model_used
        try:
            return GeneratorChatResponse.model_validate(payload)
        except ValidationError as exc:
            raise ModelOutputValidationError(str(exc)) from exc

    async def finalize(self, request: GeneratorFinalizeRequest) -> GeneratorFinalizeResponse:
        return await self.finalize_stream(request)

    async def finalize_stream(
        self,
        request: GeneratorFinalizeRequest,
        on_update: StreamUpdateCallback | None = None,
    ) -> GeneratorFinalizeResponse:
        pipeline_reasoning: list[str] = []
        stream_buffers: dict[str, FinalizeStreamBuffer] = {}
        final_content_buffer = ""
        model_used: str | None = None
        update_lock = asyncio.Lock()

        stream_order = [
            ("outline", "导演总纲"),
            *((spec.key, spec.label) for spec in FINALIZE_SECTION_SPECS),
        ]

        def rendered_reasoning() -> str:
            parts = [f"剧本生成：{message}" for message in pipeline_reasoning]
            for key, label in stream_order:
                buffer = stream_buffers.get(key)
                if buffer and buffer.reasoning.strip():
                    parts.append(f"剧本生成：{label}思考过程\n{buffer.reasoning}")
            return "\n\n".join(parts)

        def rendered_content() -> str:
            if final_content_buffer:
                return final_content_buffer
            parts: list[str] = []
            for key, label in stream_order:
                buffer = stream_buffers.get(key)
                if buffer and buffer.content.strip():
                    parts.append(f"## {label}\n{buffer.content}")
            return "\n\n".join(parts)

        async def publish_update() -> None:
            if on_update:
                await on_update(rendered_reasoning(), rendered_content(), model_used)

        def section_update_callback(key: str, label: str) -> StreamUpdateCallback:
            async def update(reasoning: str, content: str, model: str | None) -> None:
                nonlocal model_used
                async with update_lock:
                    if model:
                        model_used = model
                    stream_buffers[key] = FinalizeStreamBuffer(
                        label=label,
                        reasoning=reasoning,
                        content=content,
                    )
                    await publish_update()

            return update

        async def emit_progress(
            message: str,
            *,
            content: str | None = None,
            model: str | None = None,
        ) -> None:
            nonlocal final_content_buffer, model_used
            async with update_lock:
                if model:
                    model_used = model
                if content is not None:
                    final_content_buffer = content
                pipeline_reasoning.append(message)
                await publish_update()

        await emit_progress("正在生成 story_settings v2 导演总纲。")
        outline, outline_model = await self._generate_finalize_outline(
            request,
            on_update=section_update_callback("outline", "导演总纲"),
        )
        model_used = outline_model
        await emit_progress(
            "导演总纲完成，正在并行生成核心人物、五幕主线、机制、行动风格、素材库、基地、强制规则和初始状态。"
        )

        semaphore = asyncio.Semaphore(FINALIZE_SECTION_CONCURRENCY)

        async def run_section(spec: FinalizeSectionSpec) -> tuple[str, Any, str]:
            async with semaphore:
                await emit_progress(f"{spec.label}开始生成。")
                data, section_model = await self._generate_finalize_section(
                    request=request,
                    outline=outline,
                    spec=spec,
                    on_progress=emit_progress,
                    on_update=section_update_callback(spec.key, spec.label),
                )
                await emit_progress(f"{spec.label}生成完成。", model=section_model)
                return spec.key, data, section_model

        section_results = await asyncio.gather(
            *(run_section(spec) for spec in FINALIZE_SECTION_SPECS)
        )
        sections = {key: data for key, data, _model in section_results}
        section_models = [section_model for _key, _data, section_model in section_results]
        model_used = model_used or next((model for model in section_models if model), None)

        await emit_progress("所有分区生成完成，正在合并校验 story_settings v2。")
        payload = self._merge_finalize_payload(request, outline, sections)
        try:
            config = GeneratedGameConfig.model_validate(payload)
        except ValidationError as exc:
            raise ModelOutputValidationError(f"剧本配置合并后结构无效：{exc}") from exc

        final_json = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2)
        await emit_progress(
            "完整 story_settings v2 已合并并通过结构校验。",
            content=final_json,
            model=model_used,
        )
        return GeneratorFinalizeResponse(config=config, model_used=model_used or "unknown")

    async def _generate_finalize_outline(
        self,
        request: GeneratorFinalizeRequest,
        on_update: StreamUpdateCallback | None = None,
    ) -> tuple[dict[str, Any], str]:
        base_messages = self._build_finalize_outline_messages(request)
        last_error: Exception | None = None
        for attempt in range(FINALIZE_OUTLINE_RETRIES + 1):
            messages = (
                base_messages
                if attempt == 0
                else self._build_finalize_outline_retry_messages(base_messages)
            )
            try:
                payload, model_used = await self._collect_streamed_json(
                    task_type="generator_finalize_outline",
                    messages=messages,
                    max_tokens=FINALIZE_OUTLINE_MAX_TOKENS,
                    on_update=on_update,
                )
                return dict(payload), model_used
            except (ValueError, ModelOutputValidationError) as exc:
                last_error = exc
                if attempt < FINALIZE_OUTLINE_RETRIES:
                    continue
                break

        raise ModelOutputValidationError(f"导演总纲不是完整合法 JSON：{last_error}") from last_error

    async def _generate_finalize_section(
        self,
        *,
        request: GeneratorFinalizeRequest,
        outline: dict[str, Any],
        spec: FinalizeSectionSpec,
        on_progress: Callable[[str], Awaitable[None]],
        on_update: StreamUpdateCallback | None = None,
    ) -> tuple[Any, str]:
        last_error: Exception | None = None
        for attempt in range(FINALIZE_SECTION_RETRIES + 1):
            messages = self._build_finalize_section_messages(request, outline, spec)
            try:
                payload, model_used = await self._collect_streamed_json(
                    task_type=f"generator_finalize_{spec.key}",
                    messages=messages,
                    max_tokens=spec.max_tokens,
                    on_update=on_update,
                )
                return self._extract_finalize_section_data(spec, payload), model_used
            except (ValueError, ModelOutputValidationError, ValidationError) as exc:
                last_error = exc
                if attempt < FINALIZE_SECTION_RETRIES:
                    await on_progress(f"{spec.label}输出无效，正在局部重试。")
                    continue
                break

        raise ModelOutputValidationError(f"{spec.label}生成失败：{last_error}") from last_error

    @staticmethod
    def _build_interview_messages(
        prompt: str,
        request: GeneratorChatRequest,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": prompt}]
        if request.confirmed_requirements:
            normalized_requirements = _normalize_confirmed_requirements(
                request.confirmed_requirements,
                request.user_input,
            )
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "当前已确认需求："
                        f"{json.dumps(normalized_requirements, ensure_ascii=False)}"
                    ),
                }
            )
        messages.extend(
            {"role": message.role, "content": message.content} for message in request.history[-12:]
        )
        messages.append({"role": "user", "content": request.user_input})
        return messages

    @staticmethod
    def _build_finalize_outline_messages(request: GeneratorFinalizeRequest) -> list[dict[str, str]]:
        prompt = load_prompt_template("generate_config_outline.md")
        confirmed_requirements = _normalize_confirmed_requirements(
            request.confirmed_requirements,
            request.concept,
        )
        user_payload = {
            "concept": request.concept,
            "confirmed_requirements": confirmed_requirements,
            "history": [message.model_dump() for message in request.history],
        }
        return [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "请根据以下资料生成 story_settings v2 导演总纲 JSON：\n"
                    f"{json.dumps(user_payload, ensure_ascii=False)}"
                ),
            },
        ]

    @staticmethod
    def _build_finalize_outline_retry_messages(
        messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        return [
            *messages,
            {
                "role": "user",
                "content": (
                    "上一次导演总纲输出不是完整合法 JSON，可能在长字符串或嵌套结构中被截断。"
                    "请重新生成完整 JSON object，保持原有剧情丰富度、字段完整度和设定细节，"
                    "不要输出 Markdown，不要解释。必须保留 game_profile、worldview、story_core、"
                    "act_plan_outline、main_quest_path_outline、material_plan、"
                    "hard_rules 和 generation_parameters。"
                ),
            },
        ]

    @staticmethod
    def _build_finalize_section_messages(
        request: GeneratorFinalizeRequest,
        outline: dict[str, Any],
        spec: FinalizeSectionSpec,
    ) -> list[dict[str, str]]:
        prompt = load_prompt_template("generate_config_section.md")
        confirmed_requirements = _normalize_confirmed_requirements(
            request.confirmed_requirements,
            request.concept,
        )
        section_payload = {
            "target_section": spec.key,
            "target_kind": spec.kind,
            "outline_json": outline,
            "source_request": {
                "concept": request.concept,
                "confirmed_requirements": confirmed_requirements,
                "history": [message.model_dump() for message in request.history[-8:]],
            },
        }
        return [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    f"target_section = {spec.key}\n"
                    "请只生成这个 story_settings v2 分区 JSON：\n"
                    f"{json.dumps(section_payload, ensure_ascii=False)}"
                ),
            },
        ]

    async def _collect_streamed_json(
        self,
        *,
        task_type: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        on_update: StreamUpdateCallback | None,
    ) -> tuple[dict[str, object], str]:
        reasoning_parts: list[str] = []
        content_parts: list[str] = []
        model_used: str | None = None

        async for chunk in self.router.use_pro_stream(
            task_type,
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
            raise ModelOutputValidationError("DeepSeek API 流式返回了空内容。")
        try:
            return parse_json_object(content), model_used or "unknown"
        except ValueError as exc:
            raise ModelOutputValidationError(
                f"{task_type} 输出不是完整合法 JSON：{exc}"
            ) from exc

    @staticmethod
    def _extract_finalize_section_data(
        spec: FinalizeSectionSpec,
        payload: dict[str, Any],
    ) -> Any:
        data = payload.get(spec.key, payload.get("data", payload))
        if spec.key == "initial_state":
            data = payload.get("initial_state", data)
        if spec.kind == "list":
            if not isinstance(data, list):
                raise ModelOutputValidationError(f"{spec.key} 分区必须是 JSON array。")
            return data
        if not isinstance(data, dict):
            raise ModelOutputValidationError(f"{spec.key} 分区必须是 JSON object。")
        return data

    @staticmethod
    def _merge_finalize_payload(
        request: GeneratorFinalizeRequest,
        outline: dict[str, Any],
        sections: dict[str, Any],
    ) -> dict[str, Any]:
        profile = _mapping(outline.get("game_profile"))
        title = _string(profile.get("title")) or _string(outline.get("title")) or "未命名游戏"
        genre = _string(profile.get("genre")) or _string(outline.get("genre"))
        description = (
            _string(profile.get("description"))
            or _string(outline.get("description"))
            or request.concept[:120]
        )
        story_settings = _ensure_story_defaults(
            normalize_story_settings(
                {
                    "format_version": STORY_SETTINGS_FORMAT_VERSION,
                    "game_profile": {
                        **profile,
                        "title": title,
                        "genre": genre,
                        "description": description,
                    },
                    "worldview": _mapping(outline.get("worldview")),
                    "story_core": _merge_story_core(request, outline),
                    "core_characters": _list(sections.get("core_characters")),
                    "act_plan": _list(sections.get("act_plan"))
                    or _list(outline.get("act_plan_outline")),
                    "main_quest_path": _list(sections.get("main_quest_path"))
                    or _list(outline.get("main_quest_path_outline")),
                    "core_mechanics": _list(sections.get("core_mechanics"))
                    or _list(outline.get("core_mechanics_outline")),
                    "action_style_rules": _list(sections.get("action_style_rules")),
                    "story_material_library": _list(sections.get("story_material_library")),
                    "home_base": _mapping(sections.get("home_base"))
                    or _mapping(outline.get("home_base")),
                    "hard_rules": _merge_hard_rules(outline, sections),
                    "generation_parameters": _mapping(outline.get("generation_parameters")),
                }
            )
        )
        story_settings = validate_story_settings(story_settings)
        initial_state = _initial_state(
            title=title,
            description=description,
            initial_state=_mapping(sections.get("initial_state")),
            characters=_list(story_settings.get("core_characters")),
        )
        return {
            "title": title,
            "genre": genre,
            "description": description,
            "story_settings": story_settings,
            "initial_state": initial_state,
            "voice_profiles": [],
        }


def _ensure_story_defaults(story_settings: dict[str, Any]) -> dict[str, Any]:
    title = _string(_mapping(story_settings.get("game_profile")).get("title")) or "未命名游戏"
    description = _string(
        _mapping(story_settings.get("game_profile")).get("description")
    )
    if not _list(story_settings.get("story_material_library")):
        story_settings["story_material_library"] = [
            {
                "id": "core_setting",
                "title": f"{title} 核心设定",
                "type": "core_rule",
                "keywords": [title],
                "triggers": [],
                "priority": "critical",
                "always_on": True,
                "visibility": "public",
                "public_info": description,
                "content": description or f"{title} 的核心设定。",
                "usage": "作为长期设定锚点持续注入。",
                "enabled": True,
            }
        ]
    if not _list(story_settings.get("action_style_rules")):
        story_settings["action_style_rules"] = [
            {
                "id": "main_story",
                "name": "主线推进",
                "triggers": ["主线", "目标", "推进"],
                "rule": "围绕当前幕目标推进，不跳过必要铺垫，不强迫玩家立刻离开当前场景。",
                "priority": "high",
                "enabled": True,
            },
            {
                "id": "investigation",
                "name": "调查取证",
                "triggers": ["调查", "搜索", "线索"],
                "rule": "给出可验证线索和代价，不直接泄露隐藏真相。",
                "priority": "high",
                "enabled": True,
            },
        ]
    return story_settings


def _merge_story_core(
    request: GeneratorFinalizeRequest,
    outline: dict[str, Any],
) -> dict[str, Any]:
    requirements = _normalize_confirmed_requirements(
        request.confirmed_requirements,
        request.concept,
    )
    core = dict(_mapping(outline.get("story_core")))
    core.setdefault("premise", requirements["core_premise"] or request.concept[:160])
    core.setdefault("core_fantasy", requirements["core_premise"])
    core.setdefault("central_mystery", _string(outline.get("central_mystery")))
    core.setdefault("main_goal", _string(outline.get("main_goal")) or core.get("premise", ""))
    core.setdefault("current_act", "act_1")
    core["must_preserve"] = _unique_strings(
        [*_value_strings(core.get("must_preserve")), *_value_strings(requirements["must_include"])]
    )
    must_not = _unique_strings(
        [
            *_value_strings(core.get("must_not_become")),
            *_value_strings(requirements["forbidden_content"]),
        ]
    )
    core["must_not_become"] = must_not
    core["forbidden_drift"] = _unique_strings(
        [*_value_strings(core.get("forbidden_drift")), *_value_strings(must_not)]
    )
    core["canon_terms"] = _unique_strings(
        [
            *_value_strings(core.get("canon_terms")),
            *_value_strings(outline.get("canon_terms")),
            *_value_strings(requirements["must_include"]),
        ]
    )
    return core


def _merge_hard_rules(
    outline: dict[str, Any],
    sections: dict[str, Any],
) -> dict[str, Any]:
    outline_rules = _mapping(outline.get("hard_rules"))
    section_rules = _mapping(sections.get("hard_rules"))
    return {
        **outline_rules,
        **section_rules,
        "must_follow": _unique_strings(
            [
                *_value_strings(outline_rules.get("must_follow")),
                *_value_strings(section_rules.get("must_follow")),
            ]
        ),
        "must_not": _unique_strings(
            [
                *_value_strings(outline_rules.get("must_not")),
                *_value_strings(section_rules.get("must_not")),
            ]
        ),
        "reveal_rules": _unique_strings(
            [
                *_value_strings(outline_rules.get("reveal_rules")),
                *_value_strings(section_rules.get("reveal_rules")),
            ]
        ),
        "continuity_rules": _unique_strings(
            [
                *_value_strings(outline_rules.get("continuity_rules")),
                *_value_strings(section_rules.get("continuity_rules")),
            ]
        ),
    }


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _join_text(values: list[Any]) -> str:
    return "；".join(_value_strings(values))


def _value_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return _unique_strings(text for item in value for text in _value_strings(item))
    if isinstance(value, dict):
        return _unique_strings(text for item in value.values() for text in _value_strings(item))
    text = str(value).strip()
    return [text] if text else []


def _unique_strings(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _normalize_confirmed_requirements(
    requirements: dict[str, Any],
    raw_user_input: str = "",
) -> dict[str, Any]:
    story_background = _string(requirements.get("story_background"))
    if not story_background:
        story_background = _join_text(
            [
                requirements.get("genre"),
                requirements.get("world_style"),
                requirements.get("setting"),
                requirements.get("background"),
            ]
        )

    core_premise = _string(requirements.get("core_premise"))
    if not core_premise:
        core_premise = _join_text(
            [
                requirements.get("player_fantasy"),
                requirements.get("protagonist_identity"),
                requirements.get("core_gameplay"),
                requirements.get("main_goal"),
            ]
        )

    must_include = _unique_strings(
        [
            *_value_strings(requirements.get("must_include")),
            *_value_strings(requirements.get("must_hit_beats")),
            *_value_strings(requirements.get("relationship_focus")),
        ]
    )
    forbidden_content = _unique_strings(
        [
            *_value_strings(requirements.get("forbidden_content")),
            *_value_strings(requirements.get("forbidden_elements")),
            *_value_strings(requirements.get("forbidden_drift")),
        ]
    )
    playstyle_preferences = _unique_strings(
        [
            *_value_strings(requirements.get("playstyle_preferences")),
            *_value_strings(requirements.get("rule_complexity")),
            *_value_strings(requirements.get("failure_cost")),
            *_value_strings(requirements.get("core_gameplay")),
        ]
    )
    tone_preferences = _unique_strings(
        [
            *_value_strings(requirements.get("tone_preferences")),
            *_value_strings(requirements.get("world_style")),
            *_value_strings(requirements.get("pacing_preference")),
        ]
    )
    raw_input = _string(requirements.get("raw_user_input")) or raw_user_input

    return {
        "story_background": story_background,
        "core_premise": core_premise,
        "must_include": must_include,
        "forbidden_content": forbidden_content,
        "playstyle_preferences": playstyle_preferences,
        "tone_preferences": tone_preferences,
        "raw_user_input": raw_input,
    }


def _initial_state(
    *,
    title: str,
    description: str,
    initial_state: dict[str, Any],
    characters: list[Any],
) -> dict[str, Any]:
    protagonist = _mapping(initial_state.get("protagonist"))
    protagonist_character = next(
        (
            character
            for character in characters
            if isinstance(character, dict) and character.get("role") == "protagonist"
        ),
        None,
    )
    if isinstance(protagonist_character, dict):
        protagonist.setdefault("name", protagonist_character.get("name") or "")
        protagonist.setdefault("identity", protagonist_character.get("identity") or "")
        protagonist.setdefault("appearance", protagonist_character.get("appearance") or "")
        protagonist.setdefault(
            "portrait_prompt",
            protagonist_character.get("portrait_prompt") or "",
        )

    initial_state["current_turn"] = _int(initial_state.get("current_turn"), 0)
    initial_state["time"] = _mapping(initial_state.get("time"))
    initial_state["location"] = _mapping(initial_state.get("location"))
    initial_state["protagonist"] = protagonist
    progression = _mapping(initial_state.get("progression"))
    progression.setdefault("level", 1)
    progression.setdefault("xp", 0)
    progression.setdefault("next_level_xp", 100)
    progression.setdefault("total_xp", 0)
    progression.setdefault("xp_log", [])
    initial_state["progression"] = progression
    initial_state["skills"] = _list(initial_state.get("skills"))
    initial_state["abilities"] = _list(initial_state.get("abilities"))
    initial_state["conditions"] = _list(initial_state.get("conditions"))
    initial_state["relationships"] = _list(initial_state.get("relationships"))
    initial_state["inventory"] = _list(initial_state.get("inventory"))
    initial_state["quests"] = _list(initial_state.get("quests"))
    initial_state["npcs"] = _list(initial_state.get("npcs"))
    initial_state["factions"] = _list(initial_state.get("factions"))
    initial_state["variables"] = _mapping(initial_state.get("variables"))
    initial_state["variables"].setdefault("source_title", title)
    initial_state["variables"].setdefault("source_description", description or "")
    initial_state["known_facts"] = _list(initial_state.get("known_facts"))
    initial_state["hidden_facts"] = _list(initial_state.get("hidden_facts"))
    initial_state["open_threads"] = _list(initial_state.get("open_threads"))
    return initial_state
