from __future__ import annotations

from typing import Any

DEFAULT_GENERATION_PARAMETERS: dict[str, int] = {
    "narrative_target_min_chars": 800,
    "narrative_target_max_chars": 1200,
    "narrative_min_chars": 700,
    "paragraph_min": 3,
    "paragraph_max": 6,
    "scene_heading_max": 1,
    "emphasis_min": 2,
    "emphasis_max": 4,
    "recent_turn_excerpt_chars": 420,
}

PARAMETER_RANGES: dict[str, tuple[int, int]] = {
    "narrative_target_min_chars": (100, 10000),
    "narrative_target_max_chars": (100, 12000),
    "narrative_min_chars": (0, 10000),
    "paragraph_min": (1, 30),
    "paragraph_max": (1, 40),
    "scene_heading_max": (0, 8),
    "emphasis_min": (0, 30),
    "emphasis_max": (0, 40),
    "recent_turn_excerpt_chars": (0, 5000),
}


def normalize_generation_parameters(value: Any) -> dict[str, int]:
    parameters = dict(DEFAULT_GENERATION_PARAMETERS)
    if not isinstance(value, dict):
        return parameters

    for key, default in DEFAULT_GENERATION_PARAMETERS.items():
        raw_value = value.get(key, default)
        try:
            numeric_value = int(raw_value)
        except (TypeError, ValueError):
            numeric_value = default
        minimum, maximum = PARAMETER_RANGES[key]
        parameters[key] = min(max(numeric_value, minimum), maximum)

    parameters["narrative_target_max_chars"] = max(
        parameters["narrative_target_min_chars"],
        parameters["narrative_target_max_chars"],
    )
    parameters["narrative_min_chars"] = min(
        parameters["narrative_min_chars"],
        parameters["narrative_target_min_chars"],
    )
    parameters["paragraph_max"] = max(parameters["paragraph_min"], parameters["paragraph_max"])
    parameters["emphasis_max"] = max(parameters["emphasis_min"], parameters["emphasis_max"])
    return parameters
