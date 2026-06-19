from fastapi.testclient import TestClient

from app.main import app
from app.services.authoring_kit_exporter import AUTHORING_KIT_EXAMPLE
from app.services.story_settings import validate_story_settings
from tests.story_settings_fixtures import story_settings_payload


def test_import_script_returns_normalized_config() -> None:
    response = TestClient(app).post(
        "/api/generator/import-script",
        json=story_settings_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["model_used"] == "import"
    config = body["config"]
    assert config["title"] == "雁回镇旧案"
    assert config["genre"] == "黑暗武侠"
    assert config["story_settings"]["format_version"] == "rpgforge.story.v2"
    assert config["story_settings"]["story_core"]["main_goal"] == "查清义庄旧案。"


def test_import_script_rejects_invalid_story_settings() -> None:
    payload = story_settings_payload()
    # 制造重复角色名 → validate_story_settings 抛 ValueError
    payload["core_characters"][1]["name"] = payload["core_characters"][0]["name"]

    response = TestClient(app).post("/api/generator/import-script", json=payload)

    assert response.status_code == 400
    assert "重复" in response.json()["detail"]


def test_import_script_rejects_empty_or_garbage_payload() -> None:
    # 垃圾/空粘贴：normalize 会静默纠成「未命名游戏」空剧本，必须挡掉而不是建空游戏
    response = TestClient(app).post(
        "/api/generator/import-script",
        json={"foo": "bar", "format_version": "wrong"},
    )

    assert response.status_code == 400
    assert "空" in response.json()["detail"]


def test_import_script_accepts_settings_export_wrapper() -> None:
    # 兼容 settings-export 形态：外层包裹 + 内层 story_settings
    payload = {"title": "x", "story_settings": story_settings_payload()}

    response = TestClient(app).post("/api/generator/import-script", json=payload)

    assert response.status_code == 200
    assert response.json()["config"]["title"] == "雁回镇旧案"


def test_authoring_kit_returns_markdown() -> None:
    response = TestClient(app).get("/api/generator/authoring-kit")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    text = response.text
    assert len(text) > 500
    assert "story_settings" in text
    assert "rpgforge.story.v2" in text


def test_authoring_kit_example_is_importable() -> None:
    # 防腐：内嵌范例必须始终能过 validate，否则给 AI 的样板会失效
    story = validate_story_settings(AUTHORING_KIT_EXAMPLE)

    assert story["format_version"] == "rpgforge.story.v2"
    assert story["game_profile"]["title"]
