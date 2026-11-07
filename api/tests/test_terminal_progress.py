from fastapi.testclient import TestClient

from app.main import app
from app.services.game_creator import create_game_from_config
from app.services.turn_maintenance_jobs import _with_epilogue
from tests.story_settings_fixtures import build_two_act_config


def test_epilogue_updates_canonical_and_projected_progress_without_changing_seed():
    seed = {"current_turn": 4, "story_progress": {"current_act": "act_2"}}
    result = _with_epilogue(seed, "正式尾声")
    assert result["story_progress"]["epilogue"] == "正式尾声"
    assert result["v2"]["story_progress"]["epilogue"] == "正式尾声"
    assert "epilogue" not in seed["story_progress"]
    defeat = _with_epilogue(seed, "失败尾声", status="defeated")
    assert defeat["story_progress"]["defeat"] is True
    assert defeat["story_progress"]["campaign_complete"] is False
    assert defeat["v2"]["story_progress"]["campaign_complete"] is False


def test_finished_game_rejects_new_actions_until_restore_or_restart(db_session):
    game = create_game_from_config(db_session, build_two_act_config())
    game.status = "completed"
    db_session.commit()
    client = TestClient(app)
    for suffix in ("", "/jobs"):
        response = client.post(f"/api/games/{game.id}/turns{suffix}", json={"player_input": "继续"})
        assert response.status_code == 409
        assert "结束" in response.json()["detail"]
