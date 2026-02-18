"""Shared language-level holistic review dimension defaults."""

from __future__ import annotations

HOLISTIC_REVIEW_DIMENSIONS: list[str] = [
    "cross_module_architecture",
    "convention_outlier",
    "error_consistency",
    "abstraction_fitness",
    "api_surface_coherence",
    "authorization_consistency",
    "ai_generated_debt",
    "incomplete_migration",
    "package_organization",
    "high_level_elegance",
    "mid_level_elegance",
    "low_level_elegance",
]

__all__ = ["HOLISTIC_REVIEW_DIMENSIONS"]
