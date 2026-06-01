"""GM 输出观测层（Round 20）。

定位：**只观测、不重写**。每回合 GM 输出后，用代码对文本做轻量、确定性的校验，
把结果写进 telemetry 供 dashboard / 调优观察。不干预生成（避免 Round 16 过度重写
的覆辙），也不抛错（失败被上游吞掉，不影响主回合）。

观测哪些（按可靠度从高到低）：
1. generation_parameters 达标：字数/段落/标题/强调/行动选项数——纯机械，100% 可靠。
2. forbidden_reveals 整串命中：当前幕 forbidden_reveals 是否被原样写进输出。
   **整串匹配**（绝不滑动窗口子串，Round 16 教训）。高精度低召回：命中基本确实
   是提前揭露；未命中不代表安全（概念性揭露可能换了措辞）。
3. canon_terms 使用度：每个专名是否在 narrative 出现，统计被冷落的专名（canon
   一致性的弱代理信号——长期 0 出现可能意味着 GM 在用别的说法）。
4. 核心角色提及：哪些剧本角色（name + aliases，整串）在本回合出现。纯观测。

不做（v1）：在场一致性（state.present_npcs 数据常空，噪声大，留 v1.1）。
"""

from __future__ import annotations

import re
from typing import Any

# 场景标题：行首 ### 或 ####（gm_runtime.md 受控 Markdown 契约）。
_HEADING_RE = re.compile(r"^#{3,4}\s+\S", re.MULTILINE)
# 重点强调：成对 **...**（不跨行、内部非空非星号）。
_EMPHASIS_RE = re.compile(r"\*\*[^*\n]+\*\*")
_BIG = 10**9
# 开头重复检测：比较两回合各自前 N 字，公共前缀 >= 阈值则判为"重述同场景"。
_OPENING_WINDOW = 60
_OPENING_REPEAT_MIN_CHARS = 12


def observe_gm_output(
    *,
    narrative: str,
    visible_clues: list[str] | None,
    action_options: list[Any] | None,
    runtime_story: dict[str, Any] | None,
    generation_parameters: dict[str, int] | None,
    previous_narrative: str | None = None,
) -> dict[str, Any]:
    """对一次 GM 输出做确定性观测，返回可 JSON 序列化的观测结果（含人类可读 flags）。"""
    narrative = narrative or ""
    rs = runtime_story if isinstance(runtime_story, dict) else {}
    gp = generation_parameters if isinstance(generation_parameters, dict) else {}
    clues = visible_clues or []
    options = action_options or []

    # 全文（narrative + 线索 + 选项 label）用于 forbidden / 角色 检测。
    option_labels = [_option_label(option) for option in options]
    full_text = "\n".join([narrative, "\n".join(clues), "\n".join(option_labels)])

    generation, gen_flags = _observe_generation(narrative, options, gp)
    forbidden_hits = _observe_forbidden(full_text, rs)
    canon = _observe_canon(narrative, rs)
    characters_mentioned = _observe_characters(full_text, rs)
    opening_repeat = _observe_opening_repeat(narrative, previous_narrative or "")

    flags = list(gen_flags)
    if forbidden_hits:
        flags.append("命中当前幕禁止揭露项（整串）：" + "、".join(forbidden_hits[:5]))
    if opening_repeat["repeat_chars"] >= _OPENING_REPEAT_MIN_CHARS:
        flags.append(
            f"开头与上一回合重复 {opening_repeat['repeat_chars']} 字"
            f"（疑似重述同场景）：{opening_repeat['repeat_text'][:40]}"
        )

    return {
        "generation": generation,
        "forbidden_reveal_hits": forbidden_hits,
        "canon": canon,
        "characters_mentioned": characters_mentioned,
        "opening_repeat": opening_repeat,
        "flags": flags,
    }


def _observe_opening_repeat(narrative: str, previous_narrative: str) -> dict[str, Any]:
    """检测本回合开头是否逐字重复上一回合开头（GM 在同场景重述场景标题/开场环境）。

    取两回合各自的开头窗口做最长公共前缀式匹配（整串、去除两端空白后比较）。这是
    "新回合带上一回合内容"的主要机制（见 Round 20b 诊断）。只观测、写 flag，不重写。
    """
    cur = (narrative or "").strip()
    prev = (previous_narrative or "").strip()
    if not cur or not prev:
        return {"repeat_chars": 0, "repeat_text": ""}
    head_cur = cur[:_OPENING_WINDOW]
    head_prev = prev[:_OPENING_WINDOW]
    # 逐字符求公共前缀长度。
    common = 0
    for a, b in zip(head_cur, head_prev, strict=False):
        if a != b:
            break
        common += 1
    return {"repeat_chars": common, "repeat_text": cur[:common]}


def _observe_generation(
    narrative: str,
    options: list[Any],
    gp: dict[str, int],
) -> tuple[dict[str, Any], list[str]]:
    chars = len(narrative)
    paragraphs = _count_paragraphs(narrative)
    headings = len(_HEADING_RE.findall(narrative))
    emphasis = len(_EMPHASIS_RE.findall(narrative))
    option_count = len(options)

    min_chars = int(gp.get("narrative_min_chars", 0) or 0)
    target_min = int(gp.get("narrative_target_min_chars", 0) or 0)
    target_max = int(gp.get("narrative_target_max_chars", _BIG) or _BIG)
    para_min = int(gp.get("paragraph_min", 0) or 0)
    para_max = int(gp.get("paragraph_max", _BIG) or _BIG)
    heading_max = int(gp.get("scene_heading_max", _BIG) or _BIG)
    emph_min = int(gp.get("emphasis_min", 0) or 0)
    emph_max = int(gp.get("emphasis_max", _BIG) or _BIG)

    flags: list[str] = []
    if chars < min_chars:
        flags.append(f"narrative 字数 {chars} < 硬下限 {min_chars}")
    if not (para_min <= paragraphs <= para_max):
        flags.append(f"段落数 {paragraphs} 越界 [{para_min},{para_max}]")
    if headings > heading_max:
        flags.append(f"场景标题数 {headings} > 上限 {heading_max}")
    if not (emph_min <= emphasis <= emph_max):
        flags.append(f"强调数 {emphasis} 越界 [{emph_min},{emph_max}]")
    if option_count != 4:
        flags.append(f"行动选项数 {option_count} ≠ 4")

    generation = {
        "narrative_chars": chars,
        "meets_min_chars": chars >= min_chars,
        "in_target_range": target_min <= chars <= target_max,
        "paragraph_count": paragraphs,
        "paragraph_in_range": para_min <= paragraphs <= para_max,
        "scene_heading_count": headings,
        "scene_heading_ok": headings <= heading_max,
        "emphasis_count": emphasis,
        "emphasis_in_range": emph_min <= emphasis <= emph_max,
        "action_option_count": option_count,
        "action_options_ok": option_count == 4,
    }
    return generation, flags


def _observe_forbidden(full_text: str, rs: dict[str, Any]) -> list[str]:
    """当前幕 forbidden_reveals 的整串命中。

    只取 current_act.forbidden_reveals（会被揭露的实体/概念，整串可能 literal 出现）；
    不取 forbidden_drift / must_not_become——那是"方向/题材"描述，不是会出现在剧情里
    的词，整串匹配无意义。
    """
    current_act = rs.get("current_act")
    if not isinstance(current_act, dict):
        return []
    forbidden = _strings(current_act.get("forbidden_reveals"))
    return [term for term in dict.fromkeys(forbidden) if term and term in full_text]


def _observe_canon(narrative: str, rs: dict[str, Any]) -> dict[str, Any]:
    story_core = rs.get("story_core")
    canon_terms = _strings(story_core.get("canon_terms")) if isinstance(story_core, dict) else []
    unused = [term for term in canon_terms if term not in narrative]
    return {
        "total": len(canon_terms),
        "used": len(canon_terms) - len(unused),
        "unused": unused,
    }


def _observe_characters(full_text: str, rs: dict[str, Any]) -> list[str]:
    mentioned: list[str] = []
    for character in _records(rs.get("core_characters")):
        name = str(character.get("name") or "").strip()
        if not name:
            continue
        candidates = [name, *_strings(character.get("aliases"))]
        if any(candidate and candidate in full_text for candidate in candidates):
            mentioned.append(name)
    return mentioned


def _count_paragraphs(narrative: str) -> int:
    """按空行切块，排除纯标题块，统计正文自然段数。"""
    count = 0
    for block in re.split(r"\n\s*\n", narrative):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.lstrip().startswith("#") for line in lines):
            continue  # 纯标题块不算段落
        count += 1
    return count


def _option_label(option: Any) -> str:
    if isinstance(option, dict):
        return str(option.get("label") or "")
    return str(getattr(option, "label", "") or "")


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out
