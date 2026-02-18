"""Shared subjective-integrity utilities used across commands and scoring."""

from __future__ import annotations

SUBJECTIVE_TARGET_MATCH_TOLERANCE = 0.05


def matches_target_score(
    score: object,
    target: object,
    *,
    tolerance: float = SUBJECTIVE_TARGET_MATCH_TOLERANCE,
) -> bool:
    """Return True when score is within tolerance of target."""
    try:
        score_value = float(score)
        target_value = float(target)
        tolerance_value = max(0.0, float(tolerance))
    except (TypeError, ValueError):
        return False
    return abs(score_value - target_value) <= tolerance_value
