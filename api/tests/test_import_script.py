import json
import re
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.authoring_kit_exporter import (
    AUTHORING_KIT_EXAMPLE,
    export_authoring_kit_markdown,
)
from app.services.generation_parameters import DEFAULT_GENERATION_PARAMETERS
from app.services.state_applier import apply_state_delta
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


def test_import_script_rejects_title_only_shell() -> None:
    response = TestClient(app).post(
        "/api/generator/import-script",
        json={"game_profile": {"title": "只有标题"}},
    )

    assert response.status_code == 400
    assert "至少" in response.json()["detail"]


def test_import_script_accepts_settings_export_wrapper() -> None:
    # 兼容 settings-export 形态：外层包裹 + 内层 story_settings
    payload = {"title": "x", "story_settings": story_settings_payload()}

    response = TestClient(app).post("/api/generator/import-script", json=payload)

    assert response.status_code == 200
    assert response.json()["config"]["title"] == "雁回镇旧案"


def test_import_script_warns_when_act_lacks_required_anchor() -> None:
    payload = story_settings_payload()
    payload["act_plan"][0]["completion_anchors"] = [
        {
            "id": "act_1_optional_only",
            "title": "可选支线",
            "required": False,
            "completion_signal": "完成可选支线。",
        }
    ]

    response = TestClient(app).post("/api/generator/import-script", json=payload)

    assert response.status_code == 200
    warnings = response.json()["warnings"]
    assert any("act_1" in warning and "required" in warning for warning in warnings)


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
    assert story["generation_parameters"] == DEFAULT_GENERATION_PARAMETERS
    assert set(story) == set(AUTHORING_KIT_EXAMPLE)


def test_exported_authoring_example_imports_without_warnings_or_internal_state() -> None:
    markdown = export_authoring_kit_markdown()
    examples = re.findall(r"```json\n(.*?)\n```", markdown, flags=re.DOTALL)
    assert len(examples) == 1
    payload = json.loads(examples[0])
    response = TestClient(app).post("/api/generator/import-script", json=payload)

    assert response.status_code == 200
    assert response.json()["warnings"] == []
    story = response.json()["config"]["story_settings"]
    assert story["generation_parameters"] == payload["generation_parameters"]
    assert not {"initial_state", "state_json", "settlement_receipt", "revision"} & payload.keys()
    for item in [*story["act_plan"], *story["main_quest_path"]]:
        for field in ("title", "objective", "player_visible"):
            assert "旧账" not in item.get(field, "")
            assert "地下室" not in item.get(field, "")


@pytest.mark.parametrize(
    "route_id", ["act_1_second_person_tracks", "act_1_second_person_testimony"]
)
def test_authoring_example_alternative_routes_auto_advance_without_optional_anchor(
    route_id,
) -> None:
    story = validate_story_settings(deepcopy(AUTHORING_KIT_EXAMPLE))
    # A prose condition is not a second executable gate after required anchors.
    story["act_plan"][0]["transition_to_next_act"]["condition"] = "还要输入额外口令才转幕。"
    game = SimpleNamespace(
        title=story["game_profile"]["title"],
        description=story["game_profile"]["description"],
        config=SimpleNamespace(story_settings=story),
    )
    state = SimpleNamespace(
        game=game,
        state_json={"current_turn": 0, "story_progress": {"current_act": "act_1"}},
    )
    state.state_json = apply_state_delta(
        state,
        SimpleNamespace(turn_number=1),
        {"story_progress_update": {"completed_anchors": [route_id]}},
    )
    # One OR branch alone does not satisfy the independent mandatory A.
    assert state.state_json["story_progress"]["current_act"] == "act_1"
    advanced = apply_state_delta(
        state,
        SimpleNamespace(turn_number=2),
        {"story_progress_update": {"completed_anchors": ["act_1_inspect_lamp"]}},
    )
    assert advanced["story_progress"]["current_act"] == "act_2"
    assert "act_1_help_fishermen" not in advanced["story_progress"]["completed_anchors"]
    other_route = (
        "act_1_second_person_testimony"
        if route_id.endswith("tracks")
        else "act_1_second_person_tracks"
    )
    assert other_route not in advanced["story_progress"]["completed_anchors"]


def test_external_story_import_does_not_inject_initial_state_or_receipts() -> None:
    payload = deepcopy(AUTHORING_KIT_EXAMPLE)
    payload["initial_state"] = {"known_facts": ["不应注入的运行状态"]}
    payload["settlement_receipt"] = {"version": 1, "status": "confirmed", "sections": []}

    response = TestClient(app).post("/api/generator/import-script", json=payload)

    assert response.status_code == 200
    config = response.json()["config"]
    assert "initial_state" not in config["story_settings"]
    assert "settlement_receipt" not in config["story_settings"]
    assert "不应注入的运行状态" not in str(config["initial_state"])
