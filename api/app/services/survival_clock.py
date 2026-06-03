"""B3 压力时钟兑现 + A3 危机条/失败出口。

此前 pressure 只是展示文本、从不兑现代价；属性/技能/状态也无「输」的出口。本模块引入两个
**确定性、可重放**的时钟，在 apply_state_delta 中每回合推进一次：

- 压力时钟 pressure_clock：每回合 +1，到阈值触发一次 → 侵蚀危机条 + 重置（拖延真的有代价）。
- 危机条 crisis：0–100。受「判定失败/部分成功」「活跃状态严重度」「压力触发」侵蚀，平静时缓慢回复；
  归零 → 置 story_progress.defeat，由 maintenance 生成失败结局（A3 的「输」的出口）。

确定性来源：压力按回合数累加、危机侵蚀只依赖已落在 state 的 conditions 与已持久化进 delta 的
action_outcome —— rebuild 重放每回合调用一次即可复现，无需迁移。
"""

from __future__ import annotations

from typing import Any

CRISIS_MAX = 100
PRESSURE_DEFAULT_THRESHOLD = 10
PRESSURE_CRISIS_COST = 12
FAILURE_CRISIS_COST = 12
PARTIAL_CRISIS_COST = 5
CALM_REGEN = 4

# 活跃状态严重度 → 每回合危机侵蚀。高严重度状态会持续放血，逼玩家尽快处理。
_SEVERITY_DRAIN: dict[str, int] = {
    "critical": 8,
    "极重": 8,
    "致命": 8,
    "high": 6,
    "severe": 6,
    "重": 6,
    "严重": 6,
    "medium": 3,
    "moderate": 3,
    "中": 3,
    "中度": 3,
    "low": 1,
    "minor": 1,
    "轻": 1,
    "轻微": 1,
}


def apply_survival_clocks(state: dict[str, Any], delta: dict[str, Any]) -> None:
    crisis = _ensure_crisis(state)
    pressure = _ensure_pressure(state)

    # 1) 压力时钟推进。
    pressure["value"] = int(pressure.get("value") or 0) + 1
    threshold = max(1, int(pressure.get("threshold") or PRESSURE_DEFAULT_THRESHOLD))
    pressure_triggered = pressure["value"] >= threshold
    if pressure_triggered:
        pressure["value"] = 0
        pressure["triggers"] = int(pressure.get("triggers") or 0) + 1
        pressure["last_trigger_turn"] = state.get("current_turn")

    # 2) 危机条侵蚀/回复。
    drain = 0
    outcome = _action_outcome(delta)
    if outcome == "failure":
        drain += FAILURE_CRISIS_COST
    elif outcome == "partial":
        drain += PARTIAL_CRISIS_COST
    drain += _condition_drain(state)
    if pressure_triggered:
        drain += PRESSURE_CRISIS_COST

    net = CALM_REGEN - drain
    current = crisis.get("value")
    base = int(current) if current is not None else CRISIS_MAX
    value = _clamp(base + net, 0, CRISIS_MAX)
    crisis["value"] = value
    crisis["max"] = CRISIS_MAX

    # 3) 危机归零 → 失败出口（标记，由 maintenance 生成失败结局）。已胜利则不覆盖。
    progress = state.setdefault("story_progress", {})
    if isinstance(progress, dict) and not progress.get("campaign_complete"):
        progress["defeat"] = value <= 0


def _action_outcome(delta: dict[str, Any]) -> str:
    outcome = delta.get("action_outcome")
    if isinstance(outcome, dict):
        return str(outcome.get("outcome") or "").strip().lower()
    return ""


def _condition_drain(state: dict[str, Any]) -> int:
    conditions = state.get("conditions")
    if not isinstance(conditions, list):
        return 0
    total = 0
    for condition in conditions:
        if not isinstance(condition, dict):
            continue
        status = str(condition.get("status") or "active").strip().lower()
        if status in {"resolved", "removed", "cured", "已解决", "移除", "痊愈", "解除"}:
            continue
        severity = str(condition.get("severity") or "").strip().lower()
        total += _SEVERITY_DRAIN.get(severity, 2)  # 未知严重度按中低处理
    return total


def _ensure_crisis(state: dict[str, Any]) -> dict[str, Any]:
    crisis = state.get("crisis")
    if not isinstance(crisis, dict):
        crisis = {"value": CRISIS_MAX, "max": CRISIS_MAX}
        state["crisis"] = crisis
    return crisis


def _ensure_pressure(state: dict[str, Any]) -> dict[str, Any]:
    pressure = state.get("pressure_clock")
    if not isinstance(pressure, dict):
        pressure = {"value": 0, "threshold": PRESSURE_DEFAULT_THRESHOLD, "triggers": 0}
        state["pressure_clock"] = pressure
    return pressure


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
