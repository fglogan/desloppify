"""Shared detector output contract for TypeScript detector entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

TEntry = TypeVar("TEntry")


@dataclass(frozen=True)
class DetectorResult(Generic[TEntry]):
    """Normalized detector output with explicit population semantics."""

    entries: list[TEntry]
    population_kind: str
    population_size: int

    def as_tuple(self) -> tuple[list[TEntry], int]:
        """Backwards-compatible tuple view used by existing callers."""
        return self.entries, self.population_size


def as_legacy_tuple(result: DetectorResult[TEntry]) -> tuple[list[TEntry], int]:
    """Explicit adapter for legacy tuple-returning detector entrypoints."""
    return result.entries, result.population_size


__all__ = ["DetectorResult", "as_legacy_tuple"]
