"""Pattern → finding-ID resolution for plan commands."""

from __future__ import annotations

from desloppify.engine._state.resolution import match_findings
from desloppify.engine._state.schema import StateModel


def resolve_ids_from_patterns(
    state: StateModel,
    patterns: list[str],
    *,
    status_filter: str = "open",
) -> list[str]:
    """Resolve one or more patterns to a deduplicated list of finding IDs."""
    seen: set[str] = set()
    result: list[str] = []
    for pattern in patterns:
        matches = match_findings(state, pattern, status_filter=status_filter)
        for finding in matches:
            fid = finding["id"]
            if fid not in seen:
                seen.add(fid)
                result.append(fid)
    return result


__all__ = ["resolve_ids_from_patterns"]
