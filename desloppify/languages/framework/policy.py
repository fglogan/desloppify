"""Policy constants for language plugin validation."""

from __future__ import annotations

REQUIRED_FILES: tuple[str, ...] = (
    "commands.py",
    "extractors.py",
    "phases.py",
    "move.py",
    "review.py",
    "test_coverage.py",
)

REQUIRED_DIRS: tuple[str, ...] = ("detectors", "fixers", "tests")

ALLOWED_SCAN_PROFILES: frozenset[str] = frozenset({"objective", "full", "ci"})
