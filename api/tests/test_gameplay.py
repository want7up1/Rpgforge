import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.main import app
from app.models.generator_job import TurnJob
from app.models.state_delta import StateDelta
from app.models.summary import Summary
from app.models.turn import Turn
from app.schemas.generator import GeneratedGameConfig, GeneratedLoreEntry, GeneratedMode
from app.schemas.turn import TurnCreate
from app.services.deepseek_client import ChatCompletionResult, ChatCompletionStreamChunk
from app.services.game_creator import create_game_from_config
from app.services.gameplay import GameplayService
from app.services.lore_retriever import LoreRetriever
from app.services.mode_matcher import select_mode
from app.services.state_applier import apply_state_delta
from app.services.turn_jobs import extract_partial_json_string_field, run_turn_job


@dataclass
class FakeRouter:
    pro_messages: list[list[dict[str, str]]] = field(default_factory=list)

    async def use_pro(self, *args, **kwargs) -> ChatCompletionResult:
        self.pro_messages.append(args[1])
        return ChatCompletionResult(
            model="deepseek-v4-pro-test",
            raw={},
            content="""
            {
              "narrative": "义庄的门轴发出一声干涩低响，冷风卷起纸钱。",
              "visible_clues": ["门槛内侧有新鲜泥痕"],
              "action_options": [
                {"key": "A", "label": "检查门槛内侧的新鲜泥痕"},
                {"key": "B", "label": "绕到义庄后窗观察是否有人离开"},
                {"key": "C", "label": "点亮火折子查看棺木周围的痕迹"},
                {"key": "D", "label": "暂时退出义庄，在院外守候可疑动静"}
              ]
            }
            """,
        )

    async def use_pro_stream(self, *args, **kwargs):
        yield ChatCompletionStreamChunk(
            reasoning_delta="判断玩家行动并铺设线索。",
            model="deepseek-v4-pro-test",
        )
        yield ChatCompletionStreamChunk(
            model="deepseek-v4-pro-test",
            content_delta="""
            {
              "narrative": "义庄门槛内侧的泥痕尚未干透，像是有人刚从后院翻入。",
              "visible_clues": ["泥痕通向后院"],
              "action_options": [
                {"key": "A", "label": "沿着泥痕追到后院"},
                {"key": "B", "label": "检查门槛旁是否有其他脚印"},
                {"key": "C", "label": "询问守庄老仆昨夜是否听见动静"},
                {"key": "D", "label": "先关上义庄大门防止外人进入"}
              ]
            }
            """,
        )

    async def use_flash(self, *args, **kwargs) -> ChatCompletionResult:
        return ChatCompletionResult(
            model="deepseek-v4-flash-test",
            raw={},
            content="""
            {
              "time_delta": "半刻钟",
              "time_current": "秋末，申时二刻",
              "location_change": "雁回镇义庄内堂",
              "inventory_add": ["赤铜鱼符"],
              "inventory_remove": [],
              "npc_updates": [{"name": "守庄老仆", "attitude": "回避"}],
              "quest_updates": [{"name": "义庄旧案", "status": "发现新线索"}],
              "faction_updates": [],
              "protagonist_updates": {"mind": "警觉"},
              "variable_updates": {"mud_trace_found": true},
              "new_lore_candidates": [],
              "new_known_facts": ["门槛内侧有新鲜泥痕"],
              "new_hidden_facts": [],
              "open_thread_updates": ["确认泥痕来源"],
              "xp_events": [
                {
                  "category": "discovery",
                  "difficulty": "normal",
                  "significance": "standard",
                  "reason": "发现门槛内侧的新鲜泥痕"
                }
              ],
              "skill_events": [
                {
                  "skill": "调查",
                  "difficulty": "normal",
                  "outcome": "success",
                  "reason": "检查门槛并识别泥痕"
                }
              ],
              "ability_updates": [],
              "condition_updates": [
                {
                  "name": "警觉",
                  "status": "active",
                  "severity": "low",
                  "source": "义庄异常痕迹"
                }
              ],
              "relationship_events": [
                {
                  "npc": "守庄老仆",
                  "axis": "trust",
                  "direction": "decrease",
                  "intensity": "minor",
                  "reason": "对方回避关键问题"
                }
              ]
            }
            """,
        )


def build_generated_config() -> GeneratedGameConfig:
    return GeneratedGameConfig(
        title="雁回镇旧案",
        genre="黑暗武侠",
        description="失忆镖师追查义庄旧案。",
        system_prompt="你是 GM，每回合生成剧情和 A/B/C/D 行动选项。",
        worldview={"tone": "冷峻"},
        script_outline={"title": "雁回镇旧案", "acts": []},
        generation_notes="test",
        lore_entries=[
            GeneratedLoreEntry(
                title="义庄",
                type="location",
                keywords=["义庄"],
                trigger_words=["尸体", "棺材"],
                priority="high",
                always_on=True,
                visibility="mixed",
                public_info="镇外旧义庄。",
                gm_secret="义庄暗藏旧案账册。",
                content="义庄是第一章核心地点。",
                usage_note="调查时注入。",
            ),
            GeneratedLoreEntry(
                title="黑伞客陆沉舟",
                type="npc",
                keywords=["黑伞客", "陆沉舟", "黑伞"],
                trigger_words=["黑伞", "雨夜", "陆沉舟"],
                priority="high",
                always_on=False,
                visibility="mixed",
                public_info="常持黑伞的外乡人。",
                gm_secret="陆沉舟知道义庄旧案账册的下落。",
                content="黑伞客陆沉舟与义庄旧案有关，会在雨夜接近旧义庄。",
                usage_note="玩家提到黑伞、陆沉舟或雨夜时注入。",
            )
        ],
        modes=[
            GeneratedMode(
                name="调查模式",
                triggers=["调查", "检查"],
                injection="不要直接给出真相，提供可验证线索。",
                priority="medium",
                enabled=True,
            )
        ],
        initial_state={
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
    )


def test_create_turn_requires_deepseek_api_key(monkeypatch, db_session) -> None:
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    game = create_game_from_config(db_session, build_generated_config())
    client = TestClient(app)

    response = client.post(
        f"/api/games/{game.id}/turns",
        json={"player_input": "我检查门槛。"},
    )

    assert response.status_code == 503
    assert "DEEPSEEK_API_KEY" in response.json()["detail"]


def test_gameplay_service_creates_turn(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    service = GameplayService(router=FakeRouter())

    import asyncio

    turn = asyncio.run(
        service.run_turn(db_session, game, TurnCreate(player_input="我检查门槛。"))
    )

    assert turn.turn_number == 1
    assert turn.model_used == "deepseek-v4-pro-test"
    assert turn.action_options_json[0]["key"] == "A"
    assert "义庄" in turn.gm_output
    assert turn.state_delta_json["time_delta"] == "半刻钟"
    assert turn.hidden_summary is not None

    delta = db_session.scalar(select(StateDelta).where(StateDelta.turn_id == turn.id))
    assert delta is not None
    assert delta.status == "approved"
    assert delta.approved_at is not None
    assert delta.delta_json["inventory_add"] == ["赤铜鱼符"]
    db_session.refresh(game.state)
    assert game.state.current_turn == 1
    assert game.state.state_json["variables"]["mud_trace_found"] is True
    state_v2 = game.state.state_json["v2"]
    assert state_v2["active_scene"]["location"] == "雁回镇义庄内堂"
    assert state_v2["quest_log"]["active"][0]["name"] == "义庄旧案"
    assert state_v2["progression"]["total_xp"] == 18
    assert state_v2["skills"][0]["name"] == "调查"
    assert state_v2["skills"][0]["xp"] == 10
    assert state_v2["conditions"][0]["name"] == "警觉"
    assert state_v2["relationship_tracks"][0]["npc"] == "守庄老仆"
    assert state_v2["relationship_tracks"][0]["recent_events"][0]["change"] == -3
    assert game.state.summary
    summaries = list(db_session.scalars(select(Summary).where(Summary.game_id == game.id)).all())
    assert {summary.type for summary in summaries} == {"turn", "chapter", "long_term"}


def test_quantified_state_shows_abilities_only_when_present(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    assert game.state.state_json["v2"]["abilities"] == []

    turn = Turn(
        game_id=game.id,
        turn_number=1,
        player_input="我尝试调动光元素。",
        gm_output="掌心浮现微弱光芒。",
        visible_summary="主角觉醒了微弱光元素。",
        state_delta_json={},
        action_options_json=[],
        model_used="deepseek-v4-pro-test",
    )
    state_json = apply_state_delta(
        game.state,
        turn,
        {
            "ability_updates": [
                {
                    "name": "光元素掌控",
                    "visibility": "known",
                    "description": "凝聚微弱光芒，用于照明和净化轻微污染。",
                    "status": "active",
                }
            ],
            "skill_events": [
                {
                    "skill": "光元素掌控",
                    "difficulty": "hard",
                    "outcome": "success",
                    "reason": "首次主动调动光元素",
                }
            ],
        },
    )

    assert state_json["v2"]["abilities"][0]["name"] == "光元素掌控"
    assert state_json["v2"]["skills"][0]["name"] == "光元素掌控"
    assert state_json["v2"]["skills"][0]["xp"] == 15


def test_prompt_injects_related_lore_and_memory_summary(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    db_session.add(
        Summary(
            game_id=game.id,
            type="long_term",
            range_start_turn=1,
            range_end_turn=1,
            content="长期记忆：义庄旧案与雨夜黑伞有关。",
            important_facts={"known_facts": ["雨夜黑伞"]},
        )
    )
    db_session.commit()
    router = FakeRouter()
    service = GameplayService(router=router)

    import asyncio

    asyncio.run(
        service.run_turn(db_session, game, TurnCreate(player_input="我追问雨夜的黑伞客。"))
    )

    runtime_payload = json.loads(router.pro_messages[0][1]["content"])
    related_titles = [entry["title"] for entry in runtime_payload["related_lore"]]
    always_on_titles = [entry["title"] for entry in runtime_payload["always_on_lore"]]

    assert "义庄" in always_on_titles
    assert "黑伞客陆沉舟" in related_titles
    assert runtime_payload["memory_summaries"]["long_term"]["content"].startswith("长期记忆")
    assert runtime_payload["campaign_contract"]["source"] == "derived_from_script_outline"


def test_prompt_injects_explicit_campaign_contract(db_session) -> None:
    config = build_generated_config().model_copy(deep=True)
    config.script_outline = {
        "title": "雁回镇旧案",
        "acts": [],
        "campaign_contract": {
            "premise": "玩家想体验按线索追查义庄旧案，而不是立刻扩展成江湖大战。",
            "current_act": "act_1",
            "forbidden_drift": ["不要提前引入终局门派战争"],
        },
    }
    game = create_game_from_config(db_session, config)
    router = FakeRouter()
    service = GameplayService(router=router)

    import asyncio

    asyncio.run(service.run_turn(db_session, game, TurnCreate(player_input="我检查门槛。")))

    runtime_payload = json.loads(router.pro_messages[0][1]["content"])

    assert runtime_payload["campaign_contract"]["current_act"] == "act_1"
    assert "终局门派战争" in runtime_payload["campaign_contract"]["forbidden_drift"][0]
    assert runtime_payload["current_state_v2"]["version"] == 1


def test_story_director_decision_is_injected_into_runtime_prompt(db_session) -> None:
    class DirectorRouter(FakeRouter):
        async def use_flash(self, task_type, messages, **kwargs) -> ChatCompletionResult:
            if task_type == "story_director":
                return ChatCompletionResult(
                    model="deepseek-v4-flash-test",
                    raw={},
                    content="""
                    {
                      "player_intent": "检查义庄门槛",
                      "current_act": "act_1",
                      "scene_objective": "确认泥痕来源，不提前揭露旧案真相",
                      "mode_recommendation": "调查模式",
                      "active_lore_titles": ["义庄"],
                      "allowed_reveals": ["门槛泥痕来自后院方向"],
                      "forbidden_reveals": ["不要直接揭露账册主人"],
                      "pacing_limit": "只推进局部调查压力",
                      "continuity_notes": ["地点仍在雁回镇义庄"],
                      "gm_instruction": "先回应检查门槛的直接结果。"
                    }
                    """,
                )
            if task_type == "drift_validator":
                return ChatCompletionResult(
                    model="deepseek-v4-flash-test",
                    raw={},
                    content='{"approved": true, "severity": "none"}',
                )
            return await super().use_flash(task_type, messages, **kwargs)

    game = create_game_from_config(db_session, build_generated_config())
    router = DirectorRouter()
    service = GameplayService(router=router)

    import asyncio

    asyncio.run(service.run_turn(db_session, game, TurnCreate(player_input="我检查门槛。")))

    runtime_payload = json.loads(router.pro_messages[0][1]["content"])

    assert runtime_payload["story_director"]["current_act"] == "act_1"
    assert runtime_payload["story_director"]["mode_recommendation"] == "调查模式"
    assert "账册主人" in runtime_payload["story_director"]["forbidden_reveals"][0]


def test_drift_validator_rewrites_major_deviation(db_session) -> None:
    class RewriteRouter(FakeRouter):
        def __init__(self) -> None:
            super().__init__()
            self.pro_calls = 0

        async def use_pro(self, task_type, messages, **kwargs) -> ChatCompletionResult:
            self.pro_calls += 1
            self.pro_messages.append(messages)
            if task_type == "gm_runtime_rewrite":
                content = """
                {
                  "narrative": "义庄门槛内侧的泥痕被灯火照亮，痕迹一路拖向后院。",
                  "visible_clues": ["泥痕通向后院"],
                  "action_options": [
                    {"key": "A", "label": "沿泥痕去后院"},
                    {"key": "B", "label": "检查泥痕深浅"},
                    {"key": "C", "label": "询问守庄老仆"},
                    {"key": "D", "label": "封住义庄大门"}
                  ]
                }
                """
            else:
                content = """
                {
                  "narrative": "义庄外突然爆发终局门派战争，旧案真相被当场揭露。",
                  "visible_clues": ["终局门派战争爆发"],
                  "action_options": [
                    {"key": "A", "label": "加入门派大战"},
                    {"key": "B", "label": "追问终局真相"},
                    {"key": "C", "label": "寻找幕后掌门"},
                    {"key": "D", "label": "离开雁回镇"}
                  ]
                }
                """
            return ChatCompletionResult(
                model="deepseek-v4-pro-test",
                raw={},
                content=content,
            )

        async def use_flash(self, task_type, messages, **kwargs) -> ChatCompletionResult:
            if task_type == "story_director":
                return ChatCompletionResult(
                    model="deepseek-v4-flash-test",
                    raw={},
                    content="""
                    {
                      "player_intent": "检查门槛",
                      "current_act": "act_1",
                      "scene_objective": "局部调查泥痕",
                      "mode_recommendation": "调查模式",
                      "forbidden_reveals": ["不要引入终局门派战争"],
                      "pacing_limit": "不升级到全局冲突",
                      "gm_instruction": "先解决检查门槛的直接结果。"
                    }
                    """,
                )
            if task_type == "drift_validator":
                return ChatCompletionResult(
                    model="deepseek-v4-flash-test",
                    raw={},
                    content="""
                    {
                      "approved": false,
                      "severity": "major",
                      "issues": ["跳过玩家检查门槛的直接结果"],
                      "contract_violations": ["提前引入终局门派战争"],
                      "state_conflicts": [],
                      "rewrite_instruction": "重写为局部调查泥痕，不要引入终局门派战争。"
                    }
                    """,
                )
            return await super().use_flash(task_type, messages, **kwargs)

    game = create_game_from_config(db_session, build_generated_config())
    router = RewriteRouter()
    service = GameplayService(router=router)

    import asyncio

    turn = asyncio.run(service.run_turn(db_session, game, TurnCreate(player_input="我检查门槛。")))

    assert router.pro_calls == 2
    assert "泥痕" in turn.gm_output
    assert "终局门派战争" not in turn.gm_output
    rewrite_payload = json.loads(router.pro_messages[1][1]["content"])
    assert "局部调查泥痕" in rewrite_payload["drift_rewrite_instruction"]


def test_mode_matcher_uses_implied_investigation_triggers(db_session) -> None:
    config = build_generated_config().model_copy(deep=True)
    config.modes = [
        GeneratedMode(
            name="主线模式",
            triggers=["主线"],
            injection="推进主线压力。",
            priority="high",
            enabled=True,
        ),
        GeneratedMode(
            name="调查模式",
            triggers=["调查"],
            injection="不要直接给出真相，提供可验证线索。",
            priority="medium",
            enabled=True,
        ),
    ]
    game = create_game_from_config(db_session, config)

    selected = select_mode("我探查后院隐藏区域。", game.modes)

    assert selected is not None
    assert selected.name == "调查模式"


def test_lore_retrieval_ignores_generic_content_matches(db_session) -> None:
    config = GeneratedGameConfig(
        title="检索测试",
        genre="奇幻",
        description="营地附近的局部冒险。",
        system_prompt="你是 GM，每回合生成剧情和 A/B/C/D 行动选项。",
        worldview={"tone": "克制"},
        script_outline={"title": "检索测试", "acts": []},
        generation_notes="test",
        lore_entries=[
            GeneratedLoreEntry(
                title="银钥匙",
                type="item",
                keywords=["银钥匙"],
                trigger_words=["钥匙"],
                priority="high",
                always_on=False,
                visibility="mixed",
                content="银钥匙能打开营地北侧的旧门。",
            ),
            GeneratedLoreEntry(
                title="古老王城",
                type="location",
                keywords=["王城"],
                trigger_words=["王城"],
                priority="high",
                always_on=False,
                visibility="mixed",
                content="玩家作为一个角色可以继续当前任务，观察周围风险和目标。",
            ),
        ],
        modes=[
            GeneratedMode(
                name="主线模式",
                triggers=["主线"],
                injection="推进主线压力。",
                priority="medium",
                enabled=True,
            )
        ],
        initial_state={
            "current_turn": 0,
            "time": {"current": "清晨"},
            "location": {"current": "临时营地", "known_locations": ["临时营地"]},
            "protagonist": {"name": "旅人", "identity": "调查者"},
            "inventory": [],
            "quests": [],
            "npcs": [],
            "factions": [],
            "variables": {},
            "known_facts": [],
            "hidden_facts": [],
            "open_threads": [],
        },
    )
    game = create_game_from_config(db_session, config)
    retriever = LoreRetriever()

    generic_results = retriever.retrieve(
        db=db_session,
        game=game,
        player_input="我继续当前任务，观察周围风险。",
        selected_mode=None,
        recent_turns=[],
    )
    specific_results = retriever.retrieve(
        db=db_session,
        game=game,
        player_input="我检查银钥匙。",
        selected_mode=None,
        recent_turns=[],
    )

    assert "古老王城" not in [result.entry.title for result in generic_results]
    assert "银钥匙" in [result.entry.title for result in specific_results]


def test_gameplay_service_streams_turn(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    service = GameplayService(router=FakeRouter())
    updates: list[tuple[str, str, str | None]] = []

    async def run_stream():
        async def on_update(reasoning: str, content: str, model: str | None) -> None:
            updates.append((reasoning, content, model))

        return await service.run_turn_stream(
            db_session,
            game,
            TurnCreate(player_input="我检查门槛。"),
            on_update=on_update,
        )

    import asyncio

    turn = asyncio.run(run_stream())

    assert turn.turn_number == 1
    assert "泥痕" in turn.gm_output
    assert turn.model_used == "deepseek-v4-pro-test"
    assert updates[0] == ("判断玩家行动并铺设线索。", "", "deepseek-v4-pro-test")
    assert '"narrative"' in updates[-1][1]


def test_turn_job_lifecycle(reset_database, monkeypatch) -> None:
    async def fake_run_turn_job(job_id):
        del job_id

    monkeypatch.setattr("app.routers.gameplay.run_turn_job", fake_run_turn_job)
    client = TestClient(app)
    create_response = client.post(
        "/api/generator/create-game",
        json={"generated_config": build_generated_config().model_dump()},
    )
    game_id = create_response.json()["game"]["id"]

    response = client.post(
        f"/api/games/{game_id}/turns/jobs",
        json={"player_input": "我检查门槛。"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "pending"

    read_response = client.get(f"/api/games/{game_id}/turns/jobs/{payload['id']}")

    assert read_response.status_code == 200
    body = read_response.json()
    assert body["status"] == "pending"
    assert body["turn"] is None
    assert body["reasoning_content"] == ""
    assert body["narrative_buffer"] == ""


def test_turn_job_persists_stream_progress(db_session, monkeypatch) -> None:
    game = create_game_from_config(db_session, build_generated_config())

    class StreamingGameplayService:
        async def run_turn_stream(
            self,
            db,
            loaded_game,
            payload,
            on_update=None,
            on_progress=None,
            extract_state=True,
        ):
            del loaded_game, on_progress, extract_state
            if on_update:
                await on_update(
                    "判断自由行动并铺设线索。",
                    '{"narrative":"义庄门槛内侧的泥痕尚未干透。"',
                    "deepseek-v4-pro-test",
                )

            turn = Turn(
                game_id=game.id,
                turn_number=1,
                player_input=payload.player_input,
                gm_output="义庄门槛内侧的泥痕尚未干透。",
                visible_summary="泥痕通向后院",
                hidden_summary=None,
                state_delta_json={},
                action_options_json=[
                    {"key": "A", "label": "沿着泥痕追到后院"},
                    {"key": "B", "label": "检查其他脚印"},
                    {"key": "C", "label": "询问守庄老仆"},
                    {"key": "D", "label": "先关上义庄大门"},
                ],
                model_used="deepseek-v4-pro-test",
            )
            db.add(turn)
            db.commit()
            db.refresh(turn)
            return turn

        async def _create_state_delta(self, db, loaded_game, turn) -> None:
            del db, loaded_game, turn

    job = TurnJob(
        game_id=game.id,
        status="pending",
        request_json={"player_input": "我自由行动，检查门槛。"},
    )
    db_session.add(job)
    db_session.commit()

    monkeypatch.setattr("app.services.turn_jobs.GameplayService", StreamingGameplayService)

    import asyncio

    asyncio.run(run_turn_job(job.id))

    db_session.expire_all()
    saved = db_session.get(TurnJob, job.id)
    assert saved.status == "completed"
    assert saved.reasoning_content == "判断自由行动并铺设线索。"
    assert saved.content_buffer == '{"narrative":"义庄门槛内侧的泥痕尚未干透。"'
    assert saved.narrative_buffer == "义庄门槛内侧的泥痕尚未干透。"
    assert saved.error_message is None


def test_turn_job_events_returns_terminal_snapshot(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    turn = Turn(
        game_id=game.id,
        turn_number=1,
        player_input="我检查门槛。",
        gm_output="义庄门槛内侧的泥痕尚未干透。",
        visible_summary="泥痕通向后院",
        hidden_summary=None,
        state_delta_json={},
        action_options_json=[
            {"key": "A", "label": "沿着泥痕追到后院"},
            {"key": "B", "label": "检查其他脚印"},
            {"key": "C", "label": "询问守庄老仆"},
            {"key": "D", "label": "先关上义庄大门"},
        ],
        model_used="deepseek-v4-pro-test",
    )
    db_session.add(turn)
    db_session.commit()
    db_session.refresh(turn)

    now = datetime.now(UTC)
    job = TurnJob(
        game_id=game.id,
        status="completed",
        request_json={"player_input": "我检查门槛。"},
        turn_id=turn.id,
        model_used=turn.model_used,
        reasoning_content="判断玩家行动。",
        content_buffer='{"narrative":"义庄门槛内侧的泥痕尚未干透。"}',
        narrative_buffer=turn.gm_output,
        progress_message="剧情已生成，状态变更已写入。",
        stream_started_at=now,
        last_event_at=now,
        completed_at=now,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    client = TestClient(app)
    with client.stream("GET", f"/api/games/{game.id}/turns/jobs/{job.id}/events") as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: snapshot" in body
    assert '"terminal": true' in body
    assert "义庄门槛内侧的泥痕尚未干透" in body


def test_extract_partial_narrative_from_streaming_json() -> None:
    content = (
        '{"narrative":"义庄门轴发出干涩低响，\\n纸钱被风卷起。",'
        '"visible_clues":["门槛有泥痕"]'
    )

    assert (
        extract_partial_json_string_field(content, "narrative")
        == "义庄门轴发出干涩低响，\n纸钱被风卷起。"
    )


def test_extract_partial_narrative_waits_for_string_value() -> None:
    assert extract_partial_json_string_field('{"narrative"', "narrative") == ""
    assert extract_partial_json_string_field('{"narrative":', "narrative") == ""


def test_list_turns(reset_database) -> None:
    client = TestClient(app)
    create_response = client.post(
        "/api/generator/create-game",
        json={"generated_config": build_generated_config().model_dump()},
    )
    game_id = create_response.json()["game"]["id"]

    list_response = client.get(f"/api/games/{game_id}/turns")

    assert list_response.status_code == 200
    assert list_response.json() == []


def create_pending_state_delta(db_session) -> tuple[str, str]:
    game = create_game_from_config(db_session, build_generated_config())
    turn = Turn(
        game_id=game.id,
        turn_number=1,
        player_input="我检查门槛。",
        gm_output="义庄内堂的灰尘被人踩开，木案下露出一枚赤铜鱼符。",
        visible_summary="木案下有赤铜鱼符。",
        hidden_summary=None,
        state_delta_json={},
        action_options_json=[],
        model_used="deepseek-v4-pro-test",
    )
    db_session.add(turn)
    db_session.commit()
    db_session.refresh(turn)

    delta = StateDelta(
        game_id=game.id,
        turn_id=turn.id,
        delta_json={
            "time_delta": "半刻钟",
            "time_current": "秋末，申时二刻",
            "location_change": "雁回镇义庄内堂",
            "inventory_add": ["赤铜鱼符"],
            "inventory_remove": [],
            "npc_updates": [{"name": "守庄老仆", "attitude": "回避"}],
            "quest_updates": [{"name": "义庄旧案", "status": "发现新线索"}],
            "faction_updates": [],
            "protagonist_updates": {"mind": "警觉"},
            "variable_updates": {"mud_trace_found": True},
            "new_lore_candidates": [],
            "new_known_facts": ["门槛内侧有新鲜泥痕"],
            "new_hidden_facts": [],
            "open_thread_updates": ["确认泥痕来源"],
        },
        status="pending",
    )
    db_session.add(delta)
    db_session.commit()
    db_session.refresh(delta)
    return str(game.id), str(delta.id)


def test_approve_state_delta_applies_state(db_session) -> None:
    game_id, delta_id = create_pending_state_delta(db_session)
    client = TestClient(app)

    response = client.post(f"/api/games/{game_id}/state-deltas/{delta_id}/approve")

    assert response.status_code == 200
    state_json = response.json()["state_json"]
    assert state_json["current_turn"] == 1
    assert state_json["time"]["current"] == "秋末，申时二刻"
    assert state_json["location"]["current"] == "雁回镇义庄内堂"
    assert "赤铜鱼符" in state_json["inventory"]
    assert state_json["variables"]["mud_trace_found"] is True

    deltas_response = client.get(f"/api/games/{game_id}/state-deltas")
    assert deltas_response.status_code == 200
    assert deltas_response.json()[0]["status"] == "approved"


def test_get_game_auto_applies_pending_state_delta(db_session) -> None:
    game_id, _delta_id = create_pending_state_delta(db_session)
    client = TestClient(app)

    response = client.get(f"/api/games/{game_id}")

    assert response.status_code == 200
    state_json = response.json()["state"]["state_json"]
    assert state_json["variables"]["mud_trace_found"] is True

    deltas_response = client.get(f"/api/games/{game_id}/state-deltas")
    assert deltas_response.status_code == 200
    assert deltas_response.json()[0]["status"] == "approved"


def test_update_state_delta_then_approve_applies_edited_json(db_session) -> None:
    game_id, delta_id = create_pending_state_delta(db_session)
    client = TestClient(app)

    update_response = client.patch(
        f"/api/games/{game_id}/state-deltas/{delta_id}",
        json={
            "delta_json": {
                "time_delta": None,
                "time_current": None,
                "location_change": None,
                "inventory_add": ["黑漆木牌"],
                "inventory_remove": [],
                "npc_updates": [],
                "quest_updates": [],
                "faction_updates": [],
                "protagonist_updates": {},
                "variable_updates": {"edited_delta": True},
                "new_lore_candidates": [],
                "new_known_facts": [],
                "new_hidden_facts": [],
                "open_thread_updates": [],
            }
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "edited"

    approve_response = client.post(f"/api/games/{game_id}/state-deltas/{delta_id}/approve")

    assert approve_response.status_code == 200
    state_json = approve_response.json()["state_json"]
    assert state_json["inventory"] == ["黑漆木牌"]
    assert state_json["variables"]["edited_delta"] is True


def test_reject_state_delta_marks_rejected(db_session) -> None:
    game_id, delta_id = create_pending_state_delta(db_session)
    client = TestClient(app)

    response = client.post(f"/api/games/{game_id}/state-deltas/{delta_id}/reject")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
