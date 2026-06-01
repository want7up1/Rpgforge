import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def parse_json_object(content: str, *, repair_truncated: bool = False) -> dict[str, Any]:
    """解析模型返回的 JSON 对象。

    成功路径保持不变（去 ```fence + json.loads）。默认严格：截断/畸形直接抛错，供有
    重试机制、要求完整结果的调用方（generator finalize / director 等）触发重试。

    repair_truncated=True 时（仅 state_extractor）才对疑似截断做尽力修补——state delta
    截断会丢失整回合状态、且重试可能确定性地再次截断，抢救已完成成员优于整回合全丢；
    真正畸形（非截断）仍原样抛错。
    """
    text = _strip_code_fence(content)

    try:
        return _loads_object(text)
    except (ValueError, json.JSONDecodeError) as exc:
        if not repair_truncated:
            raise
        repaired = _repair_truncated_object(text)
        if repaired is None:
            # 区分日志：补齐括号后仍解析不出 → 大概率是真畸形而非单纯截断。
            logger.warning(
                "JSON parse failed and not recoverable as truncated object (len=%s): %s",
                len(text),
                exc,
            )
            raise
        logger.warning(
            "JSON parse failed (len=%s), recovered via truncation repair (kept %s top-level keys).",
            len(text),
            len(repaired),
        )
        return repaired


def _strip_code_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _loads_object(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object from model response.")
    return value


def _repair_truncated_object(text: str) -> dict[str, Any] | None:
    """对疑似被截断的 JSON 对象做尽力修补。

    扫描字符串/转义感知的括号栈，定位「最后一个完整顶层成员」结束的位置，截断后补齐所有
    未闭合的容器分隔符，再尝试解析。无法稳妥修补时返回 None（让调用方按原错误抛出）。
    """
    start = text.find("{")
    if start == -1:
        return None

    stack: list[str] = []  # 待闭合的容器栈（'{' / '['）
    in_string = False
    escaped = False
    # 记录「位于顶层对象内、且此刻不在任何字符串/嵌套容器中」时，最近一次完整成员的结束位置。
    # 即栈深为 1（只剩最外层对象）时遇到的 '}' '] ' 或 ',' 之后的位置。
    last_safe_end = -1

    for idx in range(start, len(text)):
        ch = text[idx]

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch in "{[":
            stack.append(ch)
            continue
        if ch in "}]":
            if not stack:
                return None  # 括号不匹配，非典型截断
            opener = stack.pop()
            if (ch == "}" and opener != "{") or (ch == "]" and opener != "["):
                return None
            if not stack:
                # 顶层对象在此正常闭合：本不是截断，交回上层按原错误处理。
                return None
            if len(stack) == 1:
                # 顶层对象的某个值（嵌套对象/数组）刚刚完整闭合 → 此处是安全切点。
                last_safe_end = idx + 1
            continue
        if ch == "," and len(stack) == 1:
            # 顶层对象成员之间的逗号 → 逗号「之前」是一个完整成员，安全切到逗号前。
            last_safe_end = idx
            continue

    # 没有任何完整的顶层成员可保留 → 放弃修补。
    if last_safe_end <= start:
        return None

    truncated = text[start:last_safe_end].rstrip().rstrip(",")
    candidate = truncated + "}"  # 截断点必然停在顶层对象内，补齐最外层 '}' 即可
    try:
        value = json.loads(candidate)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or not value:
        return None
    return value
