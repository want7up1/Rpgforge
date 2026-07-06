"""锚点驱动节奏压力（确定性、纯函数）回归测试。

根因：导演每回合只反应式服务玩家行动，缺「本幕停留多久 / 距上次锚点进展多久」的压力信号，
锚点戏被无限推迟。compute_act_pacing 用现成 state 字段确定性算出 pressure，喂给导演/GM
驱动它们把戏推向下一个未完成 required 锚点。锚点内容用通用占位（脱敏，勿写真实剧本专名）。
"""

from __future__ import annotations

from app.services.act_pacing import (
    ANCHOR_PACING_HIGH_TURNS,
    ANCHOR_PACING_RISING_TURNS,
    ANCHOR_PACING_STALL_TURNS_AFTER_HIGH,
    compute_act_pacing,
    observe_act_pacing_stall,
)

ANCHOR_REQ = {
    "id": "act_1_boss",
    "required": True,
    "title": "击败首领",
    "completion_signal": "首领在战斗中倒下",
}
ANCHOR_OPT = {
    "id": "act_1_extra",
    "required": False,
    "title": "可选支线",
    "completion_signal": "支线达成",
}


def _runtime(open_anchors: list[dict]) -> dict:
    # build_runtime_story 已把 current_act.completion_anchors 过滤为未完成锚点。
    return {"current_act": {"id": "act_1", "completion_anchors": open_anchors}}


def _state(
    current_turn: int,
    *,
    last_anchor_update_turn: int | None = None,
    last_advance_turn: int | None = None,
) -> dict:
    # 真实形状 = state_v2_view 输出（v2 投影）：回合号在 active_scene.turn，不是顶层 current_turn。
    return {
        "active_scene": {"turn": current_turn},
        "story_progress": {
            "current_act": "act_1",
            "completed_anchors": [],
            "last_anchor_update_turn": last_anchor_update_turn,
            "last_advance_turn": last_advance_turn,
        },
    }


def test_recent_anchor_progress_is_low_pressure() -> None:
    pacing = compute_act_pacing(_state(5, last_anchor_update_turn=4), _runtime([ANCHOR_REQ]))
    assert pacing["turns_since_anchor"] == 1
    assert pacing["pressure"] == "low"
    assert pacing["next_required_anchor"]["id"] == "act_1_boss"


def test_rising_pressure_at_threshold() -> None:
    base = 4
    pacing = compute_act_pacing(
        _state(base + ANCHOR_PACING_RISING_TURNS, last_anchor_update_turn=base),
        _runtime([ANCHOR_REQ]),
    )
    assert pacing["pressure"] == "rising"


def test_high_pressure_points_to_first_open_required_anchor() -> None:
    base = 4
    pacing = compute_act_pacing(
        _state(base + ANCHOR_PACING_HIGH_TURNS, last_anchor_update_turn=base),
        # 可选锚点排在前面，next_required_anchor 必须跳过它指向 required 项。
        _runtime([ANCHOR_OPT, ANCHOR_REQ]),
    )
    assert pacing["pressure"] == "high"
    assert pacing["next_required_anchor"]["id"] == "act_1_boss"
    assert pacing["next_required_anchor"]["completion_signal"] == "首领在战斗中倒下"


def test_alternative_anchor_group_counts_as_one_open_requirement() -> None:
    base = 4
    pacing = compute_act_pacing(
        _state(base + ANCHOR_PACING_RISING_TURNS, last_anchor_update_turn=base),
        _runtime(
            [
                {
                    "id": "act_1_sneak_entry",
                    "required": True,
                    "alternative_group": "entry_path",
                    "title": "潜入后门",
                    "completion_signal": "主角从后门潜入据点。",
                },
                {
                    "id": "act_1_talk_entry",
                    "required": True,
                    "alternative_group": "entry_path",
                    "title": "说服守卫",
                    "completion_signal": "守卫放行主角进入据点。",
                },
                ANCHOR_REQ,
            ]
        ),
    )

    assert pacing["open_required_count"] == 2
    assert pacing["next_required_anchor"]["id"] == "act_1_sneak_entry"


def test_ready_when_no_open_required_anchor() -> None:
    # 当幕 required 锚点已全完成，只剩可选锚点 → 不硬推、pressure=ready。
    pacing = compute_act_pacing(
        _state(50, last_anchor_update_turn=2),
        _runtime([ANCHOR_OPT]),
    )
    assert pacing["pressure"] == "ready"
    assert pacing["next_required_anchor"] is None
    assert pacing["open_required_count"] == 0


def test_opening_act_with_no_anchor_progress_counts_from_zero() -> None:
    # act_1 开局：从未推进锚点，last_anchor_update_turn / last_advance_turn 均缺省。
    # turns_since_anchor 应从 0 起算 = current_turn，而非报错或恒 0。
    pacing = compute_act_pacing(_state(9), _runtime([ANCHOR_REQ]))
    assert pacing["turns_since_anchor"] == 9
    assert pacing["pressure"] == "high"


def test_required_defaults_true_when_field_missing() -> None:
    # 与 story_settings/state_applier 一致：anchor 未写 required 时视为 required=True。
    anchor_no_flag = {"id": "act_1_x", "title": "锚点", "completion_signal": "达成"}
    pacing = compute_act_pacing(_state(20, last_anchor_update_turn=1), _runtime([anchor_no_flag]))
    assert pacing["open_required_count"] == 1
    assert pacing["pressure"] == "high"
    assert pacing["next_required_anchor"]["id"] == "act_1_x"


def test_stall_observation_flags_after_high_pressure_grace_window() -> None:
    # high 从 ANCHOR_PACING_HIGH_TURNS 开始；再持续 N 回合仍无锚点进展才报警。
    current_turn = ANCHOR_PACING_HIGH_TURNS + ANCHOR_PACING_STALL_TURNS_AFTER_HIGH
    observation = observe_act_pacing_stall(_state(current_turn), _runtime([ANCHOR_REQ]))

    assert observation["stalled"] is True
    assert observation["turns_since_high"] == ANCHOR_PACING_STALL_TURNS_AFTER_HIGH
    assert observation["next_required_anchor"]["id"] == "act_1_boss"
    assert "act_pacing_stalled" in observation["flag"]


def test_stall_observation_stays_quiet_before_grace_window() -> None:
    current_turn = ANCHOR_PACING_HIGH_TURNS + ANCHOR_PACING_STALL_TURNS_AFTER_HIGH - 1
    observation = observe_act_pacing_stall(_state(current_turn), _runtime([ANCHOR_REQ]))

    assert observation["stalled"] is False
    assert observation["flag"] == ""
