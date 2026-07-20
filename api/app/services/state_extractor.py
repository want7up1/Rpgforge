import asyncio
import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.models.game import Game
from app.models.turn import Turn
from app.services.json_utils import parse_json_object
from app.services.model_router import ModelRouter
from app.services.prompt_loader import load_prompt_template
from app.services.story_settings import (
    build_runtime_story,
    project_runtime_story_for_state_ops,
)

STATE_EXTRACTOR_TIMEOUT_SECONDS = 150.0
# state delta 是全链路最大的结构化输出（库存/NPC/任务/线索/xp/技能/关系/lore 多段并存），
# 4096 在高密度回合会截断导致整回合状态丢失。提到 8000（与 GM_REWRITE 同档），
# 配合 json_utils 的尾部修补兜底，进一步降低截断丢回合的概率。
STATE_EXTRACTOR_MAX_TOKENS = 8000
SCENE_HEADING_RE = re.compile(r"^\s{0,3}#{3,4}\s+(.+?)\s*$", re.MULTILINE)
PLACE_HINTS = (
    "基地",
    "庭院",
    "主堡",
    "主楼",
    "大厅",
    "入口",
    "山",
    "小道",
    "医院",
    "超市",
    "仓库",
    "房",
    "区",
    "站",
    "塔",
    "桥",
    "街",
    "镇",
    "城",
    "村",
    "营地",
    "洞",
    "隧道",
    "实验室",
    "研究所",
    "废墟",
)
TIME_HEADING_TEXTS = {
    "清晨",
    "黎明",
    "上午",
    "中午",
    "午后",
    "下午",
    "傍晚",
    "黄昏",
    "夜晚",
    "深夜",
    "凌晨",
    "黎明前",
    "几分钟后",
    "片刻后",
    "与此同时",
}
SCENE_HEADING_PLACE_WORDS = ("内", "外", "前", "后", "口", "顶", "下", "层")


class StateDeltaExtraction(BaseModel):
    time_delta: str | None = None
    time_current: str | None = None
    location_change: str | dict[str, Any] | None = None
    inventory_add: list[Any] = Field(default_factory=list)
    inventory_remove: list[Any] = Field(default_factory=list)
    npc_updates: list[Any] = Field(default_factory=list)
    quest_updates: list[Any] = Field(default_factory=list)
    faction_updates: list[Any] = Field(default_factory=list)
    protagonist_updates: dict[str, Any] = Field(default_factory=dict)
    variable_updates: dict[str, Any] = Field(default_factory=dict)
    new_lore_candidates: list[Any] = Field(default_factory=list)
    new_known_facts: list[Any] = Field(default_factory=list)
    new_hidden_facts: list[Any] = Field(default_factory=list)
    open_thread_updates: list[Any] = Field(default_factory=list)
    condition_updates: list[Any] = Field(default_factory=list)
    relationship_events: list[Any] = Field(default_factory=list)
    story_progress_update: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "inventory_add",
        "inventory_remove",
        "npc_updates",
        "quest_updates",
        "faction_updates",
        "new_lore_candidates",
        "new_known_facts",
        "new_hidden_facts",
        "open_thread_updates",
        "condition_updates",
        "relationship_events",
        mode="before",
    )
    @classmethod
    def coerce_list(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    @field_validator("story_progress_update", mode="before")
    @classmethod
    def coerce_mapping(cls, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}


class StateExtractorValidationError(RuntimeError):
    pass


class StateExtractor:
    def __init__(self, router: ModelRouter | None = None) -> None:
        self.router = router or ModelRouter()

    async def extract(
        self,
        game: Game,
        turn: Turn,
        director_decision: dict[str, Any] | None = None,
        drift_findings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current_state = game.state.state_json if game.state else {}
        payload: dict[str, Any] = {
            "game": {
                "title": game.title,
                "genre": game.genre,
                "description": game.description,
            },
            # 按需注入：extractor 只算状态变更，用精简投影而非全量 runtime_story。
            "runtime_story": project_runtime_story_for_state_ops(
                build_runtime_story(game.config, current_state)
            ),
            "current_state": current_state,
            "turn": {
                "turn_number": turn.turn_number,
                "player_input": turn.player_input,
                "gm_output": turn.gm_output,
                "visible_summary": turn.visible_summary,
            },
        }
        # 上游 Director / Drift 的提示信号：让 extractor 重点关注它们提到的连续性/冲突项。
        director_hints = _director_hints(director_decision)
        if director_hints:
            payload["director_hints"] = director_hints
        drift_hints = _drift_hints(drift_findings)
        if drift_hints:
            payload["drift_hints"] = drift_hints
        messages = [
            {"role": "system", "content": load_prompt_template("extract_state_delta.md")},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ]
        try:
            result = await asyncio.wait_for(
                self.router.use_flash(
                    "state_delta_extract",
                    messages,
                    json_mode=True,
                    max_tokens=STATE_EXTRACTOR_MAX_TOKENS,
                    reasoning_effort=None,
                    respect_route=False,
                ),
                timeout=STATE_EXTRACTOR_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise StateExtractorValidationError(
                f"状态提取超过 {int(STATE_EXTRACTOR_TIMEOUT_SECONDS)} 秒。"
            ) from exc
        try:
            parsed = parse_json_object(result.content, repair_truncated=True)
            delta = StateDeltaExtraction.model_validate(parsed).model_dump()
            _backfill_scene_location_change(delta, current_state, turn)
            return delta
        except (ValueError, ValidationError) as exc:
            raise StateExtractorValidationError(str(exc)) from exc


def _director_hints(decision: dict[str, Any] | None) -> dict[str, Any]:
    """从 director_decision 抽 extractor 实际能用上的提示字段。"""
    if not isinstance(decision, dict):
        return {}
    hints: dict[str, Any] = {}
    for key in ("continuity_notes", "active_material_titles", "forbidden_reveals"):
        value = decision.get(key)
        if isinstance(value, list) and value:
            hints[key] = value
    for key in ("scene_objective", "current_act", "pacing_limit"):
        value = decision.get(key)
        if isinstance(value, str) and value.strip():
            hints[key] = value
    return hints


def _drift_hints(findings: dict[str, Any] | None) -> dict[str, Any]:
    """从 drift_validation 抽 extractor 需要关注的状态冲突。"""
    if not isinstance(findings, dict):
        return {}
    hints: dict[str, Any] = {}
    for key in ("state_conflicts", "contract_violations", "issues"):
        value = findings.get(key)
        if isinstance(value, list) and value:
            hints[key] = value
    severity = findings.get("severity")
    if isinstance(severity, str) and severity.strip():
        hints["severity"] = severity
    return hints


def _backfill_scene_location_change(
    delta: dict[str, Any],
    current_state: dict[str, Any],
    turn: Turn,
) -> None:
    if delta.get("location_change"):
        return
    inferred = _infer_common_npc_location(delta, current_state)
    if not inferred:
        inferred = _infer_location_from_scene_heading(current_state, turn.gm_output)
    if not inferred:
        return

    current = _current_location(current_state)
    if current:
        delta["location_change"] = {"from": current, "to": inferred}
    else:
        delta["location_change"] = inferred
    _backfill_protagonist_npc_location(delta, current_state, inferred)


def _infer_location_from_scene_heading(
    current_state: dict[str, Any],
    gm_output: str | None,
) -> str:
    heading = _first_scene_heading(gm_output)
    if not heading:
        return ""

    normalized_heading = _normalize_location_text(heading)
    if not normalized_heading:
        return ""

    current = _current_location(current_state)
    normalized_current = _normalize_location_text(current)
    if normalized_current == normalized_heading:
        return ""

    known_locations = _known_scene_locations(current_state)
    for location in known_locations:
        normalized_location = _normalize_location_text(location)
        if normalized_location == normalized_heading:
            return location

    if normalized_current and normalized_current.startswith(normalized_heading):
        return ""
    if _heading_looks_like_location(heading):
        return _clean_heading_location(heading)
    return ""


def _first_scene_heading(gm_output: str | None) -> str:
    match = SCENE_HEADING_RE.search(gm_output or "")
    if not match:
        return ""
    heading = match.group(1).strip().strip("#").strip()
    return heading


def _current_location(state: dict[str, Any]) -> str:
    location = state.get("location")
    if not isinstance(location, dict):
        return ""
    return _text(location.get("current") or location.get("name"))


def _known_scene_locations(state: dict[str, Any]) -> list[str]:
    locations: list[str] = []
    location = state.get("location")
    if isinstance(location, dict):
        locations.extend(_text(item) for item in location.get("known_locations") or [])
        locations.extend(
            _text(location.get(key))
            for key in ("current", "name", "to", "destination")
        )

    for npc in state.get("npcs") or []:
        if not isinstance(npc, dict):
            continue
        locations.append(_text(npc.get("location") or npc.get("current_location")))

    result: list[str] = []
    for item in locations:
        if item and item not in result:
            result.append(item)
    return result


def _infer_common_npc_location(
    delta: dict[str, Any],
    current_state: dict[str, Any],
) -> str:
    location_counts: dict[str, int] = {}
    location_by_key: dict[str, str] = {}
    current = _current_location(current_state)
    normalized_current = _normalize_location_text(current)

    for update in delta.get("npc_updates") or []:
        if not isinstance(update, dict):
            continue
        location = _text(update.get("location") or update.get("current_location"))
        if not location:
            continue
        key = _normalize_location_text(location)
        if not key or key == normalized_current:
            continue
        location_counts[key] = location_counts.get(key, 0) + 1
        location_by_key.setdefault(key, location)

    if not location_counts:
        return ""
    key, count = max(location_counts.items(), key=lambda item: item[1])
    if count < 2:
        return ""
    return location_by_key[key]


def _backfill_protagonist_npc_location(
    delta: dict[str, Any],
    current_state: dict[str, Any],
    location: str,
) -> None:
    protagonist_name = _protagonist_name(current_state)
    if not protagonist_name or not _state_has_npc(current_state, protagonist_name):
        return

    updates = delta.setdefault("npc_updates", [])
    if not isinstance(updates, list):
        return
    for update in updates:
        if not isinstance(update, dict) or not _npc_update_matches(update, protagonist_name):
            continue
        if not _text(update.get("location") or update.get("current_location")):
            update["location"] = location
        return
    updates.append({"name": protagonist_name, "location": location})


def _protagonist_name(state: dict[str, Any]) -> str:
    protagonist = state.get("protagonist")
    if not isinstance(protagonist, dict):
        return ""
    return _text(protagonist.get("name") or protagonist.get("id") or protagonist.get("title"))


def _state_has_npc(state: dict[str, Any], name: str) -> bool:
    return any(
        isinstance(npc, dict) and _npc_record_matches(npc, name)
        for npc in state.get("npcs") or []
    )


def _npc_record_matches(npc: dict[str, Any], name: str) -> bool:
    candidates = [
        _text(npc.get("name")),
        _text(npc.get("id")),
        _text(npc.get("title")),
    ]
    for alias in npc.get("aliases") or []:
        candidates.append(_text(alias))
    return name in candidates


def _npc_update_matches(update: dict[str, Any], name: str) -> bool:
    return name in {
        _text(update.get("name")),
        _text(update.get("id")),
        _text(update.get("npc")),
        _text(update.get("title")),
    }


def _heading_looks_like_location(heading: str) -> bool:
    normalized = _normalize_location_text(heading)
    if not normalized or normalized in TIME_HEADING_TEXTS:
        return False
    if len(normalized) <= 3 and any(word in normalized for word in TIME_HEADING_TEXTS):
        return False
    if any(hint in heading for hint in PLACE_HINTS):
        return True
    if "·" in heading or "・" in heading:
        return True
    if any(normalized.endswith(word) for word in SCENE_HEADING_PLACE_WORDS):
        return True
    if re.search(r"\d", heading) and len(normalized) >= 4:
        return True
    return False


def _clean_heading_location(heading: str) -> str:
    text = _text(heading)
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"\s+", "", text)
    return text.strip()


def _normalize_location_text(value: Any) -> str:
    text = _text(value)
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[·・]", "", text)
    return text.strip()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
