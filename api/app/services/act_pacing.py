"""锚点驱动节奏压力（确定性、纯函数、零新增 state）。

根因（实测 28 回合困在第一幕、4 个 required 锚点只完成 1 个）：导演每回合只反应式服务玩家
当下行动、缺「本幕停留多久 / 距上次锚点进展多久」的压力信号，于是在玩家不断选"再准备一次"
的题材里把锚点戏无限推迟；GM 给的 A/B/C/D 也全落在"准备"框里 → 死循环自我强化。

本模块用现成 state 字段（current_turn / story_progress.last_anchor_update_turn /
last_advance_turn）确定性算出 pressure 与「下一个未完成 required 锚点」，喂给导演和 GM，
让它们在停留过久时主动把戏推向该锚点。不做任何文本语义推断、不写回 state、rebuild 可复现。
"""

from __future__ import annotations

from typing import Any

# 距上次锚点进展达到此回合数 → rising（导演明显朝锚点收拢、减少纯铺垫）。
ANCHOR_PACING_RISING_TURNS = 4
# 距上次锚点进展达到此回合数 → high（导演必须把戏推到锚点 completion_signal 兑现的临界点）。
# observation-driven：真实存档实测某锚点完成后约 18 回合无新锚点进展仍原地打转。
ANCHOR_PACING_HIGH_TURNS = 8


def compute_act_pacing(
    state_v2: dict[str, Any] | None,
    runtime_story: dict[str, Any] | None,
) -> dict[str, Any]:
    """据当前 state 与 runtime_story 算本幕节奏压力。

    返回 {turns_in_act, turns_since_anchor, open_required_count, pressure, next_required_anchor}。
    pressure ∈ {low, rising, high, ready}；ready = 当幕已无未完成 required 锚点（不硬推）。
    """
    state_v2 = state_v2 or {}
    progress = state_v2.get("story_progress") or {}
    if not isinstance(progress, dict):
        progress = {}

    # state_v2_view 的回合号在 active_scene.turn；兼容裸 state_json 的顶层 current_turn。
    active_scene = state_v2.get("active_scene") or {}
    if isinstance(active_scene, dict) and active_scene.get("turn") is not None:
        current_turn = _int(active_scene.get("turn"))
    else:
        current_turn = _int(state_v2.get("current_turn"))
    last_advance_turn = _opt_int(progress.get("last_advance_turn"))
    # 距上次锚点进展的回合数。优先 last_anchor_update_turn；从未推进过锚点时回退到进入本幕的
    # 回合（last_advance_turn），再回退 0（开局幕 act_1 从第 0 回合起算）。
    baseline = _opt_int(progress.get("last_anchor_update_turn"))
    if baseline is None:
        baseline = last_advance_turn
    turns_since_anchor = max(0, current_turn - (baseline or 0))
    turns_in_act = max(0, current_turn - (last_advance_turn or 0))

    current_act = (runtime_story or {}).get("current_act") or {}
    if not isinstance(current_act, dict):
        current_act = {}
    # build_runtime_story 已把 completion_anchors 过滤为「未完成」锚点。
    open_anchors = current_act.get("completion_anchors") or []
    open_required = [
        anchor
        for anchor in open_anchors
        if isinstance(anchor, dict) and _required(anchor)
    ]

    if not open_required:
        pressure = "ready"
        next_required_anchor = None
    else:
        if turns_since_anchor >= ANCHOR_PACING_HIGH_TURNS:
            pressure = "high"
        elif turns_since_anchor >= ANCHOR_PACING_RISING_TURNS:
            pressure = "rising"
        else:
            pressure = "low"
        first = open_required[0]
        next_required_anchor = {
            "id": _text(first.get("id")),
            "title": _text(first.get("title")),
            "completion_signal": _text(
                first.get("completion_signal") or first.get("description")
            ),
        }

    return {
        "turns_in_act": turns_in_act,
        "turns_since_anchor": turns_since_anchor,
        "open_required_count": len(open_required),
        "pressure": pressure,
        "next_required_anchor": next_required_anchor,
    }


def _required(anchor: dict[str, Any]) -> bool:
    # 与 story_settings/state_applier 一致：未写 required 字段时默认 required=True。
    value = anchor.get("required")
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", ""}
    return bool(value)


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _opt_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""
