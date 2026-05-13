import json
from datetime import UTC, datetime, timedelta
from threading import Thread
from time import sleep
from uuid import uuid4

import anyio
from fastapi.testclient import TestClient

from app.config import settings
from app.db.session import SessionLocal
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
from app.services.job_queue import enqueue_chat_job, recover_stale_jobs, rq_job_id
from app.services.model_router import ModelRouter


def test_generator_chat_requires_deepseek_api_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    client = TestClient(app)

    response = client.post(
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

    service = GameGeneratorService(router=FakeRouter())

    result = anyio.run(
        service.interview,
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
        service = GameGeneratorService(router=FakeRouter())

        async def on_update(reasoning: str, content: str, model: str | None) -> None:
            updates.append((reasoning, content, model))

        return await service.interview_stream(
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

    service = GameGeneratorService(router=FakeRouter())

    result = anyio.run(
        service.interview,
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

    anyio.run(
        router.use_flash,
        "state_delta",
        [{"role": "user", "content": "test"}],
    )

    assert calls[0]["model"] == "deepseek-v4-flash"
    assert calls[0]["thinking"] == "enabled"
    assert calls[0]["reasoning_effort"] == "high"


def test_generator_finalize_pipeline_merges_streamed_sections() -> None:
    calls: list[dict[str, object]] = []
    updates: list[tuple[str, str, str | None]] = []

    class FakeRouter:
        async def use_pro_stream(self, task_type, messages, **kwargs):
            calls.append({"task_type": task_type, "messages": messages, **kwargs})
            yield ChatCompletionStreamChunk(
                reasoning_delta=f"{task_type} thinking.",
                model="deepseek-v4-pro",
            )
            content = json.dumps(
                finalize_stream_payload(task_type),
                ensure_ascii=False,
            )
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
        service = GameGeneratorService(router=FakeRouter())

        async def on_update(reasoning: str, content: str, model: str | None) -> None:
            updates.append((reasoning, content, model))

        return await service.finalize_stream(
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
        "generator_finalize_characters",
        "generator_finalize_lore_entries",
        "generator_finalize_modes",
        "generator_finalize_initial_state",
        "generator_finalize_rules",
    }
    assert all(call["reasoning_effort"] == "high" for call in calls)
    assert result.config.title == "雁回镇旧案"
    assert result.config.script_outline["campaign_contract"]["canon_terms"] == [
        "雁回镇",
        "义庄",
    ]
    assert result.config.script_outline["user_brief"]["must_include"] == ["红伞女人"]
    assert "红伞女人" in result.config.script_outline["campaign_contract"]["must_preserve"]
    assert "不要修仙飞升" in result.config.script_outline["campaign_contract"]["must_not_become"]
    assert "不要修仙飞升" in result.config.script_outline["campaign_contract"]["forbidden_drift"]
    assert result.config.characters[0].name == "沈砚"
    assert result.config.initial_state["current_turn"] == 0
    assert result.config.initial_state["progression"]["level"] == 1
    assert result.config.lore_entries[0].type == "clue"
    assert result.config.lore_entries[0].gm_secret == "义庄暗藏旧案账册。"
    assert result.config.modes[0].injection
    assert any("配置生成：导演总纲完成" in reasoning for reasoning, _content, _model in updates)
    assert any(
        "配置生成：角色档案思考过程" in reasoning
        and "generator_finalize_characters thinking." in reasoning
        for reasoning, _content, _model in updates
    )
    assert any("## 世界书" in content for _reasoning, content, _model in updates)
    assert updates[-1][1].startswith("{")


def test_generator_finalize_retries_invalid_outline_without_shortening() -> None:
    calls: list[dict[str, object]] = []

    class FakeRouter:
        async def use_pro_stream(self, task_type, messages, **kwargs):
            calls.append({"task_type": task_type, "messages": messages, **kwargs})
            if task_type == "generator_finalize_outline" and _task_count(task_type, calls) == 1:
                yield ChatCompletionStreamChunk(
                    content_delta='{"title":"雁回镇旧案","script_outline":{"truth_map":["截断',
                    model="deepseek-v4-pro",
                )
                return

            yield ChatCompletionStreamChunk(
                content_delta=json.dumps(
                    finalize_stream_payload(task_type),
                    ensure_ascii=False,
                ),
                model="deepseek-v4-pro",
            )

    service = GameGeneratorService(router=FakeRouter())

    result = anyio.run(
        service.finalize,
        GeneratorFinalizeRequest(
            concept="黑暗武侠",
            history=[],
            confirmed_requirements={},
        ),
    )

    outline_calls = [
        call for call in calls if call["task_type"] == "generator_finalize_outline"
    ]
    retry_messages = outline_calls[1]["messages"]

    assert result.config.title == "雁回镇旧案"
    assert len(outline_calls) == 2
    assert outline_calls[0]["max_tokens"] == 12000
    assert outline_calls[1]["max_tokens"] == 12000
    assert "保持原有剧情丰富度" in retry_messages[-1]["content"]


def test_generator_finalize_retries_invalid_section() -> None:
    calls: list[str] = []

    class FakeRouter:
        async def use_pro_stream(self, task_type, messages, **kwargs):
            del messages, kwargs
            calls.append(task_type)
            if task_type == "generator_finalize_lore_entries" and calls.count(task_type) == 1:
                yield ChatCompletionStreamChunk(
                    content_delta='{"lore_entries":[{"title":"义庄","content":"截断',
                    model="deepseek-v4-pro",
                )
                return

            yield ChatCompletionStreamChunk(
                content_delta=json.dumps(
                    finalize_stream_payload(task_type),
                    ensure_ascii=False,
                ),
                model="deepseek-v4-pro",
            )

    service = GameGeneratorService(router=FakeRouter())

    result = anyio.run(
        service.finalize,
        GeneratorFinalizeRequest(
            concept="黑暗武侠",
            history=[],
            confirmed_requirements={},
        ),
    )

    assert result.config.title == "雁回镇旧案"
    assert calls.count("generator_finalize_lore_entries") == 2


def test_generator_finalize_job_marks_timeout_failed(db_session, monkeypatch) -> None:
    class SlowGameGeneratorService:
        async def finalize_stream(self, request, on_update=None):
            del request, on_update
            await anyio.sleep(0.05)

    job = GeneratorFinalizeJob(
        status="pending",
        request_json={
            "concept": "黑暗武侠",
            "history": [],
            "confirmed_requirements": {},
        },
    )
    db_session.add(job)
    db_session.commit()

    monkeypatch.setattr("app.services.generator_jobs.FINALIZE_JOB_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        "app.services.generator_jobs.GameGeneratorService",
        SlowGameGeneratorService,
    )

    anyio.run(run_finalize_job, job.id)

    db_session.expire_all()
    saved = db_session.get(GeneratorFinalizeJob, job.id)
    assert saved.status == "failed"
    assert "完整配置生成超过 14 分钟" in saved.error_message


def test_generator_finalize_job_persists_stream_progress(db_session, monkeypatch) -> None:
    class StreamingGameGeneratorService:
        async def finalize_stream(self, request, on_update=None):
            del request
            if on_update:
                await on_update("正在规划世界书。", '{"title":"雁回镇旧案"', "deepseek-v4-pro")
            return GeneratorFinalizeResponse(
                config=GeneratedGameConfig.model_validate(sample_generated_config()),
                model_used="deepseek-v4-pro",
            )

    job = GeneratorFinalizeJob(
        status="pending",
        request_json={
            "concept": "黑暗武侠",
            "history": [],
            "confirmed_requirements": {},
        },
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
    assert saved.reasoning_content == "正在规划世界书。"
    assert saved.content_buffer == '{"title":"雁回镇旧案"'
    assert saved.progress_message == "完整配置已生成，正在返回结果。"


def test_generator_chat_job_lifecycle(reset_database, monkeypatch) -> None:
    def fake_enqueue_chat_job(job_id):
        del job_id

    monkeypatch.setattr("app.routers.generator.enqueue_chat_job", fake_enqueue_chat_job)
    client = TestClient(app)

    response = client.post(
        "/api/generator/chat-jobs",
        json={
            "user_input": "黑暗武侠，主角是失忆镖师。",
            "history": [],
            "confirmed_requirements": {},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "pending"

    read_response = client.get(f"/api/generator/chat-jobs/{payload['id']}")

    assert read_response.status_code == 200
    assert read_response.json()["status"] == "pending"
    assert read_response.json()["response"] is None

    active_response = client.get("/api/generator/chat-jobs/active")
    assert active_response.status_code == 200
    assert active_response.json()["id"] == payload["id"]


def test_enqueue_chat_job_uses_current_rq_timeout_argument(monkeypatch) -> None:
    calls = []

    class FakeQueue:
        def enqueue_call(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("app.services.job_queue.rpgforge_queue", lambda: FakeQueue())

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
        request_json={
            "user_input": "黑暗武侠",
            "history": [],
            "confirmed_requirements": {},
        },
        result_json=result_json,
        model_used="deepseek-v4-pro",
    )
    db_session.add(job)
    db_session.commit()

    client = TestClient(app)
    response = client.get(f"/api/generator/chat-jobs/{job.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["model_used"] == "deepseek-v4-pro"
    assert payload["response"]["stage"] == "ready_to_generate"


def test_generator_finalize_job_lifecycle(reset_database, monkeypatch) -> None:
    def fake_enqueue_finalize_job(job_id):
        del job_id

    monkeypatch.setattr(
        "app.routers.generator.enqueue_finalize_job",
        fake_enqueue_finalize_job,
    )
    client = TestClient(app)

    response = client.post(
        "/api/generator/finalize-jobs",
        json={
            "concept": "黑暗武侠，主角是失忆镖师。",
            "history": [],
            "confirmed_requirements": {"genre": "武侠"},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "pending"

    read_response = client.get(f"/api/generator/finalize-jobs/{payload['id']}")

    assert read_response.status_code == 200
    assert read_response.json()["status"] == "pending"
    assert read_response.json()["config"] is None

    active_response = client.get("/api/generator/finalize-jobs/active")
    assert active_response.status_code == 200
    assert active_response.json()["id"] == payload["id"]


def test_generator_finalize_job_returns_completed_config(db_session) -> None:
    job = GeneratorFinalizeJob(
        status="completed",
        request_json={
            "concept": "黑暗武侠",
            "history": [],
            "confirmed_requirements": {},
        },
        result_json=sample_generated_config(),
        model_used="deepseek-reasoner",
    )
    db_session.add(job)
    db_session.commit()

    client = TestClient(app)
    response = client.get(f"/api/generator/finalize-jobs/{job.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["model_used"] == "deepseek-reasoner"
    assert payload["config"]["title"] == "雁回镇旧案"


def test_recover_stale_jobs_marks_missing_pending_and_timed_out(db_session, monkeypatch) -> None:
    pending = GeneratorChatJob(
        status="pending",
        request_json={
            "user_input": "黑暗武侠",
            "history": [],
            "confirmed_requirements": {},
        },
    )
    running = GeneratorFinalizeJob(
        status="running",
        request_json={
            "concept": "黑暗武侠",
            "history": [],
            "confirmed_requirements": {"genre": "武侠"},
        },
        last_event_at=datetime.now(UTC) - timedelta(minutes=20),
    )
    db_session.add_all([pending, running])
    db_session.commit()

    monkeypatch.setattr(
        "app.services.job_queue._rq_job_exists",
        lambda connection, job_id: False,
    )

    counts = recover_stale_jobs(connection=object())

    db_session.expire_all()
    assert counts == {"running_timeout": 1, "pending_missing": 1}
    assert db_session.get(GeneratorChatJob, pending.id).status == "failed"
    assert db_session.get(GeneratorFinalizeJob, running.id).status == "failed"


def test_generator_finalize_job_events_returns_terminal_snapshot(db_session) -> None:
    job = GeneratorFinalizeJob(
        status="completed",
        request_json={
            "concept": "黑暗武侠",
            "history": [],
            "confirmed_requirements": {},
        },
        result_json=sample_generated_config(),
        model_used="deepseek-reasoner",
        reasoning_content="配置生成：完整配置已合并。",
        content_buffer='{"title":"雁回镇旧案"}',
        progress_message="完整配置已生成，正在返回结果。",
    )
    db_session.add(job)
    db_session.commit()

    client = TestClient(app)
    with client.stream("GET", f"/api/generator/finalize-jobs/{job.id}/events") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: snapshot" in body
    assert '"terminal": true' in body
    assert "雁回镇旧案" in body


def test_generator_chat_job_events_poll_db_snapshot_without_broker_event(
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.routers.generator.SSE_DB_SNAPSHOT_INTERVAL_SECONDS", 0.01)
    job = GeneratorChatJob(
        status="pending",
        request_json={
            "user_input": "黑暗武侠",
            "history": [],
            "confirmed_requirements": {},
        },
        progress_message="等待 DeepSeek 返回流式事件。",
        last_event_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    def complete_job_later() -> None:
        sleep(0.05)
        with SessionLocal() as db:
            saved = db.get(GeneratorChatJob, job.id)
            assert saved is not None
            now = datetime.now(UTC)
            saved.status = "completed"
            saved.result_json = {
                "stage": "ready_to_generate",
                "confirmed_requirements": {"genre": "武侠"},
                "missing_questions": [],
                "assistant_reply": "设定已确认，可以生成完整配置。",
                "model_used": "deepseek-v4-pro",
            }
            saved.model_used = "deepseek-v4-pro"
            saved.reasoning_content = "确认核心设定。"
            saved.content_buffer = '{"stage":"ready_to_generate"}'
            saved.progress_message = "访谈回复已完成，正在返回结果。"
            saved.last_event_at = now
            saved.completed_at = now
            db.add(saved)
            db.commit()

    updater = Thread(target=complete_job_later)
    updater.start()
    client = TestClient(app)
    try:
        with client.stream("GET", f"/api/generator/chat-jobs/{job.id}/events") as response:
            body = "".join(response.iter_text())
    finally:
        updater.join(timeout=1)

    assert response.status_code == 200
    assert "event: snapshot" in body
    assert '"terminal": true' in body
    assert "设定已确认，可以生成完整配置。" in body


def test_generator_create_game_from_config(reset_database) -> None:
    client = TestClient(app)

    response = client.post(
        "/api/generator/create-game",
        json={"generated_config": sample_generated_config()},
    )

    assert response.status_code == 201
    game = response.json()["game"]
    assert game["title"] == "雁回镇旧案"
    assert len(game["lore_entries"]) == 1
    assert len(game["modes"]) == 1


def _task_count(task_type: str, calls: list[dict[str, object]]) -> int:
    return sum(1 for call in calls if call["task_type"] == task_type)


def finalize_stream_payload(task_type: str) -> dict:
    payloads = {
        "generator_finalize_outline": {
            "title": "雁回镇旧案",
            "genre": "黑暗武侠",
            "description": "失忆镖师追查义庄旧案。",
            "worldview": {
                "summary": "雁回镇义庄暗藏旧案。",
                "tone": "冷峻",
                "setting": "秋末雁回镇",
                "core_conflicts": ["旧案与新案重叠"],
            },
            "script_outline": {
                "title": "雁回镇旧案",
                "user_brief": {
                    "story_background": "黑暗武侠，雁回镇义庄。",
                    "core_premise": "失忆镖师追查义庄旧案。",
                    "must_include": [],
                    "forbidden_content": [],
                    "playstyle_preferences": [],
                    "tone_preferences": [],
                    "raw_user_input": "黑暗武侠",
                },
                "acts": [
                    {
                        "id": "act_1",
                        "name": "义庄夜雨",
                        "objective": "找到镖局旧案的第一条线索。",
                        "dramatic_question": "沈砚能否证明自己不是旧案帮凶？",
                        "pressure": "三日后封案。",
                        "must_hit_beats": ["抵达义庄", "发现账册缺页"],
                        "allowed_reveals": ["旧案仍有人遮掩"],
                        "forbidden_reveals": ["账册真凶"],
                        "relationship_turn": "仵作从回避转为有限协助。",
                        "escalation_limit": "只暴露地方旧案，不升级为江湖大战。",
                        "completion_signal": "确认旧案仍有人遮掩。",
                    }
                ],
                "campaign_contract": {
                    "premise": "失忆镖师从义庄旧案找回过去。",
                    "player_fantasy": "失忆镖师以调查和江湖人情追查旧案。",
                    "central_question": "沈砚失忆前到底护送了什么？",
                    "emotional_arc": "从不安到直面过去。",
                    "must_preserve": [],
                    "must_not_become": [],
                    "tone_do": ["冷峻", "克制"],
                    "tone_dont": ["轻喜剧"],
                    "act_plan": [],
                    "relationship_arcs": [],
                    "forbidden_drift": ["不要变成修仙升级流"],
                    "canon_terms": ["雁回镇", "义庄"],
                    "pacing_rules": ["每回合推进一个可验证线索"],
                    "current_act": "act_1",
                },
                "truth_map": [
                    {
                        "truth": "账册记录了旧案交易。",
                        "public_mask": "义庄只是闹鬼。",
                        "reveal_condition": "玩家拿到账册缺页。",
                    }
                ],
                "clue_ladder": [
                    {
                        "stage": "第一层",
                        "clue": "棺木底部有湿泥。",
                        "points_to": "义庄后门。",
                        "do_not_reveal": "真凶身份。",
                    }
                ],
                "pressure_clock": [
                    {
                        "name": "封案压力",
                        "tick_condition": "玩家拖延调查。",
                        "consequence": "官府封存尸格。",
                        "visibility": "public",
                    }
                ],
            },
            "main_characters": [
                {
                    "name": "沈砚",
                    "role": "protagonist",
                    "identity": "失忆镖师",
                    "relationship_role": "玩家主角",
                }
            ],
            "core_locations": ["义庄"],
            "core_factions": ["雁回镖局"],
            "canon_terms": ["雁回镇", "义庄"],
            "forbidden_public_spoilers": ["账册真凶"],
            "generation_notes": "测试分块流水线。",
        },
        "generator_finalize_characters": {
            "characters": [
                {
                    "name": "沈砚",
                    "aliases": ["沈镖师"],
                    "role": "protagonist",
                    "identity": "失忆镖师",
                    "description": "冷静、警觉，正在追查自己的过去。",
                    "appearance": "灰青劲装，左腕旧伤。",
                    "portrait_prompt": (
                        "Chinese wuxia courier, gray robe, old wrist scar, "
                        "restrained expression"
                    ),
                    "visibility": "visible",
                }
            ]
        },
        "generator_finalize_lore_entries": {
            "lore_entries": [
                {
                    "title": "义庄",
                    "type": "clue",
                    "keywords": ["义庄"],
                    "trigger_words": ["棺木", "账册"],
                    "priority": "critical",
                    "always_on": True,
                    "visibility": "mixed",
                    "public_info": "镇外旧义庄，近来夜里常有灯火。",
                    "gm_secret": "义庄暗藏旧案账册。",
                    "content": "义庄是第一幕核心地点，公开信息只表现异常，隐藏信息保留给 GM。",
                    "usage_note": "调查义庄时注入。",
                }
            ]
        },
        "generator_finalize_modes": {
            "modes": [
                {
                    "name": "调查模式",
                    "triggers": ["调查", "线索"],
                    "injection": "不要直接给出真相，提供可验证线索。",
                    "priority": "high",
                    "enabled": True,
                }
            ]
        },
        "generator_finalize_initial_state": {
            "initial_state": {
                "current_turn": "bad",
                "time": {"current": "秋末，申时", "pressure": "三日后封案"},
                "location": {"current": "雁回镇义庄", "known_locations": ["雁回镇"]},
                "protagonist": {"attributes": {"洞察": 2}},
                "progression": "bad",
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
        },
        "generator_finalize_rules": {
            "system_prompt": "你是 GM，每回合输出玩家可见剧情和 A/B/C/D 四个行动选项。",
            "generation_notes": "test",
            "voice_profiles": [],
        },
    }
    return payloads[task_type]


def sample_generated_config() -> dict:
    return {
        "title": "雁回镇旧案",
        "genre": "黑暗武侠",
        "description": "失忆镖师追查义庄旧案。",
        "system_prompt": "你是 GM，每回合生成剧情和 A/B/C/D 行动选项。",
        "worldview": {"tone": "冷峻"},
        "script_outline": {
            "title": "雁回镇旧案",
            "user_brief": {
                "story_background": "黑暗武侠，雁回镇义庄。",
                "core_premise": "失忆镖师追查义庄旧案。",
                "must_include": ["雨夜义庄"],
                "forbidden_content": ["不要修仙"],
                "playstyle_preferences": ["调查"],
                "tone_preferences": ["冷峻"],
                "raw_user_input": "黑暗武侠，主角是失忆镖师。",
            },
            "acts": [],
            "campaign_contract": {
                "player_fantasy": "失忆镖师追查义庄旧案。",
                "central_question": "旧案真相是什么？",
                "must_preserve": ["雨夜义庄"],
                "must_not_become": ["不要修仙"],
                "forbidden_drift": ["不要修仙"],
                "current_act": "act_1",
            },
            "truth_map": [],
            "clue_ladder": [],
            "pressure_clock": [],
        },
        "generation_notes": "test",
        "lore_entries": [
            {
                "title": "义庄",
                "type": "location",
                "keywords": ["义庄"],
                "trigger_words": ["尸体", "棺材"],
                "priority": "high",
                "always_on": True,
                "visibility": "mixed",
                "public_info": "镇外旧义庄。",
                "gm_secret": "义庄暗藏旧案账册。",
                "content": "义庄是第一章核心地点。",
                "usage_note": "调查时注入。",
            }
        ],
        "modes": [
            {
                "name": "调查模式",
                "triggers": ["调查", "搜索"],
                "injection": "不要直接给出真相，提供可验证线索。",
                "priority": "medium",
                "enabled": True,
            }
        ],
        "initial_state": {
            "current_turn": 0,
            "time": {"current": "秋末，申时", "pressure": "三日后封案"},
            "location": {"current": "雁回镇义庄", "known_locations": ["雁回镇"]},
            "protagonist": {"name": "未定", "identity": "失忆镖师"},
            "inventory": [],
            "quests": [],
            "npcs": [],
            "factions": [],
            "variables": {},
            "known_facts": [],
            "hidden_facts": [],
            "open_threads": [],
        },
    }
