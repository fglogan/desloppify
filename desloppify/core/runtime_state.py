"""Mutable process-wide runtime state shared by utility helpers."""

from __future__ import annotations

from pathlib import Path


class ExclusionConfig:
    """In-memory exclusion configuration shared across scans."""

    def __init__(self) -> None:
        self.values: tuple[str, ...] = ()


class FileTextCache:
    """Optional read-through file-text cache used by scan/review passes."""

    def __init__(self) -> None:
        self._enabled = False
        self._values: dict[str, str | None] = {}

    def enable(self) -> None:
        self._enabled = True
        self._values.clear()

    def disable(self) -> None:
        self._enabled = False
        self._values.clear()

    def read(self, filepath: str) -> str | None:
        if self._enabled and filepath in self._values:
            return self._values[filepath]

        try:
            content = Path(filepath).read_text(errors="replace")
        except OSError:
            content = None
        if self._enabled:
            self._values[filepath] = content
        return content


class CacheEnabledFlag:
    """Mutable bool-like wrapper to avoid rebinding during tests."""

    def __init__(self) -> None:
        self.value = False

    def set(self, enabled: bool) -> None:
        self.value = enabled

    def __bool__(self) -> bool:
        return self.value

    def __repr__(self) -> str:
        return str(self.value)


class SourceFileCache:
    """Small FIFO cache for source-file discovery results."""

    def __init__(self, *, max_entries: int) -> None:
        self.max_entries = max_entries
        self.values: dict[tuple, tuple[str, ...]] = {}

    def get(self, key: tuple) -> tuple[str, ...] | None:
        return self.values.get(key)

    def put(self, key: tuple, value: tuple[str, ...]) -> None:
        if len(self.values) >= self.max_entries:
            self.values.pop(next(iter(self.values)))
        self.values[key] = value

    def clear(self) -> None:
        self.values.clear()


EXCLUSION_CONFIG = ExclusionConfig()
FILE_TEXT_CACHE = FileTextCache()
CACHE_ENABLED = CacheEnabledFlag()
SOURCE_FILE_CACHE = SourceFileCache(max_entries=16)


__all__ = [
    "CACHE_ENABLED",
    "EXCLUSION_CONFIG",
    "FILE_TEXT_CACHE",
    "SOURCE_FILE_CACHE",
    "CacheEnabledFlag",
    "ExclusionConfig",
    "FileTextCache",
    "SourceFileCache",
]
