"""History restoration and retry races, using the isolated PostgreSQL fixture."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.db.session import SessionLocal
from app.main import app
from app.models.game import Game
from app.models.generator_job import TurnJob
from app.models.progress_save import GameProgressSave
from app.models.state_delta import StateDelta
from app.models.summary import Summary
from app.models.turn import Turn
from app.routers.gameplay import _admit_request_or_409
from app.routers.gameplay import gameplay_service as gameplay_service_dependency
from app.schemas.turn import TurnCreate, TurnJobRead
from app.services.context_compressor import ContextCompressionOutput, ContextCompressor
from app.services.game_creator import create_game_from_config
from app.services.gameplay import GameplayValidationError
from app.services.progress_saves import (
    create_progress_save,
    load_progress_save,
    restart_game_progress,
)
from app.services.timeline import (
    TimelineConflict,
    clean_replay_seed,
    config_digest,
)
from app.services.turn_rewind import rewind_game_to_turn
from tests.story_settings_fixtures import build_generated_config


def add_turn(db, game, number):
    turn = Turn(
        game_id=game.id,
        turn_number=number,
        player_input=f"行动{number}",
        gm_output=f"正文{number}",
        state_delta_json={},
    )
    db.add(turn)
    db.commit()
    return turn


@pytest.mark.parametrize("size", [10, 50])
def test_load_batches_history_reads_and_preserves_delta_statuses(db_session, size):
    game = create_game_from_config(db_session, build_generated_config())
    expected = {}
    for number in range(1, size + 1):
        turn_id = uuid4()
        status = ("approved", "rejected", "failed")[number % 3]
        payload = {"new_known_facts": [f"事实{number}"]}
        db_session.add(Turn(
            id=turn_id, game_id=game.id, turn_number=number,
            player_input="调查", gm_output="新的线索。",
            state_delta_json=payload if status == "approved" else {},
        ))
        db_session.add(StateDelta(
            game_id=game.id, turn_id=turn_id, status=status,
            delta_json=payload, attempt_count=8,
        ))
        expected[turn_id] = (status, payload)
    db_session.commit()
    saved = create_progress_save(db_session, game, name="批量读档")
    db_session.commit()
    selects = []

    def count_selects(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count_selects)
    try:
        load_progress_save(db_session, game, saved)
        db_session.commit()
    finally:
        event.remove(engine, "before_cursor_execute", count_selects)
    # The historical per-turn reads exceeded this even for ten turns.
    assert len(selects) <= 20
    restored = db_session.scalars(select(StateDelta).where(StateDelta.game_id == game.id)).all()
    assert len(restored) == size
    for delta in restored:
        assert (delta.status, delta.delta_json) == expected[delta.turn_id]
        assert delta.attempt_count == 8
        assert delta.turn.state_delta_json == (
            delta.delta_json if delta.status == "approved" else {}
        )


def test_seed_cleanup_never_mutates_live_ending():
    live = {
        "current_turn": 0,
        "story_progress": {"current_act": "act_1", "epilogue": "尾声", "defeat": True},
    }
    clean = clean_replay_seed(live)
    assert clean["story_progress"] == {"current_act": "act_1", "epilogue": "", "defeat": False}
    assert live["story_progress"]["epilogue"] == "尾声"


def test_job_projection_defaults_legacy_and_transient_metadata_without_loading_relationships():
    class Job(SimpleNamespace):
        @property
        def turn(self):
            raise AssertionError("serialization must not load a relationship")

    job = Job(
        id=uuid4(),
        game_id=uuid4(),
        status="running",
        stage_total=None,
        game_revision=None,
        event_seq=None,
        reasoning_content=None,
    )
    projected = TurnJobRead.from_job(job)
    assert projected.stage_total == 6
    assert projected.game_revision == projected.event_seq == projected.timeline_generation == 0
    assert projected.reasoning_content == ""
    assert projected.turn is None
    job.game_revision, job.timeline_generation, job.stream_revision, job.event_seq = 7, 3, 2, 81
    current = TurnJobRead.from_job(job)
    assert (
        current.game_revision,
        current.timeline_generation,
        current.stream_revision,
        current.event_seq,
    ) == (7, 3, 2, 81)


def test_legacy_empty_receipt_is_absent_in_turn_api(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    turn = add_turn(db_session, game, 1)
    turn.settlement_receipt = {}
    db_session.commit()
    response = TestClient(app).get(f"/api/games/{game.id}/turns/{turn.id}")
    assert response.status_code == 200
    assert response.json()["settlement_receipt"] is None


def test_turn_job_retries_reuse_one_job_and_validate_hash(db_session, monkeypatch):
    game = create_game_from_config(db_session, build_generated_config())
    queued = []
    monkeypatch.setattr("app.routers.gameplay.enqueue_turn_job", queued.append)
    monkeypatch.setattr("app.routers.gameplay.reconcile_turn_job_liveness", lambda *_: False)
    client = TestClient(app)
    payload = {"player_input": "检查门槛", "request_id": "lost-response", "expected_revision": 0}
    first = client.post(f"/api/games/{game.id}/turns/jobs", json=payload)
    second = client.post(f"/api/games/{game.id}/turns/jobs", json=payload)
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert len(queued) == 1
    assert first.json()["game_revision"] == 1
    conflict = client.post(
        f"/api/games/{game.id}/turns/jobs", json={**payload, "player_input": "改走另一条路"}
    )
    assert conflict.status_code == 409
    assert db_session.scalar(select(func.count(TurnJob.id))) == 1


def test_old_revision_rejected_after_config_edit_but_legacy_request_works(db_session, monkeypatch):
    game = create_game_from_config(db_session, build_generated_config())
    client = TestClient(app)
    edited = client.patch(
        f"/api/games/{game.id}/config", json={"story_settings": game.config.story_settings}
    )
    assert edited.status_code == 200
    assert edited.json()["revision"] == 1
    monkeypatch.setattr("app.routers.gameplay.enqueue_turn_job", lambda *_: None)
    stale = client.post(
        f"/api/games/{game.id}/turns/jobs",
        json={"player_input": "检查", "request_id": "stale", "expected_revision": 0},
    )
    assert stale.status_code == 409
    legacy = client.post(f"/api/games/{game.id}/turns/jobs", json={"player_input": "检查"})
    assert legacy.status_code == 202


def test_synchronous_request_retries_return_same_persisted_turn(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    calls = []

    class StubService:
        async def run_turn(self, db, current_game, payload, *, job_id=None):
            calls.append(payload.resolved_player_input)
            turn = add_turn(db, current_game, 1)
            job = db.get(TurnJob, job_id)
            job.status, job.turn_id = "completed", turn.id
            db.commit()
            return turn

    app.dependency_overrides[gameplay_service_dependency] = StubService
    try:
        client = TestClient(app)
        payload = {"player_input": "检查", "request_id": "sync-retry", "expected_revision": 0}
        first = client.post(f"/api/games/{game.id}/turns", json=payload)
        again = client.post(f"/api/games/{game.id}/turns", json=payload)
        assert first.status_code == again.status_code == 201
        assert first.json()["id"] == again.json()["id"]
        assert calls == ["检查"]
        assert db_session.scalar(select(func.count(Turn.id))) == 1
    finally:
        app.dependency_overrides.pop(gameplay_service_dependency, None)


def test_inline_admission_uses_timeout_without_looking_for_a_queue_job(db_session, monkeypatch):
    game = create_game_from_config(db_session, build_generated_config())
    job = TurnJob(
        game_id=game.id,
        status="running",
        request_json={"player_input": "检查", "_execution_mode": "inline"},
        last_event_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    monkeypatch.setattr(
        "app.services.job_queue.redis_connection",
        lambda: pytest.fail("inline calls do not have Redis jobs"),
    )
    client = TestClient(app)
    active = client.get(f"/api/games/{game.id}/turns/jobs/active")
    assert active.status_code == 200 and active.json()["id"] == str(job.id)
    job.last_event_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()
    expired = client.get(f"/api/games/{game.id}/turns/jobs/active")
    assert expired.status_code == 200 and expired.json() is None


def test_sync_response_stays_replayable_when_only_later_maintenance_fails(db_session):
    game = create_game_from_config(db_session, build_generated_config())

    class PersistThenFail:
        async def run_turn(self, db, current_game, payload, *, job_id=None):
            turn = add_turn(db, current_game, 1)
            job = db.get(TurnJob, job_id)
            job.status, job.turn_id = "completed", turn.id
            job.maintenance_status = "running"
            db.commit()
            raise GameplayValidationError("结算阶段失败")

    app.dependency_overrides[gameplay_service_dependency] = PersistThenFail
    try:
        client = TestClient(app)
        payload = {"player_input": "检查", "request_id": "persisted-then-failed"}
        first = client.post(f"/api/games/{game.id}/turns", json=payload)
        assert first.status_code == 502
        again = client.post(f"/api/games/{game.id}/turns", json=payload)
        assert again.status_code == 201
        job = db_session.scalar(select(TurnJob).where(TurnJob.game_id == game.id))
        assert job.status == "completed" and job.maintenance_status == "failed"
        assert db_session.scalar(select(func.count(Turn.id))) == 1
    finally:
        app.dependency_overrides.pop(gameplay_service_dependency, None)


def test_concurrent_same_request_has_single_admission(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    game_id = game.id
    barrier = Barrier(2)

    def admit():
        with SessionLocal() as db:
            barrier.wait(timeout=5)
            job, replay = _admit_request_or_409(
                db,
                game_id,
                TurnCreate(player_input="同一个行动", request_id="raced", expected_revision=0),
            )
            db.commit()
            return job.id, replay

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(lambda _: admit(), range(2)))
    assert a[0] == b[0]
    assert sorted([a[1], b[1]]) == [False, True]
    db_session.expire_all()
    assert db_session.get(Game, game_id).revision == 1


def test_rollback_generation_invalidates_old_request_and_background_job(db_session, monkeypatch):
    game = create_game_from_config(db_session, build_generated_config())
    payload = TurnCreate(player_input="检查", request_id="old", expected_revision=0)
    job, _ = _admit_request_or_409(db_session, game.id, payload)
    job.status = "completed"
    job.maintenance_status = "running"
    job.maintenance_stage = "memory_update"
    db_session.commit()
    restart_game_progress(db_session, game)
    db_session.commit()
    assert game.timeline_generation == 1
    assert game.revision == 2
    assert job.maintenance_status == "skipped"
    client = TestClient(app)
    response = client.post(f"/api/games/{game.id}/turns/jobs", json=payload.model_dump())
    assert response.status_code == 409
    assert client.get(f"/api/games/{game.id}/turns/jobs/{job.id}").status_code == 409


def test_save_round_trip_preserves_seed_attempts_and_real_ending(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    initial_seed = deepcopy(game.state.initial_state_json)
    turn = add_turn(db_session, game, 1)
    delta = StateDelta(
        game_id=game.id,
        turn_id=turn.id,
        status="failed",
        delta_json={},
        attempt_count=4,
    )
    db_session.add(delta)
    game.state.state_json = {
        **game.state.state_json,
        "current_turn": 1,
        "story_progress": {"current_act": "act_1", "defeat": True, "epilogue": "真实尾声"},
    }
    game.state.current_turn = 1
    game.status = "defeated"
    db_session.commit()
    saved = create_progress_save(db_session, game, name="终局")
    db_session.commit()
    assert saved.snapshot_version == 2
    assert saved.config_hash == config_digest(game)
    restart_game_progress(db_session, game)
    db_session.commit()
    load_progress_save(db_session, game, saved)
    db_session.commit()
    restored_delta = db_session.scalar(select(StateDelta).where(StateDelta.game_id == game.id))
    assert restored_delta.attempt_count == 4
    assert game.state.initial_state_json == initial_seed
    assert game.state.state_json["story_progress"]["epilogue"] == "真实尾声"
    assert game.status == "defeated"


def test_early_save_restores_clean_seed_after_later_legacy_contamination(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    saved = create_progress_save(db_session, game, name="开局")
    db_session.commit()
    seed = deepcopy(game.state.initial_state_json)
    seed["story_progress"]["epilogue"] = "未来尾声"
    seed["story_progress"]["campaign_complete"] = True
    game.state.initial_state_json = seed
    game.status = "completed"
    db_session.commit()
    load_progress_save(db_session, game, saved)
    db_session.commit()
    assert not game.state.initial_state_json["story_progress"].get("epilogue")
    assert not game.state.initial_state_json["story_progress"].get("campaign_complete")
    assert not game.state.state_json["story_progress"].get("epilogue")
    assert game.status != "completed"


def test_load_response_exposes_only_restored_summary_collection(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    add_turn(db_session, game, 1)
    game.state.current_turn = 1
    db_session.add(
        Summary(
            game_id=game.id,
            type="turn",
            range_start_turn=1,
            range_end_turn=1,
            content="存档时的记忆",
        )
    )
    db_session.commit()
    saved = create_progress_save(db_session, game, name="第一回合")
    db_session.commit()
    add_turn(db_session, game, 2)
    db_session.add(
        Summary(
            game_id=game.id,
            type="turn",
            range_start_turn=2,
            range_end_turn=2,
            content="废弃未来秘密",
        )
    )
    db_session.commit()
    response = TestClient(app).post(f"/api/games/{game.id}/progress-saves/{saved.id}/load")
    assert response.status_code == 200
    assert [item["content"] for item in response.json()["summaries"]] == ["存档时的记忆"]


def test_legacy_save_without_seed_keeps_opening_separate_from_saved_live_state(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    original_seed = deepcopy(game.state.initial_state_json)
    saved = GameProgressSave(
        game_id=game.id,
        name="旧档",
        snapshot_version=1,
        state_current_turn=1,
        state_json={"current_turn": 1, "known_facts": ["存档中的事实"]},
        turns_json=[],
        summaries_json=[],
        state_deltas_json=[],
    )
    db_session.add(saved)
    db_session.commit()
    load_progress_save(db_session, game, saved)
    db_session.commit()
    assert game.state.state_json["known_facts"] == ["存档中的事实"]
    assert game.state.initial_state_json == original_seed


def test_rewind_drops_every_summary_that_mentions_the_discarded_future(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    add_turn(db_session, game, 1)
    add_turn(db_session, game, 2)
    for kind, start, end in [
        ("turn", 1, 1),
        ("chapter", 1, 2),
        ("long_term", 1, 2),
        ("narrative", 1, 2),
    ]:
        db_session.add(
            Summary(
                game_id=game.id,
                type=kind,
                range_start_turn=start,
                range_end_turn=end,
                content="过去" if end == 1 else "未来秘密",
            )
        )
    game.state.summary = "未来秘密"
    db_session.commit()
    assert rewind_game_to_turn(db_session, game, 1) == 1
    remaining = list(db_session.scalars(select(Summary).where(Summary.game_id == game.id)))
    assert [(item.type, item.range_end_turn) for item in remaining] == [("turn", 1)]
    assert game.state.summary == ""
    prompt = ContextCompressor().load_prompt_summaries(db_session, game.id)
    assert "未来秘密" not in str(prompt)


def test_summary_query_ignores_future_and_older_async_output_cannot_replace_newer(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    turn = add_turn(db_session, game, 1)
    for end, content in [(1, "有效记忆"), (99, "幽灵未来")]:
        db_session.add(
            Summary(
                game_id=game.id,
                type="long_term",
                range_start_turn=1,
                range_end_turn=end,
                content=content,
            )
        )
    db_session.commit()
    compressor = ContextCompressor()
    assert (
        compressor.load_prompt_summaries(db_session, game.id)["long_term"]["content"] == "有效记忆"
    )
    # Remove the intentionally invalid fixture, then model a newer same-generation completion.
    future = db_session.scalar(select(Summary).where(Summary.range_end_turn == 99))
    db_session.delete(future)
    db_session.commit()
    add_turn(db_session, game, 2)
    current = db_session.scalar(select(Summary).where(Summary.type == "long_term"))
    current.range_end_turn = 2
    current.content = "第二回合记忆"
    game.state.summary = current.content
    db_session.commit()

    async def output(**_):
        return ContextCompressionOutput(
            long_term_summary="迟到的第一回合", turn_visible_summary="旧正文摘要"
        )

    compressor._compress_with_fallback = output
    asyncio.run(compressor.update_after_turn(db_session, game, turn, {}))
    assert current.content == "第二回合记忆"
    assert game.state.summary == "第二回合记忆"


def test_compression_finishing_after_restart_cannot_write_into_new_timeline(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    turn = add_turn(db_session, game, 1)
    compressor = ContextCompressor()

    async def restart_during_model(**_):
        with SessionLocal() as other:
            other_game = other.get(Game, game.id)
            restart_game_progress(other, other_game)
            other.commit()
        return ContextCompressionOutput(long_term_summary="旧任务的未来摘要")

    compressor._compress_with_fallback = restart_during_model
    with pytest.raises(TimelineConflict):
        asyncio.run(compressor.update_after_turn(db_session, game, turn, {}))
    db_session.rollback()
    assert db_session.scalar(select(func.count(Summary.id))) == 0
    assert db_session.scalar(select(func.count(Turn.id))) == 0


def test_compression_finishing_after_settings_change_cannot_restore_old_memory(db_session):
    game = create_game_from_config(db_session, build_generated_config())
    turn = add_turn(db_session, game, 1)
    compressor = ContextCompressor()

    async def edit_during_model(**_):
        with SessionLocal() as other:
            other_game = other.get(Game, game.id)
            updated = deepcopy(other_game.config.story_settings)
            updated["worldview"]["setting"] = "新地点设定"
            other_game.config.story_settings = updated
            other.commit()
        return ContextCompressionOutput(long_term_summary="按旧设定生成的摘要")

    compressor._compress_with_fallback = edit_during_model
    with pytest.raises(TimelineConflict, match="设定"):
        asyncio.run(compressor.update_after_turn(db_session, game, turn, {}))
    db_session.rollback()
    assert db_session.scalar(select(func.count(Summary.id))) == 0
