import json

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models.generator_job import TurnJob
from app.models.turn import Turn
from app.routers.gameplay import gameplay_service
from app.services.deepseek_client import ChatCompletionResult
from app.services.game_creator import create_game_from_config
from app.services.gameplay import GameplayService
from tests.story_settings_fixtures import build_two_act_config


class DeterministicRouter:
    def __init__(self):
        self.narratives = 0

    async def use_flash(self, task, _messages, **_options):
        result = {"inventory_add": ["仓库钥匙"]} if task == "state_delta_extract" else {}
        return ChatCompletionResult(content=json.dumps(result), model="fake", raw={})

    async def use_pro(self, _task, _messages, **_options):
        self.narratives += 1
        return ChatCompletionResult(
            content=json.dumps(
                {
                    "narrative": "你接过仓库钥匙，继续追查运单的来历。",
                    "action_options": [{"key": key, "label": "继续调查"} for key in "ABCD"],
                }
            ),
            model="fake",
            raw={},
        )


def test_inline_real_service_atomically_links_result_and_replays_request(db_session):
    game = create_game_from_config(db_session, build_two_act_config())
    router = DeterministicRouter()
    service = GameplayService(router=router)
    app.dependency_overrides[gameplay_service] = lambda: service
    try:
        client = TestClient(app)
        payload = {"player_input": "取钥匙", "request_id": "same-action", "expected_revision": 0}
        first = client.post(f"/api/games/{game.id}/turns", json=payload)
        second = client.post(f"/api/games/{game.id}/turns", json=payload)
        assert first.status_code == second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
        assert first.json()["settlement_receipt"]["status"] == "confirmed"
        assert router.narratives == 1
        db_session.expire_all()
        job = db_session.scalar(select(TurnJob).where(TurnJob.game_id == game.id))
        assert str(job.turn_id) == first.json()["id"]
        assert job.status == "completed" and job.maintenance_status == "completed"
    finally:
        app.dependency_overrides.pop(gameplay_service, None)


def test_inline_post_persistence_failure_can_still_retrieve_original_turn(db_session):
    game = create_game_from_config(db_session, build_two_act_config())
    router = DeterministicRouter()
    service = GameplayService(router=router)

    class LostMaintenance:
        async def extract(self, *_args, **_kwargs):
            raise RuntimeError("simulated process failure after narrative commit")

    service.state_extractor = LostMaintenance()
    app.dependency_overrides[gameplay_service] = lambda: service
    try:
        client = TestClient(app, raise_server_exceptions=False)
        payload = {"player_input": "取钥匙", "request_id": "lost-response"}
        first = client.post(f"/api/games/{game.id}/turns", json=payload)
        assert first.status_code >= 500
        retry = client.post(f"/api/games/{game.id}/turns", json=payload)
        assert retry.status_code == 201
        assert retry.json()["settlement_receipt"]["status"] == "failed"
        assert router.narratives == 1
        assert (
            db_session.scalar(select(func.count()).select_from(Turn).where(Turn.game_id == game.id))
            == 1
        )
    finally:
        app.dependency_overrides.pop(gameplay_service, None)
