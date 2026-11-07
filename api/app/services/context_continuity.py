"""Bounded recent prose and removable observations; no model calls or state writes."""

from __future__ import annotations

from typing import Any

from app.services.output_observer import observe_gm_output


def recent_narrative_excerpt(value: str | None, limit: int) -> str:
    """Keep the opening and the actual last beat within the existing character budget."""
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    separator = "\n…（中段省略）…\n"
    if limit <= len(separator):
        return text[-max(1, limit) :]
    head = (limit - len(separator)) // 3
    tail = limit - len(separator) - head
    return text[:head] + separator + text[-tail:]


def recent_continuity_facts(turns: list[Any]) -> dict[str, Any]:
    """Report only consecutive observed repetition, withdrawing after recovery.

    Reuse the existing observer's exact-prefix measurement. These counts are
    context, not a semantic drift verdict or an automatic rewrite instruction.
    """
    if len(turns) < 3:
        return {}
    recent = turns[-3:]
    observations = [
        observe_gm_output(
            narrative=current.gm_output,
            previous_narrative=previous.gm_output,
            visible_clues=[],
            action_options=[],
            runtime_story={},
            generation_parameters={},
        )["opening_repeat"]
        for previous, current in zip(recent, recent[1:], strict=False)
    ]
    if not all(item["repeat_chars"] >= 12 for item in observations):
        return {}
    return {
        "opening_repeat_chars": [item["repeat_chars"] for item in observations],
        "turn_numbers": [turn.turn_number for turn in recent[1:]],
    }
