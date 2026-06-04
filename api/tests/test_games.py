import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.main import app
from app.models.character import Character
from app.models.game import Game
from app.models.generator_job import TurnJob
from app.models.setting_version import GameSettingVersion
from app.models.summary import Summary
from app.models.turn import Turn
from app.services.game_creator import create_game_from_config
from tests.story_settings_fixtures import build_generated_config, copied_story_settings


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
    assert created["config"]["story_settings"]["format_version"] == "rpgforge.story.v2"
    assert created["config"]["story_settings"]["game_profile"]["genre"] == "黑暗武侠"
    assert (
        created["config"]["story_settings"]["generation_parameters"][
            "narrative_target_min_chars"
        ]
        == 800
    )
    assert created["state"]["current_turn"] == 0
    assert created["state"]["state_json"]["story_progress"]["current_act"] == "act_1"
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

    response = TestClient(app).delete(f"/api/games/{game_id}")

    assert response.status_code == 204
    db_session.expire_all()
    assert db_session.get(Game, game_id) is None
    assert not portrait_path.exists()
    assert not portrait_dir.exists()


def test_delete_game_rejects_active_turn_job(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    db_session.add(
        TurnJob(
            game_id=game.id,
            status="running",
            request_json={"player_input": "我继续前进。"},
        )
    )
    db_session.commit()

    response = TestClient(app).delete(f"/api/games/{game.id}")

    assert response.status_code == 409
    assert db_session.get(Game, game.id) is not None


def test_game_memory_endpoint_exposes_summaries_without_legacy_lore(db_session) -> None:
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

    response = TestClient(app).get(f"/api/games/{game.id}/memory")

    assert response.status_code == 200
    body = response.json()
    assert body["game"]["id"] == str(game.id)
    assert "lore_entries" not in body
    assert "modes" not in body
    assert body["summaries"][0]["content"].startswith("长期记忆")


def test_export_game_script_contains_story_settings_without_play_history(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
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

    response = TestClient(app).get(f"/api/games/{game.id}/script-export")

    assert response.status_code == 200
    markdown = response.text
    assert "# 雁回镇旧案" in markdown
    assert "## 世界观" in markdown
    assert "## 故事核心" in markdown
    assert "## 五幕主线" in markdown
    assert "## 主线任务轨迹" in markdown
    assert "## 行动风格规则" in markdown
    assert "## 剧本素材库" in markdown
    assert "雁回镇义庄" in markdown
    assert "黑伞客陆沉舟" in markdown
    assert "## 生成参数" in markdown
    assert "我检查门槛" not in markdown
    assert "门槛内侧有新鲜泥痕。" not in markdown


def test_update_game_config_updates_story_settings_and_versions(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    updated = copied_story_settings()
    updated["game_profile"]["title"] = "雁回镇新案"
    updated["game_profile"]["genre"] = "诡秘武侠"
    updated["game_profile"]["description"] = "追查义庄背后的黑伞契约。"
    updated["story_core"]["main_goal"] = "查清黑伞契约真相"
    updated["generation_parameters"]["narrative_target_min_chars"] = 900
    updated["generation_parameters"]["recent_turn_excerpt_chars"] = 180

    response = TestClient(app).patch(
        f"/api/games/{game.id}/config",
        json={"story_settings_json": updated},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "雁回镇新案"
    assert body["genre"] == "诡秘武侠"
    assert (
        body["config"]["story_settings"]["generation_parameters"][
            "narrative_target_min_chars"
        ]
        == 900
    )
    versions = list(
        db_session.scalars(
            select(GameSettingVersion).where(GameSettingVersion.game_id == game.id)
        )
    )
    assert {version.action for version in versions} >= {"baseline", "updated"}


def test_setting_version_restore_restores_story_settings(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    client = TestClient(app)
    updated = copied_story_settings()
    updated["game_profile"]["title"] = "雁回镇新案"
    updated["story_core"]["main_goal"] = "查清黑伞契约真相"

    update_response = client.patch(
        f"/api/games/{game.id}/config",
        json={"story_settings": updated},
    )
    assert update_response.status_code == 200

    versions = client.get(f"/api/games/{game.id}/setting-versions").json()
    baseline = next(version for version in versions if version["action"] == "baseline")
    restore_response = client.post(
        f"/api/games/{game.id}/setting-versions/{baseline['id']}/restore"
    )

    assert restore_response.status_code == 200
    body = restore_response.json()
    assert body["title"] == "雁回镇旧案"
    assert body["config"]["story_settings"]["story_core"]["main_goal"] == "查清义庄旧案。"


def test_settings_export_import_overwrites_all_story_settings_and_characters(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    client = TestClient(app)
    export_response = client.get(f"/api/games/{game.id}/settings-export")
    payload = json.loads(export_response.text)
    payload["game_profile"]["title"] = "导入后的雁回镇"
    payload["game_profile"]["description"] = "用户完整修改后的剧本设定。"
    payload["story_core"]["main_goal"] = "按用户新设定追查红灯账册。"
    payload["story_core"]["must_preserve"] = ["红灯账册"]
    payload["core_characters"] = [
        {
            "id": "lin_qing",
            "name": "林青",
            "aliases": [],
            "role": "protagonist",
            "identity": "红灯账册保管人",
            "description": "新导入剧本的主角。",
            "appearance": "灰白斗篷，腰间藏有账册铜扣。",
            "portrait_prompt": "",
            "visibility": "visible",
            "dramatic_function": "新主线承载者",
            "desire": "找出账册主人",
            "fear": "账册牵连亲族",
            "leverage": "账册铜扣",
            "relationship_arc": "从逃避到正面追查",
            "public_limit": "不会开局说出账册来历",
        }
    ]
    payload["story_material_library"] = [
        {
            "id": "red_lamp_ledger",
            "title": "红灯账册",
            "type": "item",
            "keywords": ["红灯账册"],
            "triggers": ["账册", "红灯"],
            "priority": "critical",
            "always_on": True,
            "visibility": "mixed",
            "public_info": "一本带铜扣的旧账册。",
            "gm_secret": "账册记录新主线真相。",
            "content": "导入后 GM 必须按红灯账册推进新主线。",
            "usage": "玩家调查账册时召回。",
            "enabled": True,
        }
    ]

    import_response = client.post(f"/api/games/{game.id}/settings-import", json=payload)

    assert import_response.status_code == 200
    body = import_response.json()
    assert body["title"] == "导入后的雁回镇"
    assert body["config"]["story_settings"]["story_core"]["must_preserve"] == ["红灯账册"]
    assert body["config"]["story_settings"]["story_material_library"][0]["title"] == "红灯账册"
    db_session.expire_all()
    names = [character.name for character in db_session.scalars(select(Character)).all()]
    assert names == ["林青"]

    second_import_response = client.post(f"/api/games/{game.id}/settings-import", json=payload)
    assert second_import_response.status_code == 200
    db_session.expire_all()
    names_after_second_import = [
        character.name for character in db_session.scalars(select(Character)).all()
    ]
    assert names_after_second_import == ["林青"]

    reexport = json.loads(client.get(f"/api/games/{game.id}/settings-export").text)
    assert reexport["game_profile"]["title"] == "导入后的雁回镇"
    assert reexport["story_core"]["main_goal"] == "按用户新设定追查红灯账册。"
    assert reexport["story_material_library"][0]["id"] == "red_lamp_ledger"


def test_settings_guide_export_is_markdown_and_does_not_change_json_export(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    client = TestClient(app)

    guide_response = client.get(f"/api/games/{game.id}/settings-guide-export")
    json_response = client.get(f"/api/games/{game.id}/settings-export")

    assert guide_response.status_code == 200
    assert guide_response.headers["content-type"].startswith("text/markdown")
    assert "设定填写说明" in guide_response.text
    assert "给 AI 的修改指令模板" in guide_response.text
    assert "story_material_library[].gm_secret" in guide_response.text
    assert "completion_anchors[].completion_signal" in guide_response.text
    assert "导入生效范围：只覆盖剧本设定源" in guide_response.text

    exported_json = json.loads(json_response.text)
    assert exported_json["format_version"] == "rpgforge.story.v2"
    assert "_field_guide" not in exported_json
    assert "guide" not in exported_json


def test_settings_guide_documents_every_normalized_field(db_session) -> None:
    """护栏：story_settings 规范化产出的每个字段都必须在填写说明文档里有记录。

    防止 schema 加字段后 settings_guide_exporter 的硬编码字段表漏同步。
    """
    import re

    from app.services.settings_guide_exporter import export_settings_guide_markdown
    from app.services.story_settings import normalize_story_settings

    # 让所有数组都非空，使数组元素字段也参与规范化；
    # worldview / home_base 是自由透传容器，schema 不强制固定子键，置空避免污染。
    sample = normalize_story_settings(
        {
            "core_characters": [{}],
            "act_plan": [{"completion_anchors": [{}]}],
            "main_quest_path": [{}],
            "core_mechanics": [{}],
            "action_style_rules": [{}],
            "story_material_library": [{}],
            "worldview": {},
            "home_base": {},
        }
    )

    field_names: set[str] = set()

    def collect_keys(obj: object) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                field_names.add(key)
                collect_keys(value)
        elif isinstance(obj, list):
            for item in obj:
                collect_keys(item)

    collect_keys(sample)

    game = create_game_from_config(db_session, build_generated_config())
    markdown = export_settings_guide_markdown(game)

    missing = sorted(
        name
        for name in field_names
        if not re.search(rf"\b{re.escape(name)}\b", markdown)
    )
    assert not missing, f"填写说明缺少字段记录：{missing}"


def test_settings_import_validation_rejects_bad_payloads(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    client = TestClient(app)

    invalid_version = client.post(
        f"/api/games/{game.id}/settings-import",
        json={"format_version": "legacy"},
    )
    assert invalid_version.status_code == 400

    duplicate_anchor_payload = copied_story_settings()
    duplicate_anchor_payload["act_plan"][0]["completion_anchors"][1]["id"] = (
        "act_1_find_mud"
    )
    duplicate_anchor = client.post(
        f"/api/games/{game.id}/settings-import",
        json=duplicate_anchor_payload,
    )
    assert duplicate_anchor.status_code == 400
    assert "完成锚点 id 重复" in duplicate_anchor.json()["detail"]

    duplicate_character_payload = copied_story_settings()
    duplicate_character_payload["core_characters"][1]["name"] = (
        duplicate_character_payload["core_characters"][0]["name"]
    )
    duplicate_character = client.post(
        f"/api/games/{game.id}/settings-import",
        json=duplicate_character_payload,
    )
    assert duplicate_character.status_code == 400
    assert "core_characters[1].name 重复" in duplicate_character.json()["detail"]


def test_settings_import_rejects_active_turn_job(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    db_session.add(
        TurnJob(
            game_id=game.id,
            status="running",
            request_json={"player_input": "我继续前进。"},
        )
    )
    db_session.commit()

    response = TestClient(app).post(
        f"/api/games/{game.id}/settings-import",
        json=copied_story_settings(),
    )

    assert response.status_code == 409


def test_context_diagnostic_returns_runtime_story_and_materials(db_session) -> None:
    game = create_game_from_config(db_session, build_generated_config())
    db_session.add(
        Turn(
            game_id=game.id,
            turn_number=1,
            player_input="我调查义庄门槛的泥痕。",
            gm_output="门槛内侧有新鲜泥痕。",
            visible_summary="发现门槛泥痕。",
            hidden_summary=None,
            state_delta_json={},
            action_options_json=[],
            model_used="deepseek-v4-pro-test",
        )
    )
    db_session.commit()

    response = TestClient(app).get(f"/api/games/{game.id}/context-diagnostic")

    assert response.status_code == 200
    body = response.json()
    assert body["runtime_story"]["current_act"]["id"] == "act_1"
    assert body["selected_action_style"]["id"] == "investigation"
    assert "雁回镇义庄" in [item["title"] for item in body["related_story_materials"]]
