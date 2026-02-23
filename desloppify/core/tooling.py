"""Tool metadata helpers (hashing, staleness checks)."""

from __future__ import annotations

import hashlib
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent.parent


def compute_tool_hash() -> str:
    """Compute a content hash of all .py files in the desloppify package."""
    digest = hashlib.sha256()
    for py_file in sorted(TOOL_DIR.rglob("*.py")):
        rel_parts = py_file.relative_to(TOOL_DIR).parts
        if "tests" in rel_parts:
            continue
        try:
            digest.update(str(py_file.relative_to(TOOL_DIR)).encode())
            digest.update(py_file.read_bytes())
        except OSError:
            digest.update(f"[unreadable:{py_file.name}]".encode())
            continue
    return digest.hexdigest()[:12]


def check_tool_staleness(state: dict) -> str | None:
    """Return warning if tool code has changed since last scan."""
    stored = state.get("tool_hash")
    if not stored:
        return None
    current = compute_tool_hash()
    if current != stored:
        return (
            f"Tool code changed since last scan (was {stored}, now {current}). "
            "Consider re-running: desloppify scan"
        )
    return None


__all__ = ["TOOL_DIR", "check_tool_staleness", "compute_tool_hash"]
