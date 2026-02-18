"""Holistic review dimension definitions and system prompt."""

from __future__ import annotations

from desloppify.intelligence.review.dimensions.data import load_holistic_dimensions

(
    HOLISTIC_DIMENSIONS,
    HOLISTIC_DIMENSION_PROMPTS,
    HOLISTIC_REVIEW_SYSTEM_PROMPT,
) = load_holistic_dimensions()
