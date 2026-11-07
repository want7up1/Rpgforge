import anyio
import pytest
from sqlalchemy import func, select

from app.models.generator_job import TurnJob
from app.models.turn import Turn
from app.schemas.turn import GMRuntimeOutput
from app.services.game_creator import create_game_from_config
from app.services.progress_saves import restart_game_progress
from app.services.timeline import advance_timeline, lock_game_timeline
from app.services.turn_jobs import _update_stream_progress, run_turn_job
from app.services.turn_maintenance_jobs import (
    _apply_delta,
    _mark_maintenance_running,
    _persist_campaign_ending,
)
from tests.story_settings_fixtures import build_two_act_config


def test_old_worker_and_ending_cannot_write_after_timeline_advance(db_session):
    game = create_game_from_config(db_session, build_two_act_config())
    job = TurnJob(game_id=game.id, status="running", request_json={"player_input": "行动"})
    db_session.add(job)
    db_session.commit()
    advance_timeline(db_session, lock_game_timeline(db_session, game.id))
    db_session.commit()
    _update_stream_progress(
        job.id,
        reasoning="旧推理",
        content="旧正文",
        narrative="旧正文",
        model=None,
        message="旧更新",
        stage="gm_runtime",
        stage_started_at=None,
        reset_buffers=False,
    )
    _apply_delta(job.id, {"new_known_facts": ["错误的未来事实"]})
    _persist_campaign_ending(game.id, "错误的未来尾声", "completed", expected_generation=0)
    db_session.expire_all()
    assert db_session.get(TurnJob, job.id).narrative_buffer == ""
    assert db_session.get(type(game), game.id).status == "active"
    assert "错误的未来事实" not in str(game.state.state_json)


@pytest.mark.parametrize("invalidation", ["restart", "timeout"])
def test_model_result_returning_after_invalidation_does_not_persist_turn(
    db_session, monkeypatch, invalidation
):
    game = create_game_from_config(db_session, build_two_act_config())
    job = TurnJob(game_id=game.id, status="pending", request_json={"player_input": "行动"})
    db_session.add(job)
    db_session.commit()

    class ModelFinishesAfterRestart:
        async def load_turn_runtime_context(self, _db, loaded_game, _request, **_callbacks):
            from types import SimpleNamespace

            return SimpleNamespace(game=loaded_game, player_input="行动")

        async def generate_turn_runtime_output(self, _context, **_callbacks):
            from app.db.session import SessionLocal

            with SessionLocal() as db:
                from app.models.game import Game

                loaded = db.get(Game, game.id)
                if invalidation == "restart":
                    restart_game_progress(db, loaded)
                else:
                    expired = db.get(TurnJob, job.id)
                    expired.status = "failed"
                    db.add(expired)
                db.commit()
            return GMRuntimeOutput(
                narrative="应被丢弃的旧结果",
                action_options=[{"key": key, "label": "行动"} for key in "ABCD"],
            ), "fake-model"

        def persist_runtime_turn(self, *_args, **_kwargs):
            raise AssertionError("stale model output reached persistence")

    monkeypatch.setattr("app.services.turn_jobs.GameplayService", ModelFinishesAfterRestart)
    anyio.run(run_turn_job, job.id)
    assert (
        db_session.scalar(select(func.count()).select_from(Turn).where(Turn.game_id == game.id))
        == 0
    )
    db_session.expire_all()
    assert db_session.get(TurnJob, job.id).status == "failed"


def test_duplicate_maintenance_and_late_extraction_do_not_reopen_finished_work(
    db_session, monkeypatch
):
    game = create_game_from_config(db_session, build_two_act_config())
    turn = Turn(game_id=game.id, turn_number=1, player_input="调查", gm_output="剧情")
    db_session.add(turn)
    db_session.flush()
    job = TurnJob(
        game_id=game.id,
        turn_id=turn.id,
        status="completed",
        request_json={},
        maintenance_status="pending",
        maintenance_stage="state_extract",
    )
    db_session.add(job)
    db_session.commit()
    monkeypatch.setattr(
        "app.services.turn_maintenance_jobs.publish_turn_job_snapshot", lambda *_: None
    )
    assert _mark_maintenance_running(job.id, stage="state_extract", message="提取")
    assert not _mark_maintenance_running(job.id, stage="state_extract", message="重复提取")
    db_session.refresh(job)
    job.maintenance_status = "failed"
    db_session.commit()
    assert not _apply_delta(job.id, {"new_known_facts": ["晚到结果"]}, require_active=True)
    assert not _mark_maintenance_running(job.id, stage="state_extract", message="重复提取")
