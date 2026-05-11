from app.models.mode import Mode

PRIORITY_WEIGHT = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}

IMPLIED_TRIGGERS_BY_MODE = {
    "调查": [
        "调查",
        "检查",
        "搜索",
        "搜查",
        "探查",
        "查看",
        "观察",
        "研究",
        "追踪",
        "追问",
        "寻找线索",
        "勘查",
        "审问",
    ],
    "探索": [
        "探索",
        "前往",
        "进入",
        "穿过",
        "绕到",
        "开路",
        "侦察",
        "巡查",
        "移动",
        "离开",
        "翻越",
    ],
    "社交": [
        "交谈",
        "沟通",
        "说服",
        "安抚",
        "询问",
        "谈判",
        "威胁",
        "拉拢",
        "表达",
        "告知",
    ],
    "战斗": [
        "攻击",
        "开火",
        "射击",
        "格挡",
        "闪避",
        "战斗",
        "迎战",
        "突袭",
        "伏击",
        "防守",
        "撤退",
    ],
    "建设": [
        "建设",
        "建造",
        "维修",
        "升级",
        "生产",
        "管理",
        "分配",
        "招募",
        "基地",
        "资源",
    ],
    "经营": [
        "建设",
        "建造",
        "维修",
        "升级",
        "生产",
        "管理",
        "分配",
        "招募",
        "基地",
        "资源",
    ],
    "休整": [
        "休息",
        "治疗",
        "包扎",
        "恢复",
        "整理",
        "清点",
        "睡眠",
        "训练",
    ],
    "日常": [
        "休息",
        "治疗",
        "包扎",
        "恢复",
        "整理",
        "清点",
        "睡眠",
        "训练",
    ],
    "潜行": [
        "潜行",
        "躲避",
        "绕开",
        "隐藏",
        "埋伏",
        "偷袭",
        "潜入",
    ],
    "主线": [
        "主线",
        "推进",
        "继续任务",
        "关键目标",
    ],
}


def select_mode(player_input: str, modes: list[Mode]) -> Mode | None:
    text = player_input.lower()
    candidates: list[tuple[float, int, int, Mode]] = []
    for index, mode in enumerate(modes):
        if not mode.enabled:
            continue
        score = _mode_trigger_score(text, mode)
        if score > 0:
            candidates.append(
                (
                    score,
                    PRIORITY_WEIGHT.get(mode.priority or "medium", 2),
                    -index,
                    mode,
                )
            )

    if candidates:
        return max(candidates, key=lambda item: (item[0], item[1], item[2]))[3]

    for mode in modes:
        if mode.enabled and "主线" in mode.name:
            return mode
    return next((mode for mode in modes if mode.enabled), None)


def _mode_trigger_score(text: str, mode: Mode) -> float:
    score = 0.0
    seen: set[str] = set()
    for trigger in _mode_triggers(mode):
        trigger = trigger.strip().lower()
        if not trigger or trigger in seen:
            continue
        seen.add(trigger)
        if trigger in text:
            score += _trigger_weight(trigger)
    return score


def _mode_triggers(mode: Mode) -> list[str]:
    triggers = list(mode.triggers or [])
    mode_text = f"{mode.name or ''}\n{mode.injection or ''}"
    for marker, implied_triggers in IMPLIED_TRIGGERS_BY_MODE.items():
        if marker in mode_text:
            triggers.extend(implied_triggers)
    return triggers


def _trigger_weight(trigger: str) -> float:
    if len(trigger) >= 4:
        return 2.0
    if len(trigger) == 3:
        return 1.5
    return 1.0
