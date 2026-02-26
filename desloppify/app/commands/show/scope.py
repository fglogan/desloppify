"""Scope and queue helpers for show command selection."""

from __future__ import annotations

from desloppify import scoring as scoring_mod
from desloppify import state as state_mod
from desloppify.engine.work_queue import (
    QueueBuildOptions,
    build_work_queue,
)
from desloppify.core.output_api import colorize


def _build_dimension_lookup() -> dict[str, list[str]]:
    """Build a map from dimension name/key (lowered) to detector names."""
    lookup: dict[str, list[str]] = {}
    for dim in scoring_mod.DIMENSIONS:
        detectors = list(dim.detectors) if hasattr(dim, "detectors") else []
        lookup[dim.name.lower()] = detectors
        # Also index by underscore key: "file_health" -> detectors
        key = dim.name.lower().replace(" ", "_")
        if key not in lookup:
            lookup[key] = detectors
    # Also add DISPLAY_NAMES reverse lookup (e.g. "abstraction_fit" -> "Abstraction Fit")
    for key, display in scoring_mod.DISPLAY_NAMES.items():
        normalized_key = key.lower().replace(" ", "_")
        normalized_display = display.lower()
        # Find which dimension this belongs to via get_dimension_for_detector or direct name match
        for dim in scoring_mod.DIMENSIONS:
            dim_lower = dim.name.lower()
            if normalized_display == dim_lower or normalized_key == dim_lower.replace(" ", "_"):
                detectors = list(dim.detectors) if hasattr(dim, "detectors") else []
                if normalized_key not in lookup:
                    lookup[normalized_key] = detectors
                if normalized_display not in lookup:
                    lookup[normalized_display] = detectors
    return lookup


def try_dimension_rewrite(pattern: str) -> str | None:
    """If pattern matches a dimension name/key, return a detector scope. Otherwise None."""
    lookup = _build_dimension_lookup()
    lowered = pattern.lower().replace(" ", "_")
    detectors = lookup.get(lowered)
    if not detectors:
        # Try display name form (with spaces)
        detectors = lookup.get(pattern.lower())
    if not detectors:
        return None
    # Return first detector as scope — the work queue will match on detector name.
    # For multi-detector dimensions, we can't pass multiple scopes through the current
    # interface, but most dimensions have one primary detector. Use glob pattern.
    if len(detectors) == 1:
        return detectors[0]
    # For multi-detector dimensions, use wildcard pattern that scope_matches handles
    return None  # Fall through to load_matches_for_dimension


def load_matches_for_dimension(
    state: dict,
    pattern: str,
    *,
    status_filter: str,
) -> tuple[list[dict], str | None]:
    """Try to load findings matching a dimension name. Returns (matches, rewritten_pattern)."""
    lookup = _build_dimension_lookup()
    lowered = pattern.lower().replace(" ", "_")
    detectors = lookup.get(lowered) or lookup.get(pattern.lower())
    if not detectors:
        return [], None

    # Load findings for each detector in this dimension
    all_matches: list[dict] = []
    for detector in detectors:
        matches = load_matches(
            state, scope=detector, status_filter=status_filter, chronic=False
        )
        all_matches.extend(matches)
    # Deduplicate by finding ID
    seen: set[str] = set()
    unique: list[dict] = []
    for item in all_matches:
        fid = item.get("id", "")
        if fid not in seen:
            seen.add(fid)
            unique.append(item)

    # Find the display name for the dimension
    dim_display = pattern
    for dim in scoring_mod.DIMENSIONS:
        if dim.name.lower() == lowered or dim.name.lower().replace(" ", "_") == lowered:
            dim_display = dim.name
            break

    return unique, dim_display


def _detector_names_hint() -> str:
    """Return a compact list of detector names for the help message."""
    from desloppify.core import registry as registry_mod
    names = getattr(registry_mod, "DISPLAY_ORDER", [])
    if names:
        return ", ".join(names[:10]) + (", ..." if len(names) > 10 else "")
    return "smells, structural, security, review, ..."


def resolve_show_scope(args) -> tuple[bool, str | None, str, str | None]:
    """Resolve scope/pattern/status for a show invocation."""
    chronic = getattr(args, "chronic", False)
    pattern = args.pattern
    status_filter = "open" if chronic else getattr(args, "status", "open")
    if chronic:
        scope = pattern
        pattern = pattern or "<chronic>"
        return True, pattern, status_filter, scope
    if not pattern:
        print(
            colorize(
                "Pattern required (or use --chronic). Try: desloppify show --help",
                "yellow",
            )
        )
        return False, None, status_filter, ""
    return True, pattern, status_filter, pattern


def load_matches(
    state: dict,
    *,
    scope: str | None,
    status_filter: str,
    chronic: bool,
) -> list[dict]:
    """Load matching findings from the ranked queue."""
    queue = build_work_queue(
        state,
        options=QueueBuildOptions(
            count=None,
            scan_path=state.get("scan_path"),
            scope=scope,
            status=status_filter,
            include_subjective=False,
            chronic=chronic,
            no_tier_fallback=True,
        ),
    )
    return [item for item in queue.get("items", []) if item.get("kind") == "finding"]


def resolve_noise(config: dict, matches: list[dict]):
    """Apply detector/global noise budget to show matches."""
    noise_budget, global_noise_budget, budget_warning = (
        state_mod.resolve_finding_noise_settings(config)
    )
    surfaced_matches, hidden_by_detector = state_mod.apply_finding_noise_budget(
        matches,
        budget=noise_budget,
        global_budget=global_noise_budget,
    )
    return (
        surfaced_matches,
        hidden_by_detector,
        noise_budget,
        global_noise_budget,
        budget_warning,
    )


__all__ = [
    "_detector_names_hint",
    "load_matches",
    "load_matches_for_dimension",
    "resolve_noise",
    "resolve_show_scope",
]
