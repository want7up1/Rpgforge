import json

import anyio
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.generator_job import GeneratorChatJob, GeneratorFinalizeJob
from app.schemas.generator import (
    GeneratedGameConfig,
    GeneratorChatRequest,
    GeneratorFinalizeRequest,
    GeneratorFinalizeResponse,
)
from app.services.deepseek_client import (
    ChatCompletionResult,
    ChatCompletionStreamChunk,
    DeepSeekClient,
)
from app.services.game_generator import GameGeneratorService
from app.services.generator_jobs import run_finalize_job
from app.services.job_queue import enqueue_chat_job, rq_job_id
from app.services.model_router import ModelRouter
from tests.story_settings_fixtures import build_generated_config


def test_generator_chat_requires_deepseek_api_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    response = TestClient(app).post(
        "/api/generator/chat",
        json={"user_input": "我想玩黑暗武侠，主角是失忆镖师。"},
    )

    assert response.status_code == 503
    assert "DEEPSEEK_API_KEY" in response.json()["detail"]


def test_generator_interview_uses_pro_with_high_thinking() -> None:
    calls: list[dict[str, object]] = []

    class FakeRouter:
        async def use_pro(self, task_type, messages, **kwargs):
            calls.append({"task_type": task_type, "messages": messages, **kwargs})
            return ChatCompletionResult(
                content=(
                    '{"stage":"ready_to_generate","confirmed_requirements":{'
                    '"story_background":"黑暗武侠","core_premise":"失忆镖师追查义庄旧案",'
                    '"must_include":["雨夜义庄"],"forbidden_content":["不要修仙"],'
                    '"playstyle_preferences":["调查"],"tone_preferences":["冷峻"],'
                    '"raw_user_input":"黑暗武侠，主角是失忆镖师。"},'
                    '"missing_questions":[],"assistant_reply":"设定已确认，可以生成完整配置。"}'
                ),
                model="deepseek-reasoner",
                raw={},
            )

    result = anyio.run(
        GameGeneratorService(router=FakeRouter()).interview,
        GeneratorChatRequest(user_input="黑暗武侠，主角是失忆镖师。"),
    )

    assert result.stage == "ready_to_generate"
    assert result.confirmed_requirements["core_premise"] == "失忆镖师追查义庄旧案"
    assert calls[0]["task_type"] == "generator_interview"
    assert calls[0]["reasoning_effort"] == "high"


def test_generator_interview_stream_reports_reasoning_and_content() -> None:
    calls: list[dict[str, object]] = []
    updates: list[tuple[str, str, str | None]] = []

    class FakeRouter:
        async def use_pro_stream(self, task_type, messages, **kwargs):
            calls.append({"task_type": task_type, "messages": messages, **kwargs})
            yield ChatCompletionStreamChunk(
                reasoning_delta="先确认类型与主角。",
                model="deepseek-v4-pro",
            )
            yield ChatCompletionStreamChunk(
                content_delta=(
                    '{"stage":"ready_to_generate","confirmed_requirements":{'
                    '"story_background":"黑暗武侠","core_premise":"失忆镖师追查义庄旧案",'
                    '"must_include":[],"forbidden_content":[],'
                    '"playstyle_preferences":[],"tone_preferences":[],"raw_user_input":"黑暗武侠"},'
                    '"missing_questions":[],"assistant_reply":"设定已确认，可以生成完整配置。"}'
                ),
                model="deepseek-v4-pro",
            )

    async def run_stream():
        async def on_update(reasoning: str, content: str, model: str | None) -> None:
            updates.append((reasoning, content, model))

        return await GameGeneratorService(router=FakeRouter()).interview_stream(
            GeneratorChatRequest(user_input="黑暗武侠，主角是失忆镖师。"),
            on_update=on_update,
        )

    result = anyio.run(run_stream)

    assert result.stage == "ready_to_generate"
    assert calls[0]["reasoning_effort"] == "high"
    assert updates[0] == ("先确认类型与主角。", "", "deepseek-v4-pro")
    assert updates[-1][1].startswith('{"stage"')


def test_generator_interview_normalizes_legacy_requirements() -> None:
    class FakeRouter:
        async def use_pro(self, task_type, messages, **kwargs):
            del task_type, messages, kwargs
            return ChatCompletionResult(
                content=(
                    '{"stage":"ready_to_generate","confirmed_requirements":{'
                    '"genre":"武侠","protagonist_identity":"失忆镖师",'
                    '"core_gameplay":"调查旧案","must_hit_beats":["红伞女人"],'
                    '"forbidden_elements":["不要修仙"]},'
                    '"missing_questions":[],"assistant_reply":"可以生成。"}'
                ),
                model="deepseek-v4-pro",
                raw={},
            )

    result = anyio.run(
        GameGeneratorService(router=FakeRouter()).interview,
        GeneratorChatRequest(user_input="黑暗武侠，主角是失忆镖师。"),
    )

    assert result.confirmed_requirements["story_background"] == "武侠"
    assert "失忆镖师" in result.confirmed_requirements["core_premise"]
    assert result.confirmed_requirements["must_include"] == ["红伞女人"]
    assert result.confirmed_requirements["forbidden_content"] == ["不要修仙"]


def test_deepseek_payload_enables_thinking_without_temperature() -> None:
    payload = DeepSeekClient._build_payload(
        model="deepseek-v4-pro",
        messages=[{"role": "user", "content": "test"}],
        stream=True,
        json_mode=True,
        thinking="enabled",
        reasoning_effort="high",
        temperature=0.7,
        max_tokens=128,
    )

    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "high"
    assert payload["stream"] is True
    assert "temperature" not in payload


def test_model_router_flash_uses_high_thinking(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeClient:
        async def chat_completion(self, **kwargs):
            calls.append(kwargs)
            return ChatCompletionResult(content="{}", model=kwargs["model"], raw={})

    monkeypatch.setattr(settings, "deepseek_flash_model", "deepseek-v4-flash")
    router = ModelRouter(client=FakeClient(), app_settings=settings)

    anyio.run(router.use_flash, "state_delta", [{"role": "user", "content": "test"}])

    assert calls[0]["model"] == "deepseek-v4-flash"
    assert calls[0]["thinking"] == "enabled"
    assert calls[0]["reasoning_effort"] == "high"


def test_generator_finalize_pipeline_merges_streamed_story_settings_v2() -> None:
    calls: list[dict[str, object]] = []
    updates: list[tuple[str, str, str | None]] = []

    class FakeRouter:
        async def use_pro_stream(self, task_type, messages, **kwargs):
            calls.append({"task_type": task_type, "messages": messages, **kwargs})
            yield ChatCompletionStreamChunk(
                reasoning_delta=f"{task_type} thinking.",
                model="deepseek-v4-pro",
            )
            content = json.dumps(finalize_stream_payload(task_type), ensure_ascii=False)
            midpoint = len(content) // 2
            yield ChatCompletionStreamChunk(
                content_delta=content[:midpoint],
                model="deepseek-v4-pro",
            )
            yield ChatCompletionStreamChunk(
                content_delta=content[midpoint:],
                model="deepseek-v4-pro",
            )

    async def run_finalize():
        async def on_update(reasoning: str, content: str, model: str | None) -> None:
            updates.append((reasoning, content, model))

        return await GameGeneratorService(router=FakeRouter()).finalize_stream(
            GeneratorFinalizeRequest(
                concept="黑暗武侠",
                history=[],
                confirmed_requirements={
                    "story_background": "黑暗武侠，雁回镇义庄。",
                    "core_premise": "失忆镖师追查义庄旧案。",
                    "must_include": ["红伞女人"],
                    "forbidden_content": ["不要修仙飞升"],
                    "playstyle_preferences": ["调查"],
                    "tone_preferences": ["冷峻"],
                },
            ),
            on_update=on_update,
        )

    result = anyio.run(run_finalize)
    task_types = {str(call["task_type"]) for call in calls}

    assert task_types == {
        "generator_finalize_outline",
        "generator_finalize_core_characters",
        "generator_finalize_act_plan",
        "generator_finalize_main_quest_path",
        "generator_finalize_core_mechanics",
        "generator_finalize_action_style_rules",
        "generator_finalize_story_material_library",
        "generator_finalize_home_base",
        "generator_finalize_hard_rules",
        "generator_finalize_initial_state",
    }
    assert not any("lore_entries" in task_type or "modes" in task_type for task_type in task_types)
    assert all(call["reasoning_effort"] == "high" for call in calls)
    assert result.config.title == "雁回镇旧案"
    story = result.config.story_settings
    assert story["format_version"] == "rpgforge.story.v2"
    assert story["story_core"]["canon_terms"] == ["雁回镇", "义庄", "红伞女人"]
    assert "红伞女人" in story["story_core"]["must_preserve"]
    assert "不要修仙飞升" in story["story_core"]["must_not_become"]
    assert "不要修仙飞升" in story["story_core"]["forbidden_drift"]
    assert story["core_characters"][0]["name"] == "沈砚"
    assert story["act_plan"][0]["completion_anchors"][0]["id"] == "act_1_find_mud"
    assert story["story_material_library"][0]["gm_secret"] == "义庄暗藏旧案账册。"
    assert result.config.initial_state["current_turn"] == 0
    assert result.config.initial_state["protagonist"]["name"] == "沈砚"
    assert any("剧本生成：导演总纲完成" in reasoning for reasoning, _content, _model in updates)
    assert any("## 剧本素材库" in content for _reasoning, content, _model in updates)
    assert updates[-1][1].startswith("{")


def test_generator_finalize_retries_invalid_outline_without_shortening() -> None:
    calls: list[dict[str, object]] = []

    class FakeRouter:
        async def use_pro_stream(self, task_type, messages, **kwargs):
            calls.append({"task_type": task_type, "messages": messages, **kwargs})
            if task_type == "generator_finalize_outline" and _task_count(task_type, calls) == 1:
                yield ChatCompletionStreamChunk(
                    content_delta='{"format_version":"rpgforge.story.v2","worldview":{"summary":"截断',
                    model="deepseek-v4-pro",
                )
                return
            yield ChatCompletionStreamChunk(
                content_delta=json.dumps(finalize_stream_payload(task_type), ensure_ascii=False),
                model="deepseek-v4-pro",
            )

    result = anyio.run(
        GameGeneratorService(router=FakeRouter()).finalize,
        GeneratorFinalizeRequest(concept="黑暗武侠", history=[], confirmed_requirements={}),
    )
    outline_calls = [
        call for call in calls if call["task_type"] == "generator_finalize_outline"
    ]

    assert result.config.title == "雁回镇旧案"
    assert len(outline_calls) == 2
    assert outline_calls[0]["max_tokens"] == 12000
    assert outline_calls[1]["max_tokens"] == 12000
    assert "保持原有剧情丰富度" in outline_calls[1]["messages"][-1]["content"]
    assert "game_profile" in outline_calls[1]["messages"][-1]["content"]


def test_generator_finalize_retries_invalid_section() -> None:
    calls: list[str] = []

    class FakeRouter:
        async def use_pro_stream(self, task_type, messages, **kwargs):
            del messages, kwargs
            calls.append(task_type)
            if (
                task_type == "generator_finalize_story_material_library"
                and calls.count(task_type) == 1
            ):
                yield ChatCompletionStreamChunk(
                    content_delta='{"story_material_library":{"bad":"not list"}}',
                    model="deepseek-v4-pro",
                )
                return
            yield ChatCompletionStreamChunk(
                content_delta=json.dumps(finalize_stream_payload(task_type), ensure_ascii=False),
                model="deepseek-v4-pro",
            )

    result = anyio.run(
        GameGeneratorService(router=FakeRouter()).finalize,
        GeneratorFinalizeRequest(concept="黑暗武侠", history=[], confirmed_requirements={}),
    )

    assert result.config.title == "雁回镇旧案"
    assert calls.count("generator_finalize_story_material_library") == 2


def test_generator_finalize_job_persists_stream_progress(db_session, monkeypatch) -> None:
    class StreamingGameGeneratorService:
        async def finalize_stream(self, request, on_update=None):
            del request
            if on_update:
                await on_update("正在生成剧本素材库。", '{"title":"雁回镇旧案"', "deepseek-v4-pro")
            return GeneratorFinalizeResponse(
                config=build_generated_config(),
                model_used="deepseek-v4-pro",
            )

    job = GeneratorFinalizeJob(
        status="pending",
        request_json={"concept": "黑暗武侠", "history": [], "confirmed_requirements": {}},
    )
    db_session.add(job)
    db_session.commit()
    monkeypatch.setattr(
        "app.services.generator_jobs.GameGeneratorService",
        StreamingGameGeneratorService,
    )

    anyio.run(run_finalize_job, job.id)

    db_session.expire_all()
    saved = db_session.get(GeneratorFinalizeJob, job.id)
    assert saved.status == "completed"
    assert saved.reasoning_content == "正在生成剧本素材库。"
    assert saved.content_buffer == '{"title":"雁回镇旧案"'
    assert saved.result_json["story_settings"]["format_version"] == "rpgforge.story.v2"


def test_generator_chat_job_lifecycle(reset_database, monkeypatch) -> None:
    monkeypatch.setattr("app.routers.generator.enqueue_chat_job", lambda job_id: None)
    client = TestClient(app)

    response = client.post(
        "/api/generator/chat-jobs",
        json={
            "user_input": "黑暗武侠，主角是失忆镖师。",
            "history": [],
            "confirmed_requirements": {},
        },
    )
    payload = response.json()
    read_response = client.get(f"/api/generator/chat-jobs/{payload['id']}")
    active_response = client.get("/api/generator/chat-jobs/active")

    assert response.status_code == 202
    assert read_response.json()["status"] == "pending"
    assert active_response.json()["id"] == payload["id"]


def test_generator_finalize_job_returns_completed_config(db_session) -> None:
    config = build_generated_config().model_dump(mode="json")
    job = GeneratorFinalizeJob(
        status="completed",
        request_json={"concept": "黑暗武侠", "history": [], "confirmed_requirements": {}},
        result_json=config,
        model_used="deepseek-reasoner",
    )
    db_session.add(job)
    db_session.commit()

    response = TestClient(app).get(f"/api/generator/finalize-jobs/{job.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["config"]["story_settings"]["format_version"] == "rpgforge.story.v2"


def test_generator_create_game_from_story_settings_config(reset_database) -> None:
    response = TestClient(app).post(
        "/api/generator/create-game",
        json={"generated_config": build_generated_config().model_dump(mode="json")},
    )

    assert response.status_code == 201
    game = response.json()["game"]
    assert game["title"] == "雁回镇旧案"
    assert game["config"]["story_settings"]["story_core"]["main_goal"] == "查清义庄旧案。"
    assert [character["name"] for character in game.get("characters", [])] == []


def test_enqueue_chat_job_uses_current_rq_timeout_argument(monkeypatch) -> None:
    calls = []

    class FakeQueue:
        def enqueue_call(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("app.services.job_queue.rpgforge_queue", lambda: FakeQueue())

    from uuid import uuid4

    job_id = uuid4()
    enqueue_chat_job(job_id)

    assert calls[0]["job_id"] == rq_job_id("chat", job_id)
    assert ":" not in calls[0]["job_id"]
    assert calls[0]["args"] == (str(job_id),)
    assert calls[0]["timeout"] > 0
    assert "job_timeout" not in calls[0]


def test_generator_chat_job_returns_completed_response(db_session) -> None:
    result_json = {
        "stage": "ready_to_generate",
        "confirmed_requirements": {"genre": "武侠"},
        "missing_questions": [],
        "assistant_reply": "设定已确认，可以生成完整配置。",
        "model_used": "deepseek-v4-pro",
    }
    job = GeneratorChatJob(
        status="completed",
        request_json={"user_input": "黑暗武侠", "history": [], "confirmed_requirements": {}},
        result_json=result_json,
        model_used="deepseek-v4-pro",
    )
    db_session.add(job)
    db_session.commit()

    response = TestClient(app).get(f"/api/generator/chat-jobs/{job.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["response"]["stage"] == "ready_to_generate"


def finalize_stream_payload(task_type: str) -> dict:
    if task_type == "generator_finalize_outline":
        return {
            "format_version": "rpgforge.story.v2",
            "game_profile": {
                "title": "雁回镇旧案",
                "genre": "黑暗武侠",
                "description": "失忆镖师追查义庄旧案。",
                "tone": "冷峻",
            },
            "worldview": {
                "summary": "雁回镇义庄旧案多年未结。",
                "setting": "雁回镇义庄",
                "public_facts": ["镇外旧义庄无人敢近。"],
                "hidden_facts": ["义庄暗藏旧案账册。"],
            },
            "story_core": {
                "premise": "失忆镖师追查义庄旧案。",
                "core_fantasy": "调查旧案。",
                "central_mystery": "沈砚失忆前到底护送了什么？",
                "main_goal": "查清义庄旧案。",
                "current_act": "act_1",
                "must_preserve": [],
                "must_not_become": [],
                "forbidden_drift": [],
                "canon_terms": ["雁回镇", "义庄"],
            },
            "act_plan_outline": [],
            "main_quest_path_outline": [],
            "core_mechanics_outline": [],
            "material_plan": [],
            "home_base": {"name": "[地点]", "role": "休整与情报据点"},
            "hard_rules": {
                "must_follow": ["每回合给出 A/B/C/D 四个具体行动选项。"],
                "must_not": [],
                "reveal_rules": ["不要提前揭露账册真凶。"],
                "continuity_rules": ["保持人物动机一致。"],
            },
            "generation_parameters": {
                "narrative_target_min_chars": 800,
                "narrative_target_max_chars": 1200,
                "narrative_min_chars": 700,
                "paragraph_min": 3,
                "paragraph_max": 6,
                "scene_heading_max": 1,
                "emphasis_min": 2,
                "emphasis_max": 4,
                "recent_turn_excerpt_chars": 420,
            },
        }
    if task_type == "generator_finalize_core_characters":
        return {
            "core_characters": [
                {
                    "id": "shen_yan",
                    "name": "沈砚",
                    "aliases": [],
                    "role": "protagonist",
                    "identity": "失忆镖师",
                    "description": "追查义庄旧案的主角。",
                    "appearance": "旧青色短打，右手缠着褪色布带。",
                    "portrait_prompt": "",
                    "visibility": "visible",
                    "dramatic_function": "调查主角",
                    "desire": "找回记忆",
                    "fear": "自己与旧案有关",
                    "leverage": "义庄铃声",
                    "relationship_arc": "从孤身调查到信任同伴",
                    "public_limit": "不会提前知道真凶",
                }
            ]
        }
    if task_type == "generator_finalize_act_plan":
        return {
            "act_plan": [
                {
                    "id": "act_1",
                    "title": "义庄夜雨",
                    "objective": "找到旧案第一条线索。",
                    "dramatic_question": "沈砚能否证明自己不是帮凶？",
                    "pressure": "黑伞客也在寻找线索。",
                    "must_hit_beats": ["发现门槛泥痕"],
                    "allowed_reveals": ["旧案仍有人遮掩"],
                    "forbidden_reveals": ["账册真凶"],
                    "completion_anchors": [
                        {
                            "id": "act_1_find_mud",
                            "title": "找到门槛泥痕",
                            "required": True,
                            "description": "确认有人近期翻入义庄。",
                            "completion_signal": "发现门槛泥痕。",
                        }
                    ],
                    "transition_to_next_act": {
                        "target_act": "act_2",
                        "condition": "发现泥痕后追查黑伞客。",
                    },
                },
                {
                    "id": "act_2",
                    "title": "黑伞追踪",
                    "objective": "追查黑伞客。",
                    "dramatic_question": "陆沉舟是敌是友？",
                    "pressure": "捕房封锁线索。",
                    "must_hit_beats": ["找到账册残页"],
                    "allowed_reveals": ["账册残页存在"],
                    "forbidden_reveals": ["最终主谋"],
                    "completion_anchors": [],
                    "transition_to_next_act": {},
                },
            ]
        }
    if task_type == "generator_finalize_main_quest_path":
        return {
            "main_quest_path": [
                {
                    "id": "main_quest_1",
                    "act_id": "act_1",
                    "title": "查明义庄泥痕",
                    "objective": "找到旧案第一条线索。",
                    "player_visible": "调查义庄异常痕迹。",
                    "completion_signal": "发现门槛泥痕。",
                    "optional": False,
                }
            ]
        }
    if task_type == "generator_finalize_core_mechanics":
        return {
            "core_mechanics": [
                {
                    "id": "investigation",
                    "name": "调查推进",
                    "rule": "给线索不给答案。",
                    "progression": "锚点完成后切幕。",
                    "visibility": "public",
                }
            ]
        }
    if task_type == "generator_finalize_action_style_rules":
        return {
            "action_style_rules": [
                {
                    "id": "investigation",
                    "name": "调查行动",
                    "triggers": ["调查", "检查"],
                    "rule": "提供可验证线索。",
                    "priority": "high",
                    "enabled": True,
                }
            ]
        }
    if task_type == "generator_finalize_story_material_library":
        return {
            "story_material_library": [
                {
                    "id": "yizhuang",
                    "title": "义庄",
                    "type": "clue",
                    "keywords": ["义庄", "泥痕"],
                    "triggers": ["义庄", "泥痕"],
                    "priority": "critical",
                    "always_on": True,
                    "visibility": "mixed",
                    "public_info": "镇外旧义庄无人敢近。",
                    "gm_secret": "义庄暗藏旧案账册。",
                    "content": "义庄门槛泥痕指向黑伞客。",
                    "usage": "玩家调查义庄时召回。",
                    "enabled": True,
                }
            ]
        }
    if task_type == "generator_finalize_home_base":
        return {
            "home_base": {
                "id": "home_base",
                "name": "[地点]",
                "role": "休整与情报据点",
                "public_functions": ["整理线索"],
                "hidden_hooks": [],
            }
        }
    if task_type == "generator_finalize_hard_rules":
        return {
            "hard_rules": {
                "must_follow": ["每回合给出 A/B/C/D 四个具体行动选项。"],
                "must_not": ["不要修仙飞升"],
                "reveal_rules": ["不要提前揭露账册真凶。"],
                "continuity_rules": ["保持人物动机一致。"],
            }
        }
    if task_type == "generator_finalize_initial_state":
        return {
            "initial_state": {
                "current_turn": 0,
                "time": {"current": "秋末雨夜"},
                "location": {"current": "雁回镇义庄"},
                "protagonist": {"name": "沈砚", "identity": "失忆镖师"},
                "progression": {
                    "level": 1,
                    "xp": 0,
                    "next_level_xp": 100,
                    "total_xp": 0,
                    "xp_log": [],
                },
                "skills": [],
                "abilities": [],
                "conditions": [],
                "relationships": [],
                "inventory": [],
                "quests": [],
                "npcs": [],
                "factions": [],
                "variables": {},
                "known_facts": [],
                "hidden_facts": [],
                "open_threads": [],
            }
        }
    raise AssertionError(f"Unexpected task type: {task_type}")


def _task_count(task_type: str, calls: list[dict[str, object]]) -> int:
    return sum(1 for call in calls if call["task_type"] == task_type)
