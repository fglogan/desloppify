"""Shared mutable registry state for language plugin discovery."""

from __future__ import annotations

_registry: dict[str, type] = {}
_load_attempted = False
_load_errors: dict[str, BaseException] = {}
