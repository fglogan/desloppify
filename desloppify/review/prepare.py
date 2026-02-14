"""Review preparation: prepare_review, prepare_holistic_review, batches."""

from __future__ import annotations

from pathlib import Path

from .. import utils as _utils_mod
from ..utils import rel, enable_file_cache, disable_file_cache, _read_file_text
from .context import (
    build_review_context, build_holistic_context, _serialize_context,
    _abs, _dep_graph_lookup, _importer_count,
)
from .selection import (
    select_files_for_review, _get_file_findings, _count_fresh, _count_stale,
)
from .dimensions import (
    DEFAULT_DIMENSIONS, DIMENSION_PROMPTS,
    HOLISTIC_DIMENSIONS, HOLISTIC_DIMENSION_PROMPTS,
    REVIEW_SYSTEM_PROMPT, HOLISTIC_REVIEW_SYSTEM_PROMPT,
    LANG_GUIDANCE,
)


def _rel_list(s) -> list[str]:
    """Normalize a set or list of paths to sorted relative paths (max 10)."""
    if isinstance(s, set):
        return sorted(rel(x) for x in s)[:10]
    return [rel(x) for x in list(s)[:10]]


def prepare_review(path: Path, lang, state: dict, *,
                   max_files: int = 50, max_age_days: int = 30,
                   force_refresh: bool = False,
                   dimensions: list[str] | None = None,
                   files: list[str] | None = None) -> dict:
    """Prepare review data for agent consumption. Returns structured dict.

    If *files* is provided, skip file_finder (avoids redundant filesystem walks
    when the caller already has the file list, e.g. from _setup_lang).
    """
    all_files = files if files is not None else (
        lang.file_finder(path) if lang.file_finder else []
    )

    # Enable file cache for entire prepare operation — context building,
    # file selection, and content extraction all read the same files.
    already_cached = _utils_mod._cache_enabled
    if not already_cached:
        enable_file_cache()
    try:
        context = build_review_context(path, lang, state, files=all_files)
        selected = select_files_for_review(lang, path, state,
                                           max_files=max_files,
                                           max_age_days=max_age_days,
                                           force_refresh=force_refresh,
                                           files=all_files)
        file_requests = _build_file_requests(selected, lang, state)
    finally:
        if not already_cached:
            disable_file_cache()

    dims = dimensions or DEFAULT_DIMENSIONS
    lang_guide = LANG_GUIDANCE.get(lang.name, {})

    return {
        "command": "review",
        "language": lang.name,
        "dimensions": dims,
        "dimension_prompts": {d: DIMENSION_PROMPTS[d] for d in dims if d in DIMENSION_PROMPTS},
        "lang_guidance": lang_guide,
        "context": _serialize_context(context),
        "system_prompt": REVIEW_SYSTEM_PROMPT,
        "files": file_requests,
        "total_candidates": len(file_requests),
        "cache_status": {
            "fresh": _count_fresh(state, max_age_days),
            "stale": _count_stale(state, max_age_days),
            "new": len(file_requests),
        },
    }


def _build_file_requests(files: list[str], lang, state: dict) -> list[dict]:
    """Build per-file review request dicts."""
    file_requests = []
    for filepath in files:
        content = _read_file_text(_abs(filepath))
        if content is None:
            continue

        rpath = rel(filepath)
        zone = "production"
        if lang._zone_map is not None:
            zone = lang._zone_map.get(filepath).value

        # Get import neighbors for context
        neighbors: dict = {}
        if lang._dep_graph:
            entry = _dep_graph_lookup(lang._dep_graph, filepath)
            imports_raw = entry.get("imports", set())
            importers_raw = entry.get("importers", set())
            neighbors = {
                "imports": _rel_list(imports_raw),
                "importers": _rel_list(importers_raw),
                "importer_count": _importer_count(entry),
            }

        file_requests.append({
            "file": rpath,
            "content": content,
            "zone": zone,
            "loc": len(content.splitlines()),
            "neighbors": neighbors,
            "existing_findings": _get_file_findings(state, filepath),
        })
    return file_requests


# ── Holistic review preparation ──────────────────────────────────

_HOLISTIC_WORKFLOW = [
    "Read .desloppify/query.json for context, excerpts, and investigation batches",
    "For each batch: read the listed files, evaluate the batch's dimensions (batches are independent — parallelize)",
    "Cross-reference findings with the sibling_behavior and convention data",
    "For simple issues (missing import, wrong name): fix directly in code, then note as resolved",
    "For cross-cutting issues: write to findings.json (format described in system_prompt)",
    "Import: desloppify review --import findings.json --holistic",
    "Run `desloppify issues` to see the work queue, then fix each finding and resolve",
]


def prepare_holistic_review(path: Path, lang, state: dict, *,
                            dimensions: list[str] | None = None,
                            files: list[str] | None = None) -> dict:
    """Prepare holistic review data for agent consumption. Returns structured dict."""
    all_files = files if files is not None else (
        lang.file_finder(path) if lang.file_finder else []
    )

    already_cached = _utils_mod._cache_enabled
    if not already_cached:
        enable_file_cache()
    try:
        context = build_holistic_context(path, lang, state, files=all_files)
        # Also include per-file review context for reference
        review_ctx = build_review_context(path, lang, state, files=all_files)
    finally:
        if not already_cached:
            disable_file_cache()

    dims = dimensions or HOLISTIC_DIMENSIONS
    lang_guide = LANG_GUIDANCE.get(lang.name, {})
    batches = _build_investigation_batches(context, lang)

    return {
        "command": "review",
        "mode": "holistic",
        "language": lang.name,
        "dimensions": dims,
        "dimension_prompts": {d: HOLISTIC_DIMENSION_PROMPTS[d]
                              for d in dims if d in HOLISTIC_DIMENSION_PROMPTS},
        "lang_guidance": lang_guide,
        "holistic_context": context,
        "review_context": _serialize_context(review_ctx),
        "system_prompt": HOLISTIC_REVIEW_SYSTEM_PROMPT,
        "total_files": context.get("codebase_stats", {}).get("total_files", 0),
        "workflow": _HOLISTIC_WORKFLOW,
        "investigation_batches": batches,
    }


def _build_investigation_batches(holistic_ctx: dict, lang) -> list[dict]:
    """Derive up to 6 independent, parallelizable investigation batches from context.

    Each batch groups related dimensions and the files an agent should read.
    Max 15 files per batch, deduplicated. Batches 5-6 only appear when
    authorization/migration context data is non-empty.
    """
    def _collect(sources: list[list[dict]], key: str = "file") -> list[str]:
        """Collect unique file paths from multiple source lists."""
        seen: set[str] = set()
        out: list[str] = []
        for src in sources:
            for item in src:
                f = item.get(key, "")
                if f and f not in seen:
                    seen.add(f)
                    out.append(f)
        return out[:15]

    arch = holistic_ctx.get("architecture", {})
    coupling = holistic_ctx.get("coupling", {})
    conventions = holistic_ctx.get("conventions", {})
    abstractions = holistic_ctx.get("abstractions", {})
    deps = holistic_ctx.get("dependencies", {})
    testing = holistic_ctx.get("testing", {})
    api = holistic_ctx.get("api_surface", {})

    # Batch 1: Architecture & Coupling
    god_modules = arch.get("god_modules", [])
    module_io = coupling.get("module_level_io", [])
    batch1_files = _collect([god_modules, module_io])
    batch1 = {
        "name": "Architecture & Coupling",
        "dimensions": ["cross_module_architecture", "initialization_coupling"],
        "files_to_read": batch1_files,
        "why": "god modules, import-time side effects",
    }

    # Batch 2: Conventions & Errors — sibling behavior outliers
    sibling = conventions.get("sibling_behavior", {})
    outlier_files = []
    for dir_info in sibling.values():
        for o in dir_info.get("outliers", []):
            outlier_files.append({"file": o["file"]})
    # Also include dirs with mixed error strategies (top 5 by count)
    errors = holistic_ctx.get("errors", {})
    error_dirs = errors.get("strategy_by_directory", {})
    mixed_error_files: list[dict] = []
    for dir_name, strategies in error_dirs.items():
        if len(strategies) >= 3:  # Multiple strategies = potential inconsistency
            mixed_error_files.append({"file": dir_name})
    batch2_files = _collect([outlier_files, mixed_error_files])
    batch2 = {
        "name": "Conventions & Errors",
        "dimensions": ["convention_outlier", "error_consistency"],
        "files_to_read": batch2_files,
        "why": "naming drift, behavioral outliers, mixed error strategies",
    }

    # Batch 3: Abstractions & Dependencies
    util_files = abstractions.get("util_files", [])
    # Files involved in cycles (from dependency summaries)
    cycle_files: list[dict] = []
    for summary in deps.get("cycle_summaries", []):
        for token in summary.split():
            if "/" in token and "." in token:
                cycle_files.append({"file": token.strip(",'\"")})
    batch3_files = _collect([util_files, cycle_files])
    batch3 = {
        "name": "Abstractions & Dependencies",
        "dimensions": ["abstraction_fitness", "dependency_health"],
        "files_to_read": batch3_files,
        "why": "util dumping grounds, dep cycles",
    }

    # Batch 4: Testing & API
    critical_untested = testing.get("critical_untested", [])
    sync_async = [{"file": f} for f in api.get("sync_async_mix", [])]
    batch4_files = _collect([critical_untested, sync_async])
    batch4 = {
        "name": "Testing & API",
        "dimensions": ["test_strategy", "api_surface_coherence"],
        "files_to_read": batch4_files,
        "why": "critical untested paths, API inconsistency",
    }

    # Batch 5: Authorization (only when auth context exists)
    auth_ctx = holistic_ctx.get("authorization", {})
    auth_files: list[dict] = []
    # Route files with auth gaps
    for rpath, info in auth_ctx.get("route_auth_coverage", {}).items():
        if info.get("without_auth", 0) > 0:
            auth_files.append({"file": rpath})
    # Service role files
    for rpath in auth_ctx.get("service_role_usage", []):
        auth_files.append({"file": rpath})
    batch5_files = _collect([auth_files])
    batch5 = {
        "name": "Authorization",
        "dimensions": ["authorization_consistency"],
        "files_to_read": batch5_files,
        "why": "auth gaps, service role usage, RLS coverage",
    }

    # Batch 6: AI Debt & Migrations (only when signals exist)
    ai_debt = holistic_ctx.get("ai_debt_signals", {})
    migration = holistic_ctx.get("migration_signals", {})
    debt_files: list[dict] = []
    for rpath in ai_debt.get("file_signals", {}):
        debt_files.append({"file": rpath})
    for entry in migration.get("deprecated_markers", {}).get("files", {}).keys() if isinstance(migration.get("deprecated_markers", {}).get("files"), dict) else []:
        debt_files.append({"file": entry})
    for entry in migration.get("migration_todos", []):
        debt_files.append({"file": entry.get("file", "")})
    batch6_files = _collect([debt_files])
    batch6 = {
        "name": "AI Debt & Migrations",
        "dimensions": ["ai_generated_debt", "incomplete_migration"],
        "files_to_read": batch6_files,
        "why": "AI-generated patterns, deprecated markers, migration TODOs",
    }

    return [b for b in [batch1, batch2, batch3, batch4, batch5, batch6] if b["files_to_read"]]
