import json

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.main import app
from app.models.character import Character
from app.models.game import Game
from app.models.generator_job import TurnJob
from app.models.setting_version import GameSettingVersion
from app.models.summary import Summary
from app.models.turn import Turn
from app.services.game_creator import create_game_from_config
from app.services.lore_retriever import LoreRetriever
from app.services.mode_matcher import select_mode
from app.services.prompt_builder import PromptBuilder
from tests.test_gameplay import build_generated_config


def test_create_and_read_manual_game(reset_database) -> None:
    client = TestClient(app)

    create_response = client.post(
        "/api/games",
        json={
            "title": "雁回镇旧案",
            "genre": "黑暗武侠",
            "description": "失忆镖师追查义庄旧案。",
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["title"] == "雁回镇旧案"
    assert created["config"]["worldview"]["genre"] == "黑暗武侠"
    assert created["state"]["current_turn"] == 0
    assert created["state"]["state_json"]["progression"]["level"] == 1
    assert created["state"]["state_json"]["skills"] == []
    assert created["state"]["state_json"]["abilities"] == []
    assert created["state"]["state_json"]["conditions"] == []
    assert created["state"]["state_json"]["relationships"] == []
    assert created["state"]["state_json"]["v2"]["progression"]["next_level_xp"] == 100

    list_response = client.get("/api/games")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    detail_response = client.get(f"/api/games/{created['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == created["id"]


def test_delete_game_removes_game_data_and_portraits(db_session, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "portrait_storage_path", str(tmp_path))
    game = create_game_from_config(db_session, build_generated_config())
    game_id = game.id
    character = db_session.scalars(
        select(Character).where(Character.game_id == game_id)
    ).first()
    portrait_dir = tmp_path / str(game_id)
    portrait_dir.mkdir(parents=True)
    portrait_path = portrait_dir / f"{character.id}.png"
    portrait_path.write_bytes(b"portrait")
    character.portrait_path = str(portrait_path)
    character.portrait_mime_type = "image/png"
    db_session.add(character)
    db_session.commit()

    client = TestClient(app)
    response = client.delete(f"/api/games/{game_id}")

    assert response.status_code == 204
    db_session.expire_all()
    assert db_session.get(Game, game_id) is None
    assert not portrait_path.exists()
    assert not portrait_dir.exists()
    assert client.get(f"/api/games/{game_id}").status_code == 404


def test_delete_game_rejects_active_turn_job(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    job = TurnJob(
        game_id=game.id,
        status="running",
        request_json={"player_input": "我继续前进。"},
    )
    db_session.add(job)
    db_session.commit()

    client = TestClient(app)
    response = client.delete(f"/api/games/{game.id}")

    assert response.status_code == 409
    assert db_session.get(Game, game.id) is not None


def test_game_memory_endpoint_exposes_lore_and_summaries(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    db_session.add(
        Summary(
            game_id=game.id,
            type="long_term",
            range_start_turn=1,
            range_end_turn=1,
            content="长期记忆：义庄旧案与黑伞客有关。",
            important_facts={"known_facts": ["黑伞客"]},
        )
    )
    db_session.commit()
    client = TestClient(app)

    response = client.get(f"/api/games/{game.id}/memory")

    assert response.status_code == 200
    body = response.json()
    assert body["game"]["id"] == str(game.id)
    assert body["lore_entries"][0]["embedding_configured"] is True
    assert body["summaries"][0]["content"].startswith("长期记忆")


def test_export_game_script_contains_framework_without_play_history(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    db_session.add(
        Character(
            game_id=game.id,
            name="沈砚",
            role="protagonist",
            identity="失忆镖师",
            description="追查义庄旧案的主角。",
            appearance="眉骨锋利，旧伤横过左肩，常穿褪色短打。",
            aliases=["旧别名不应导出"],
            portrait_prompt="portrait prompt should not be exported",
        )
    )
    db_session.add(
        Turn(
            game_id=game.id,
            turn_number=1,
            player_input="我检查门槛。",
            gm_output="门槛内侧有新鲜泥痕。",
            visible_summary="门槛内侧有新鲜泥痕。",
            hidden_summary=None,
            state_delta_json={},
            action_options_json=[],
            model_used="deepseek-v4-pro-test",
        )
    )
    db_session.commit()
    client = TestClient(app)

    response = client.get(f"/api/games/{game.id}/script-export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "filename*=UTF-8''RPGForge-" in response.headers["content-disposition"]
    markdown = response.text
    assert "# 雁回镇旧案" in markdown
    assert "## 世界观" in markdown
    assert "## 创作简报与编剧蓝图" in markdown
    assert "核心悬念" in markdown
    assert "沈砚失忆前到底护送了什么" in markdown
    assert "线索阶梯" in markdown
    assert "压力时钟" in markdown
    assert "## 世界资料 / 世界书" in markdown
    assert "### 义庄" in markdown
    assert "义庄暗藏旧案账册" in markdown
    assert "## 模式注入 / 机制规则" in markdown
    assert "### 调查模式" in markdown
    assert "## 角色档案" in markdown
    assert "### 沈砚" in markdown
    assert "外貌描述：眉骨锋利" in markdown
    assert "我检查门槛" not in markdown
    assert "门槛内侧有新鲜泥痕" not in markdown
    assert "别名：旧别名不应导出" in markdown
    assert "portrait prompt should not be exported" not in markdown


def test_update_game_config_updates_runtime_contract_and_versions(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    client = TestClient(app)

    response = client.patch(
        f"/api/games/{game.id}/config",
        json={
            "title": "雁回镇新案",
            "genre": "诡秘武侠",
            "description": "追查义庄背后的黑伞契约。",
            "system_prompt": "保持克制，遵守 RPGForge 剧情 Markdown 契约。",
            "generation_notes": "玩家手动修订。",
            "worldview": {
                "summary": "黑伞契约正在侵蚀雁回镇。",
                "tone": "冷峻悬疑",
                "key_npcs": ["黑伞客陆沉舟"],
                "conflicts": ["义庄旧案与黑伞契约"],
            },
            "campaign_contract": {
                "main_goal": "查清黑伞契约真相",
                "current_act": "义庄调查",
                "forbidden_drift": ["不要提前进入终局门派战争"],
            },
            "story_contract": {
                "narrative_style": "细节密集的冷峻武侠",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "雁回镇新案"
    assert body["config"]["worldview"]["summary"] == "黑伞契约正在侵蚀雁回镇。"
    assert (
        body["config"]["script_outline"]["campaign_contract"]["main_goal"]
        == "查清黑伞契约真相"
    )

    versions = db_session.scalars(
        select(GameSettingVersion)
        .where(GameSettingVersion.game_id == game.id, GameSettingVersion.scope == "config")
        .order_by(GameSettingVersion.created_at.asc())
    ).all()
    assert [version.action for version in versions] == ["baseline", "updated"]

    db_session.expire_all()
    saved = db_session.scalars(
        select(Game)
        .options(
            selectinload(Game.config),
            selectinload(Game.lore_entries),
            selectinload(Game.modes),
        )
        .where(Game.id == game.id)
    ).one()
    messages = PromptBuilder().build_runtime_messages(
        game=saved,
        player_input="我继续检查义庄。",
        selected_mode=None,
        recent_turns=[],
        related_lore=[],
        summaries={},
    )
    runtime_payload = json.loads(messages[1]["content"])
    assert runtime_payload["worldview"]["tone"] == "冷峻悬疑"
    assert runtime_payload["campaign_contract"]["main_goal"] == "查清黑伞契约真相"

    restore_response = client.post(
        f"/api/games/{game.id}/setting-versions/{versions[0].id}/restore"
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["title"] == "雁回镇旧案"


def test_update_game_config_advanced_json_preserves_required_story_fields(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    script_outline = dict(game.config.script_outline)
    script_outline["_character_profiles"] = {"沈砚": {"desire": "查明义庄旧案"}}
    game.config.script_outline = script_outline
    db_session.add(game.config)
    db_session.commit()
    client = TestClient(app)

    invalid_response = client.patch(
        f"/api/games/{game.id}/config",
        json={"script_outline_json": []},
    )
    assert invalid_response.status_code == 400

    response = client.patch(
        f"/api/games/{game.id}/config",
        json={
            "worldview_json": {"summary": "手动修正后的雁回镇世界观。"},
            "script_outline_json": {
                "title": "手动修正蓝图",
                "campaign_contract": {"main_goal": "按线索查明义庄旧案"},
            },
        },
    )

    assert response.status_code == 200
    script = response.json()["config"]["script_outline"]
    assert script["title"] == "手动修正蓝图"
    assert script["user_brief"]["raw_user_input"] == "黑暗武侠，主角是失忆镖师。"
    assert script["_character_profiles"]["沈砚"]["desire"] == "查明义庄旧案"
    assert "雨夜义庄" in script["campaign_contract"]["must_preserve"]
    assert "不要修仙" in script["campaign_contract"]["must_not_become"]
    assert "不要修仙" in script["campaign_contract"]["forbidden_drift"]


def test_runtime_prompt_uses_token_optimized_context(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    long_output = "义庄里传来低声回响。" * 80
    turn = Turn(
        game_id=game.id,
        turn_number=1,
        player_input="我检查义庄。",
        gm_output=long_output,
        visible_summary="玩家检查义庄，发现门槛内侧有新鲜泥痕。",
        hidden_summary="泥痕来自后院。",
        state_delta_json={},
        action_options_json=[
            {"key": "A", "label": "追踪泥痕"},
            {"key": "B", "label": "检查后窗"},
            {"key": "C", "label": "询问老仆"},
            {"key": "D", "label": "守住大门"},
        ],
        model_used="deepseek-v4-pro-test",
    )
    db_session.add(turn)
    db_session.commit()
    db_session.expire_all()
    saved = db_session.scalars(
        select(Game)
        .options(
            selectinload(Game.config),
            selectinload(Game.state),
            selectinload(Game.lore_entries),
            selectinload(Game.modes),
        )
        .where(Game.id == game.id)
    ).one()

    messages = PromptBuilder().build_runtime_messages(
        game=saved,
        player_input="我沿着泥痕追到后院。",
        selected_mode=None,
        recent_turns=[turn],
        related_lore=[],
        summaries={},
    )
    runtime_payload = json.loads(messages[1]["content"])
    recent_turn = runtime_payload["recent_turns"][0]

    assert "current_state" not in runtime_payload
    assert "script_outline" not in runtime_payload
    assert runtime_payload["current_state_v2"]["version"] == 1
    assert runtime_payload["campaign_contract"]
    assert "gm_output" not in recent_turn
    assert recent_turn["gm_output_excerpt"].endswith("...")
    assert len(recent_turn["gm_output_excerpt"]) < len(long_output)
    assert recent_turn["visible_summary"] == "玩家检查义庄，发现门槛内侧有新鲜泥痕。"
    assert recent_turn["hidden_summary"] == "泥痕来自后院。"


def test_lore_create_update_archive_and_restore_affects_retrieval(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    client = TestClient(app)

    create_response = client.post(
        f"/api/games/{game.id}/memory/lore",
        json={
            "title": "银钥匙",
            "type": "item",
            "keywords": ["银钥匙"],
            "trigger_words": ["钥匙"],
            "priority": "high",
            "always_on": True,
            "visibility": "mixed",
            "public_info": "一枚刻有义庄暗纹的银钥匙。",
            "gm_secret": "银钥匙能打开义庄账房暗格。",
            "content": "银钥匙是义庄旧案的重要物证。",
            "usage_note": "玩家检查钥匙或账房时注入。",
        },
    )
    assert create_response.status_code == 201
    lore_id = create_response.json()["id"]

    update_response = client.patch(
        f"/api/games/{game.id}/memory/lore/{lore_id}",
        json={"content": "银钥匙能开启义庄后堂账房暗格。", "keywords": ["银钥匙", "账房"]},
    )
    assert update_response.status_code == 200
    assert update_response.json()["keywords"] == ["银钥匙", "账房"]

    archive_response = client.delete(f"/api/games/{game.id}/memory/lore/{lore_id}")
    assert archive_response.status_code == 200
    assert archive_response.json()["is_active"] is False

    memory_response = client.get(f"/api/games/{game.id}/memory")
    archived_entry = next(
        entry for entry in memory_response.json()["lore_entries"] if entry["id"] == lore_id
    )
    assert archived_entry["is_active"] is False

    db_session.expire_all()
    saved = db_session.scalars(
        select(Game)
        .options(
            selectinload(Game.config),
            selectinload(Game.state),
            selectinload(Game.lore_entries),
        )
        .where(Game.id == game.id)
    ).one()
    messages = PromptBuilder().build_runtime_messages(
        game=saved,
        player_input="我查看银钥匙。",
        selected_mode=None,
        recent_turns=[],
        related_lore=[],
        summaries={},
    )
    runtime_payload = json.loads(messages[1]["content"])
    assert "银钥匙" not in [entry["title"] for entry in runtime_payload["always_on_lore"]]
    retrieved_titles = [
        result.entry.title
        for result in LoreRetriever().retrieve(
            db=db_session,
            game=saved,
            player_input="我查看银钥匙和账房。",
            selected_mode=None,
            recent_turns=[],
        )
    ]
    assert "银钥匙" not in retrieved_titles

    version = db_session.scalars(
        select(GameSettingVersion)
        .where(
            GameSettingVersion.game_id == game.id,
            GameSettingVersion.scope == "lore",
            GameSettingVersion.action == "updated",
        )
        .limit(1)
    ).one()
    restore_response = client.post(f"/api/games/{game.id}/setting-versions/{version.id}/restore")
    assert restore_response.status_code == 200
    restored = client.get(f"/api/games/{game.id}/memory").json()["lore_entries"]
    assert next(entry for entry in restored if entry["id"] == lore_id)["is_active"] is True


def test_mode_create_update_and_disable_affects_mode_matching(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    client = TestClient(app)

    create_response = client.post(
        f"/api/games/{game.id}/modes",
        json={
            "name": "潜行模式",
            "triggers": ["潜入", "躲避"],
            "injection": "强调隐蔽、巡逻路线和暴露风险。",
            "priority": "high",
            "enabled": True,
        },
    )
    assert create_response.status_code == 201
    mode_id = create_response.json()["id"]

    db_session.expire_all()
    saved = db_session.scalars(
        select(Game).options(selectinload(Game.modes)).where(Game.id == game.id)
    ).one()
    assert select_mode("我潜入义庄后院。", saved.modes).name == "潜行模式"

    update_response = client.patch(
        f"/api/games/{game.id}/modes/{mode_id}",
        json={"enabled": False, "triggers": ["潜入"]},
    )
    assert update_response.status_code == 200
    assert update_response.json()["enabled"] is False

    db_session.expire_all()
    saved = db_session.scalars(
        select(Game).options(selectinload(Game.modes)).where(Game.id == game.id)
    ).one()
    assert select_mode("我潜入义庄后院。", saved.modes).name != "潜行模式"


def test_setting_edit_rejects_active_turn_job(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    db_session.add(
        TurnJob(
            game_id=game.id,
            status="running",
            request_json={"player_input": "我继续前进。"},
        )
    )
    db_session.commit()
    client = TestClient(app)

    response = client.patch(
        f"/api/games/{game.id}/config",
        json={"worldview": {"summary": "不应写入。"}},
    )

    assert response.status_code == 409


def test_rebuild_game_summaries_from_history(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    db_session.add_all(
        [
            Turn(
                game_id=game.id,
                turn_number=1,
                player_input="我检查门槛。",
                gm_output="门槛内侧有新鲜泥痕。",
                visible_summary="门槛内侧有新鲜泥痕。",
                hidden_summary="泥痕来自后院。",
                state_delta_json={},
                action_options_json=[],
                model_used="deepseek-v4-pro-test",
            ),
            Turn(
                game_id=game.id,
                turn_number=2,
                player_input="我沿着泥痕去后院。",
                gm_output="后院墙根有黑伞留下的水痕。",
                visible_summary="后院墙根有黑伞水痕。",
                hidden_summary=None,
                state_delta_json={},
                action_options_json=[],
                model_used="deepseek-v4-pro-test",
            ),
        ]
    )
    db_session.commit()
    client = TestClient(app)

    response = client.post(f"/api/games/{game.id}/memory/summaries/rebuild")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 4
    summary_types = {
        summary.type
        for summary in db_session.scalars(
            select(Summary).where(Summary.game_id == game.id)
        ).all()
    }
    assert {"turn", "chapter", "long_term"}.issubset(summary_types)


def test_reindex_game_lore_embeddings(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    for entry in game.lore_entries:
        entry.embedding = None
        db_session.add(entry)
    db_session.commit()
    client = TestClient(app)

    response = client.post(f"/api/games/{game.id}/memory/lore/reindex")

    assert response.status_code == 200
    assert response.json() == {"total": 2, "updated": 2}
    memory_response = client.get(f"/api/games/{game.id}/memory")
    assert all(entry["embedding_configured"] for entry in memory_response.json()["lore_entries"])


def test_context_diagnostic_for_turn(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    turn = Turn(
        game_id=game.id,
        turn_number=1,
        player_input="我追问雨夜的黑伞客。",
        gm_output="守庄老仆提到雨夜曾有黑伞客靠近义庄。",
        visible_summary="雨夜黑伞客靠近义庄。",
        hidden_summary=None,
        state_delta_json={},
        action_options_json=[],
        model_used="deepseek-v4-pro-test",
    )
    db_session.add(turn)
    db_session.commit()
    client = TestClient(app)

    response = client.get(f"/api/games/{game.id}/context-diagnostic?turn_id={turn.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["turn_number"] == 1
    assert body["campaign_contract"]["central_question"] == "沈砚失忆前到底护送了什么？"
    assert body["story_blueprint"]["current_act"]["id"] == "act_1"
    assert body["story_blueprint"]["current_act"]["forbidden_reveals"] == ["账册真凶"]
    assert body["always_on_lore"][0]["title"] == "义庄"
    assert "黑伞客陆沉舟" in [entry["title"] for entry in body["related_lore"]]
