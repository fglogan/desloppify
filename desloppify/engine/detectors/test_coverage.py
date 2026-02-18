"""Test coverage gap detection — static analysis of test file mapping and quality.

Measures test *need* (what's dangerous without tests) not just test existence,
weighting by blast radius (importer count) so that testing one critical file
moves the score more than testing ten trivial ones.
"""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path

from desloppify.hook_registry import get_lang_hook
from desloppify.utils import PROJECT_ROOT
from desloppify.engine.policy.zones import FileZoneMap, Zone

# Minimum LOC threshold — tiny files don't need dedicated tests
_MIN_LOC = 10

# Max untested modules to report when there are zero tests
_MAX_NO_TESTS_ENTRIES = 50


def detect_test_coverage(
    graph: dict,
    zone_map: FileZoneMap,
    lang_name: str,
    extra_test_files: set[str] | None = None,
    complexity_map: dict[str, float] | None = None,
) -> tuple[list[dict], int]:
    """Detect test coverage gaps.

    Args:
        graph: dep graph from lang.build_dep_graph — {filepath: {"imports": set, "importer_count": int, ...}}
        zone_map: FileZoneMap from LangRun.zone_map
        lang_name: language plugin name (for loading language-specific coverage hooks)
        extra_test_files: test files outside the scanned path (e.g. PROJECT_ROOT/tests/)
        complexity_map: {filepath: complexity_score} from structural phase — files above
            _COMPLEXITY_TIER_UPGRADE threshold get their tier upgraded to 2

    Returns:
        (entries, potential) where entries are finding-like dicts and potential
        is LOC-weighted (sqrt(loc) capped at 50 per file).
    """
    # Normalize graph paths to relative (zone_map uses relative paths, graph may use absolute)
    root_prefix = str(PROJECT_ROOT) + os.sep

    def _to_rel(p: str) -> str:
        return p[len(root_prefix) :] if p.startswith(root_prefix) else p

    needs_norm = any(k.startswith(root_prefix) for k in list(graph)[:3])
    if needs_norm:
        norm_graph: dict = {}
        for k, v in graph.items():
            rk = _to_rel(k)
            norm_graph[rk] = {
                **v,
                "imports": {_to_rel(imp) for imp in v.get("imports", set())},
            }
        graph = norm_graph

    all_files = zone_map.all_files()
    production_files = set(
        zone_map.include_only(all_files, Zone.PRODUCTION, Zone.SCRIPT)
    )
    test_files = set(zone_map.include_only(all_files, Zone.TEST))

    # Include test files from outside the scanned path (normalize to relative)
    if extra_test_files:
        test_files |= {_to_rel(f) for f in extra_test_files}

    # Only score production files that are substantial and have testable logic.
    # Excludes type-only files, barrel re-exports, and declaration-only files.
    scorable = {
        f
        for f in production_files
        if _file_loc(f) >= _MIN_LOC and _has_testable_logic(f, lang_name)
    }

    if not scorable:
        return [], 0

    # LOC-weighted potential: sqrt(loc) capped at 50 per file.
    # This weights large untested files more heavily — a 500-LOC untested file
    # contributes ~22x more to score impact than a 15-LOC file.
    potential = round(sum(min(math.sqrt(_file_loc(f)), 50) for f in scorable))

    # If zero test files, emit findings for top modules by LOC
    if not test_files:
        entries = _no_tests_findings(scorable, graph, lang_name, complexity_map)
        return entries, potential

    # Step 1: Import-based mapping (precise)
    directly_tested = _import_based_mapping(
        graph, test_files, production_files, lang_name
    )

    # Step 2: Naming convention fallback
    name_tested = _naming_based_mapping(test_files, production_files, lang_name)
    directly_tested |= name_tested

    # Step 3: Transitive coverage via BFS
    transitively_tested = _transitive_coverage(directly_tested, graph, production_files)

    # Step 4: Test quality analysis
    test_quality = _analyze_test_quality(test_files, lang_name)

    # Step 5: Generate findings
    entries = _generate_findings(
        scorable,
        directly_tested,
        transitively_tested,
        test_quality,
        graph,
        lang_name,
        complexity_map=complexity_map,
    )

    return entries, potential


# ── Internal helpers ──────────────────────────────────────


def _file_loc(filepath: str) -> int:
    """Count lines in a file, returning 0 on error."""
    try:
        return len(Path(filepath).read_text().splitlines())
    except (OSError, UnicodeDecodeError):
        return 0


def _loc_weight(loc: int) -> float:
    """Compute LOC weight for a file: sqrt(loc) capped at 50."""
    return min(math.sqrt(loc), 50)


def _has_testable_logic(filepath: str, lang_name: str) -> bool:
    """Check whether a file contains runtime logic worth testing.

    Returns False for files that need no dedicated tests:
    - .d.ts type definition files (TypeScript)
    - Files containing only type/interface declarations and imports
    - Barrel files containing only re-exports
    - Python files with no function or method definitions
    """
    try:
        content = Path(filepath).read_text()
    except (OSError, UnicodeDecodeError):
        return True  # assume testable if unreadable

    mod = _load_lang_test_coverage_module(lang_name)
    has_logic = getattr(mod, "has_testable_logic", None)
    if callable(has_logic):
        return bool(has_logic(filepath, content))
    return True


def _load_lang_test_coverage_module(lang_name: str):
    """Load language-specific test coverage helpers from ``lang/<name>/test_coverage.py``."""
    return get_lang_hook(lang_name, "test_coverage") or object()


def _no_tests_findings(
    scorable: set[str],
    graph: dict,
    complexity_map: dict[str, float] | None = None,
) -> list[dict]:
    """Generate findings when there are zero test files."""
    cmap = complexity_map or {}
    # Sort by LOC descending, take top N
    by_loc = sorted(scorable, key=lambda f: -_file_loc(f))
    entries = []
    for f in by_loc[:_MAX_NO_TESTS_ENTRIES]:
        loc = _file_loc(f)
        ic = graph.get(f, {}).get("importer_count", 0)
        is_runtime_entry = _is_runtime_entrypoint(f, lang_name)
        if is_runtime_entry:
            entries.append({
                "file": f,
                "name": "runtime_entrypoint_no_direct_tests",
                "tier": 3,
                "confidence": "medium",
                "summary": (f"Runtime entrypoint ({loc} LOC, {ic} importers) — "
                            f"externally invoked; no direct tests found"),
                "detail": {
                    "kind": "runtime_entrypoint_no_direct_tests",
                    "loc": loc,
                    "importer_count": ic,
                    "loc_weight": 0.0,
                    "entrypoint": True,
                },
            })
            continue
        complexity = cmap.get(f, 0)
        is_complex = complexity >= _COMPLEXITY_TIER_UPGRADE
        is_critical = ic >= 10 or is_complex
        tier = 2 if is_critical else 3
        kind = "untested_critical" if is_critical else "untested_module"
        detail: dict = {
            "kind": kind,
            "loc": loc,
            "importer_count": ic,
            "loc_weight": _loc_weight(loc),
        }
        if is_complex:
            detail["complexity_score"] = complexity
        entries.append(
            {
                "file": f,
                "name": "",
                "tier": tier,
                "confidence": "high",
                "summary": f"Untested module ({loc} LOC, {ic} importers) — no test files found",
                "detail": detail,
            }
        )
    return entries


from desloppify.engine.detectors.coverage.mapping import _analyze_test_quality, _get_test_files_for_prod, _import_based_mapping, _naming_based_mapping, _transitive_coverage

# Complexity score threshold for upgrading test coverage tier.
# Files above this are risky enough without tests to warrant tier 2.
_COMPLEXITY_TIER_UPGRADE = 20


def _quality_risk_level(loc: int, importer_count: int, complexity: float) -> str:
    """Classify module test-risk level for quality confidence gating."""
    if importer_count >= 10 or complexity >= _COMPLEXITY_TIER_UPGRADE or loc >= 400:
        return "high"
    if importer_count >= 4 or complexity >= 12 or loc >= 200:
        return "medium"
    return "low"


def _quality_threshold(risk: str) -> float:
    """Minimum acceptable test quality score by risk level."""
    return {"high": 0.60, "medium": 0.50}.get(risk, 0.35)


def _generate_findings(
    scorable: set[str],
    directly_tested: set[str],
    transitively_tested: set[str],
    test_quality: dict[str, dict],
    graph: dict,
    lang_name: str,
    complexity_map: dict[str, float] | None = None,
) -> list[dict]:
    """Generate test coverage findings from the analysis results."""
    entries: list[dict] = []
    cmap = complexity_map or {}
    test_files = set(test_quality.keys())

    for f in scorable:
        loc = _file_loc(f)
        ic = graph.get(f, {}).get("importer_count", 0)
        lw = _loc_weight(loc)

        if f in directly_tested:
            related_tests = _get_test_files_for_prod(f, test_files, graph, lang_name)
            quality_scores: list[float] = []
            total_negative_path = 0
            total_behavioral = 0
            total_assertions = 0
            for tf in related_tests:
                tq = test_quality.get(tf)
                if tq is None:
                    continue
                finding = _quality_issue_finding(prod_file=f, test_file=tf, quality=tq, loc_weight=lw)
                if finding:
                    entries.append(finding)
            continue

        complexity = cmap.get(f, 0)
        if f in transitively_tested:
            entries.append(
                _transitive_coverage_gap_finding(
                    file_path=f,
                    loc=loc,
                    importer_count=ic,
                    loc_weight=lw,
                    complexity=complexity,
                )
            )
            continue

        entries.append(
            _untested_module_finding(
                file_path=f,
                loc=loc,
                importer_count=ic,
                loc_weight=lw,
                complexity=complexity,
            )
        )

    return entries


def _quality_issue_finding(
    *,
    prod_file: str,
    test_file: str,
    quality: dict,
    loc_weight: float,
) -> dict | None:
    """Build a finding for low-quality direct tests."""
    basename = os.path.basename(test_file)
    quality_kind = quality.get("quality")
    if quality_kind == "assertion_free":
        return {
            "file": prod_file,
            "name": f"assertion_free::{basename}",
            "tier": 3,
            "confidence": "medium",
            "summary": (
                f"Assertion-free test: {basename} has "
                f"{quality['test_functions']} test functions but 0 assertions"
            ),
            "detail": {
                "kind": "assertion_free_test",
                "test_file": test_file,
                "test_functions": quality["test_functions"],
                "loc_weight": loc_weight,
            },
        }
    if quality_kind == "placeholder_smoke":
        return {
            "file": prod_file,
            "name": f"placeholder::{basename}",
            "tier": 2,
            "confidence": "high",
            "summary": (
                f"Placeholder smoke test: {basename} relies on tautological assertions "
                "and likely inflates coverage confidence"
            ),
            "detail": {
                "kind": "placeholder_test",
                "test_file": test_file,
                "assertions": quality["assertions"],
                "test_functions": quality["test_functions"],
                "loc_weight": loc_weight,
            },
        }
    if quality_kind == "smoke":
        return {
            "file": prod_file,
            "name": f"shallow::{basename}",
            "tier": 3,
            "confidence": "medium",
            "summary": (
                f"Shallow tests: {basename} has {quality['assertions']} assertions across "
                f"{quality['test_functions']} test functions"
            ),
            "detail": {
                "kind": "shallow_tests",
                "test_file": test_file,
                "assertions": quality["assertions"],
                "test_functions": quality["test_functions"],
                "loc_weight": loc_weight,
            },
        }
    if quality_kind == "over_mocked":
        return {
            "file": prod_file,
            "name": f"over_mocked::{basename}",
            "tier": 3,
            "confidence": "low",
            "summary": (
                f"Over-mocked tests: {basename} has "
                f"{quality['mocks']} mocks vs {quality['assertions']} assertions"
            ),
            "detail": {
                "kind": "over_mocked",
                "test_file": test_file,
                "mocks": quality["mocks"],
                "assertions": quality["assertions"],
                "loc_weight": loc_weight,
            },
        }
    if quality_kind == "snapshot_heavy":
        return {
            "file": prod_file,
            "name": f"snapshot_heavy::{basename}",
            "tier": 3,
            "confidence": "low",
            "summary": (
                f"Snapshot-heavy tests: {basename} has {quality['snapshots']} snapshots vs "
                f"{quality['assertions']} assertions"
            ),
            "detail": {
                "kind": "snapshot_heavy",
                "test_file": test_file,
                "snapshots": quality["snapshots"],
                "assertions": quality["assertions"],
                "loc_weight": loc_weight,
            },
        }
    return None


def _transitive_coverage_gap_finding(
    *,
    file_path: str,
    loc: int,
    importer_count: int,
    loc_weight: float,
    complexity: float,
) -> dict:
    """Build finding for modules covered only via transitive tests."""
    is_complex = complexity >= _COMPLEXITY_TIER_UPGRADE
    detail: dict = {
        "kind": "transitive_only",
        "loc": loc,
        "importer_count": importer_count,
        "loc_weight": loc_weight,
    }
    if is_complex:
        detail["complexity_score"] = complexity
    return {
        "file": file_path,
        "name": "transitive_only",
        "tier": 2 if (importer_count >= 10 or is_complex) else 3,
        "confidence": "medium",
        "summary": (
            f"No direct tests ({loc} LOC, {importer_count} importers) "
            "— covered only via imports from tested modules"
        ),
        "detail": detail,
    }


def _untested_module_finding(
    *,
    file_path: str,
    loc: int,
    importer_count: int,
    loc_weight: float,
    complexity: float,
) -> dict:
    """Build finding for modules with no direct or transitive tests."""
    is_complex = complexity >= _COMPLEXITY_TIER_UPGRADE
    if importer_count >= 10 or is_complex:
        detail: dict = {
            "kind": "untested_critical",
            "loc": loc,
            "importer_count": importer_count,
            "loc_weight": loc_weight,
        }
        if is_complex:
            detail["complexity_score"] = complexity
        return {
            "file": file_path,
            "name": "untested_critical",
            "tier": 2,
            "confidence": "high",
            "summary": (
                f"Untested critical module ({loc} LOC, {importer_count} importers) "
                "— high blast radius"
            ),
            "detail": detail,
        }
    return {
        "file": file_path,
        "name": "untested_module",
        "tier": 3,
        "confidence": "high",
        "summary": f"Untested module ({loc} LOC, {importer_count} importers)",
        "detail": {
            "kind": "untested_module",
            "loc": loc,
            "importer_count": importer_count,
            "loc_weight": loc_weight,
        },
    }
