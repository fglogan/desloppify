"""Per-file review dimension definitions and system prompt."""

from __future__ import annotations

from desloppify.intelligence.review.dimensions.data import load_per_file_dimensions

DEFAULT_DIMENSIONS, DIMENSION_PROMPTS, REVIEW_SYSTEM_PROMPT = load_per_file_dimensions()
