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


class ModelOutputValidationError(RuntimeError):
    pass


StreamUpdateCallback = Callable[[str, str, str | None], Awaitable[None]]

FINALIZE_SECTION_RETRIES = 1
FINALIZE_SECTION_CONCURRENCY = 4


@dataclass(frozen=True)
class FinalizeSectionSpec:
    key: str
    label: str
    max_tokens: int


@dataclass
class FinalizeStreamBuffer:
    label: str
    reasoning: str = ""
    content: str = ""


FINALIZE_SECTION_SPECS: tuple[FinalizeSectionSpec, ...] = (
    FinalizeSectionSpec("characters", "角色档案", 3500),
    FinalizeSectionSpec("lore_entries", "世界书", 6500),
    FinalizeSectionSpec("modes", "模式注入", 3500),
    FinalizeSectionSpec("initial_state", "初始状态", 5500),
    FinalizeSectionSpec("rules", "系统规则", 3000),
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

        stream_order = [("outline", "导演总纲"), *[
            (spec.key, spec.label) for spec in FINALIZE_SECTION_SPECS
        ]]

        def rendered_reasoning() -> str:
            parts = [f"配置生成：{message}" for message in pipeline_reasoning]
            for key, label in stream_order:
                buffer = stream_buffers.get(key)
                if buffer and buffer.reasoning.strip():
                    parts.append(f"配置生成：{label}思考过程\n{buffer.reasoning}")
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

        await emit_progress("正在生成导演总纲。")
        outline, outline_model = await self._generate_finalize_outline(
            request,
            on_update=section_update_callback("outline", "导演总纲"),
        )
        model_used = outline_model
        await emit_progress("导演总纲完成，正在并行生成角色、世界书、模式、状态和系统规则。")

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

        await emit_progress("所有分块生成完成，正在合并校验。")
        payload = self._merge_finalize_payload(request, outline, sections)
        try:
            config = GeneratedGameConfig.model_validate(payload)
        except ValidationError as exc:
            raise ModelOutputValidationError(f"分块配置合并后结构无效：{exc}") from exc

        final_json = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, indent=2)
        await emit_progress(
            "完整配置已合并并通过结构校验。",
            content=final_json,
            model=model_used,
        )
        return GeneratorFinalizeResponse(config=config, model_used=model_used or "unknown")

    async def _generate_finalize_outline(
        self,
        request: GeneratorFinalizeRequest,
        on_update: StreamUpdateCallback | None = None,
    ) -> tuple[dict[str, Any], str]:
        messages = self._build_finalize_outline_messages(request)
        try:
            payload, model_used = await self._collect_streamed_json(
                task_type="generator_finalize_outline",
                messages=messages,
                max_tokens=5000,
                on_update=on_update,
            )
        except (ValueError, ModelOutputValidationError) as exc:
            raise ModelOutputValidationError(f"导演总纲不是完整合法 JSON：{exc}") from exc
        return dict(payload), model_used

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
                return self._extract_finalize_section_data(spec.key, payload), model_used
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
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "当前已确认需求："
                        f"{json.dumps(request.confirmed_requirements, ensure_ascii=False)}"
                    ),
                }
            )
        messages.extend(
            {"role": message.role, "content": message.content} for message in request.history[-12:]
        )
        messages.append({"role": "user", "content": request.user_input})
        return messages

    @staticmethod
    def _build_finalize_messages(request: GeneratorFinalizeRequest) -> list[dict[str, str]]:
        prompt = load_prompt_template("generate_game_config.md")
        user_payload = {
            "concept": request.concept,
            "confirmed_requirements": request.confirmed_requirements,
            "history": [message.model_dump() for message in request.history],
        }
        return [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "请根据以下资料生成 RPGForge 游戏配置 JSON：\n"
                    f"{json.dumps(user_payload, ensure_ascii=False)}"
                ),
            },
        ]

    @staticmethod
    def _build_finalize_outline_messages(request: GeneratorFinalizeRequest) -> list[dict[str, str]]:
        prompt = load_prompt_template("generate_config_outline.md")
        user_payload = {
            "concept": request.concept,
            "confirmed_requirements": request.confirmed_requirements,
            "history": [message.model_dump() for message in request.history],
        }
        return [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "请根据以下资料生成短总纲 JSON：\n"
                    f"{json.dumps(user_payload, ensure_ascii=False)}"
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
        section_payload = {
            "target_section": spec.key,
            "outline_json": outline,
            "source_request": {
                "concept": request.concept,
                "confirmed_requirements": request.confirmed_requirements,
                "history": [message.model_dump() for message in request.history[-8:]],
            },
        }
        return [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    f"target_section = {spec.key}\n"
                    "请只生成这个分块 JSON：\n"
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
    def _extract_finalize_section_data(section_key: str, payload: dict[str, Any]) -> Any:
        if section_key == "rules":
            data = payload.get("data", payload)
            if not isinstance(data, dict):
                raise ModelOutputValidationError("rules 分块必须是 JSON object。")
            return data

        data = payload.get(section_key, payload.get("data"))
        if section_key in {"characters", "lore_entries", "modes"}:
            if not isinstance(data, list):
                raise ModelOutputValidationError(f"{section_key} 分块必须是 JSON array。")
            return data
        if section_key == "initial_state":
            if not isinstance(data, dict):
                raise ModelOutputValidationError("initial_state 分块必须是 JSON object。")
            return data
        raise ModelOutputValidationError(f"未知分块：{section_key}")

    @staticmethod
    def _merge_finalize_payload(
        request: GeneratorFinalizeRequest,
        outline: dict[str, Any],
        sections: dict[str, Any],
    ) -> dict[str, Any]:
        title = _string(outline.get("title")) or "未命名游戏"
        description = _string(outline.get("description")) or request.concept[:120]
        worldview = _mapping(outline.get("worldview"))
        script_outline = _mapping(outline.get("script_outline"))
        script_outline.setdefault("title", title)
        script_outline.setdefault("acts", [])
        script_outline["campaign_contract"] = _campaign_contract(outline, script_outline)

        rules = _mapping(sections.get("rules"))
        characters = _list(sections.get("characters"))
        initial_state = _initial_state(
            title=title,
            description=description,
            initial_state=_mapping(sections.get("initial_state")),
            characters=characters,
        )

        generation_notes = _string(rules.get("generation_notes")) or _string(
            outline.get("generation_notes")
        )
        if not generation_notes:
            generation_notes = (
                "分块流水线生成：导演总纲、角色、世界书、模式、初始状态并行生成后合并。"
            )

        return {
            "title": title,
            "genre": _string(outline.get("genre")),
            "description": description,
            "system_prompt": _system_prompt(rules, outline),
            "worldview": worldview,
            "script_outline": script_outline,
            "generation_notes": generation_notes,
            "characters": _characters(characters, initial_state),
            "lore_entries": _lore_entries(
                _list(sections.get("lore_entries")),
                title=title,
                description=description,
            ),
            "modes": _modes(_list(sections.get("modes"))),
            "initial_state": initial_state,
            "voice_profiles": _list(rules.get("voice_profiles")),
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


def _campaign_contract(
    outline: dict[str, Any],
    script_outline: dict[str, Any],
) -> dict[str, Any]:
    contract = _mapping(script_outline.get("campaign_contract")) or _mapping(
        outline.get("campaign_contract")
    )
    canon_terms = _list(contract.get("canon_terms")) or _list(outline.get("canon_terms"))
    contract.setdefault("premise", _string(outline.get("description")) or "围绕玩家核心设定推进。")
    contract.setdefault("tone_do", [])
    contract.setdefault("tone_dont", [])
    contract.setdefault("act_plan", _list(script_outline.get("acts")))
    contract.setdefault("relationship_arcs", [])
    contract.setdefault("forbidden_drift", _list(outline.get("forbidden_drift")))
    contract["canon_terms"] = canon_terms
    contract.setdefault("pacing_rules", [])
    contract.setdefault("current_act", "act_1")
    return contract


def _system_prompt(rules: dict[str, Any], outline: dict[str, Any]) -> str:
    prompt = _string(rules.get("system_prompt")) or _string(outline.get("system_prompt"))
    if prompt:
        return prompt
    return (
        "你是本局 GM。每回合只输出玩家可见剧情，保持隐藏信息与玩家可见信息分离，"
        "并给出 A/B/C/D 四个具体行动选项。叙事必须遵守 campaign_contract，"
        "不要提前泄露 forbidden_reveals 或 gm_secret。"
        "输出格式必须遵守 RPGForge 剧情 Markdown 契约。"
    )


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
    initial_state["variables"].setdefault("source_description", description)
    initial_state["known_facts"] = _list(initial_state.get("known_facts"))
    initial_state["hidden_facts"] = _list(initial_state.get("hidden_facts"))
    initial_state["open_threads"] = _list(initial_state.get("open_threads"))
    return initial_state


def _characters(
    characters: list[Any],
    initial_state: dict[str, Any],
) -> list[Any]:
    character_profiles = [character for character in characters if isinstance(character, dict)]
    if character_profiles:
        return character_profiles
    protagonist = _mapping(initial_state.get("protagonist"))
    name = _string(protagonist.get("name")) or "主角"
    return [
        {
            "name": name,
            "aliases": [],
            "role": "protagonist",
            "identity": _string(protagonist.get("identity")),
            "description": _string(protagonist.get("identity")),
            "appearance": _string(protagonist.get("appearance")),
            "portrait_prompt": _string(protagonist.get("portrait_prompt")),
            "visibility": "visible",
        }
    ]


def _lore_entries(
    lore_entries: list[Any],
    *,
    title: str,
    description: str,
) -> list[Any]:
    entries = [entry for entry in lore_entries if isinstance(entry, dict)]
    if entries:
        return entries
    return [
        {
            "title": title,
            "type": "core_rule",
            "keywords": [title],
            "trigger_words": [],
            "priority": "critical",
            "always_on": True,
            "visibility": "public",
            "public_info": description,
            "gm_secret": "",
            "content": description or f"{title} 的核心设定待在游玩中展开。",
            "usage_note": "作为全局设定锚点持续注入。",
        }
    ]


def _modes(modes: list[Any]) -> list[Any]:
    mode_profiles = [mode for mode in modes if isinstance(mode, dict)]
    if mode_profiles:
        return mode_profiles
    return [
        {
            "name": "主线模式",
            "triggers": ["主线", "目标", "推进"],
            "injection": "围绕当前幕目标推进，避免跳过关键铺垫。",
            "priority": "high",
            "enabled": True,
        },
        {
            "name": "调查模式",
            "triggers": ["调查", "搜索", "线索"],
            "injection": "给出可验证线索，不直接泄露隐藏真相。",
            "priority": "high",
            "enabled": True,
        },
        {
            "name": "社交模式",
            "triggers": ["交谈", "询问", "关系"],
            "injection": "通过动机、态度和关系变化推动互动。",
            "priority": "medium",
            "enabled": True,
        },
        {
            "name": "探索模式",
            "triggers": ["移动", "探索", "观察"],
            "injection": "强调环境细节、风险提示和可选择路径。",
            "priority": "medium",
            "enabled": True,
        },
    ]
