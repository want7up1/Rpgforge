"""admin endpoint 集成测试（TestClient + 真实 DB）。

覆盖 Round 3-6 新增的 /api/admin/* endpoint：trace 列表/详情/聚合、
golden 过滤、stats 聚合、turn evaluation 查询、token 鉴权。
"""

from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models.agent_trace import AgentTrace
from app.models.turn import Turn
from app.models.turn_evaluation import TurnEvaluation
from app.services.game_creator import create_game_from_config
from tests.story_settings_fixtures import build_generated_config


def _make_trace(**overrides) -> AgentTrace:
    defaults = dict(
        job_kind="turn",
        job_id=uuid4(),
        agent="gm_runtime",
        task_type="gm_runtime",
        model="deepseek-v4-pro",
        prompt_messages=[{"role": "user", "content": "我调查泥痕"}],
        output_text='{"narrative":"门槛有泥痕"}',
        reasoning_text="玩家在调查",
        tokens_input=1500,
        tokens_output=800,
        tokens_reasoning=300,
        latency_ms=4200,
        status="success",
        extras={"slot": "pro"},
    )
    defaults.update(overrides)
    return AgentTrace(**defaults)


def test_admin_stats_empty(db_session) -> None:
    client = TestClient(app)
    resp = client.get("/api/admin/stats/recent-turns")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_size"] == 0
    assert body["avg_overall_score"] is None
    assert body["drift_severity_distribution"] == {}


def test_admin_traces_list_and_detail(db_session) -> None:
    with SessionLocal() as db:
        trace = _make_trace()
        db.add(trace)
        db.commit()
        trace_id = str(trace.id)

    client = TestClient(app)

    # 列表（summary，不含 prompt 全文）
    list_resp = client.get("/api/admin/traces?limit=10")
    assert list_resp.status_code == 200
    rows = list_resp.json()
    assert len(rows) >= 1
    assert "prompt_messages" not in rows[0]  # summary 不暴露全文
    assert rows[0]["agent"] == "gm_runtime"

    # 详情（含完整 prompt/output）
    detail_resp = client.get(f"/api/admin/traces/{trace_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["prompt_messages"][0]["content"] == "我调查泥痕"
    assert detail["output_text"] == '{"narrative":"门槛有泥痕"}'


def test_admin_traces_filter_by_agent(db_session) -> None:
    with SessionLocal() as db:
        db.add(_make_trace(agent="gm_runtime", task_type="gm_runtime"))
        db.add(_make_trace(agent="drift_validator", task_type="drift_validator"))
        db.commit()

    client = TestClient(app)
    resp = client.get("/api/admin/traces?agent=drift_validator&limit=10")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 1
    assert all(r["agent"] == "drift_validator" for r in rows)


def test_admin_trace_detail_404(db_session) -> None:
    client = TestClient(app)
    resp = client.get(f"/api/admin/traces/{uuid4()}")
    assert resp.status_code == 404


def test_admin_golden_label_filter(db_session) -> None:
    with SessionLocal() as db:
        db.add(_make_trace(extras={"label": "good", "note": "经典"}))
        db.add(_make_trace(extras={"label": "bad"}))
        db.add(_make_trace(extras={"slot": "pro"}))  # 无 label
        db.commit()

    client = TestClient(app)

    all_golden = client.get("/api/admin/golden").json()
    assert len(all_golden) == 2  # 只有带 label 的

    good_only = client.get("/api/admin/golden?label=good").json()
    assert len(good_only) == 1


def test_admin_turn_job_traces_ordering(db_session) -> None:
    job_id = uuid4()
    with SessionLocal() as db:
        db.add(_make_trace(job_id=job_id, agent="story_director", task_type="story_director"))
        db.add(_make_trace(job_id=job_id, agent="gm_runtime", task_type="gm_runtime"))
        db.commit()

    client = TestClient(app)
    resp = client.get(f"/api/admin/turn-jobs/{job_id}/traces")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    # 按 created_at 正序
    assert rows[0]["created_at"] <= rows[1]["created_at"]


def test_admin_game_evaluations(db_session) -> None:
    # turn_evaluations 有 FK 到 turns/games，需要真实 game + turn。
    game = create_game_from_config(db_session, build_generated_config())
    turn = Turn(
        game_id=game.id,
        turn_number=1,
        player_input="我调查泥痕",
        gm_output="门槛有泥痕",
        visible_summary="发现泥痕",
        hidden_summary=None,
        state_delta_json={},
        action_options_json=[],
        model_used="deepseek-v4-pro-test",
    )
    db_session.add(turn)
    db_session.commit()
    db_session.refresh(turn)

    db_session.add(
        TurnEvaluation(
            turn_id=turn.id,
            game_id=game.id,
            canon_fidelity=4,
            state_consistency=5,
            pacing=3,
            prose_quality=4,
            freshness=4,
            safety=5,
            overall_score=4.17,
            rationale={"pacing": "稍快"},
            judge_model="deepseek-v4-pro",
            status="success",
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    client = TestClient(app)
    resp = client.get(f"/api/admin/games/{game.id}/evaluations")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["overall_score"] == 4.17
    assert rows[0]["canon_fidelity"] == 4


def test_admin_requires_token_when_configured(db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "settings_admin_token", "secret-token")
    client = TestClient(app)

    blocked = client.get("/api/admin/stats/recent-turns")
    assert blocked.status_code == 401

    allowed = client.get(
        "/api/admin/stats/recent-turns",
        headers={"X-Settings-Admin-Token": "secret-token"},
    )
    assert allowed.status_code == 200
