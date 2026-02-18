"""Holistic codebase-wide context gathering for cross-cutting review."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from desloppify import utils as _utils_mod
from desloppify.utils import disable_file_cache, enable_file_cache, read_file_text, rel, resolve_path
from desloppify.intelligence.review.context import file_excerpt, importer_count
from desloppify.intelligence.review.context_internal.patterns import ERROR_PATTERNS as _ERROR_PATTERNS
from desloppify.intelligence.review.context_internal.patterns import FUNC_NAME_RE as _FUNC_NAME_RE
from desloppify.intelligence.review.context_internal.patterns import extract_imported_names as _extract_imported_names
from desloppify.intelligence.review.context_internal.structure import compute_structure_context
from desloppify.intelligence.review.context_internal.models import HolisticContext
from desloppify.intelligence.review.context_signals.ai import gather_ai_debt_signals
from desloppify.intelligence.review.context_signals.auth import gather_auth_context
from desloppify.intelligence.review.context_signals.migration import gather_migration_signals

_DEF_SIGNATURE_RE = re.compile(
    r"(?:^|\n)\s*(?:async\s+def|def|async\s+function|function)\s+\w+\s*\(([^)]*)\)",
    re.MULTILINE,
)
_PY_PASSTHROUGH_RE = re.compile(
    r"\bdef\s+(\w+)\s*\([^)]*\)\s*:\s*(?:\n\s*(?:#.*)?\s*)*\n?\s*return\s+(\w+)\s*\(",
    re.MULTILINE,
)
_TS_PASSTHROUGH_RE = re.compile(
    r"\bfunction\s+(\w+)\s*\([^)]*\)\s*\{\s*return\s+(\w+)\s*\(",
    re.MULTILINE,
)
_INTERFACE_RE = re.compile(
    r"\binterface\s+([A-Za-z_]\w*)\b|\bclass\s+([A-Za-z_]\w*Protocol)\b"
)
_IMPLEMENTS_RE = re.compile(r"\bclass\s+\w+\s+implements\s+([^{:\n]+)")
_INHERITS_RE = re.compile(r"\bclass\s+\w+\s*(?:\(([^)\n]+)\)\s*:|:\s*([^\n{]+))")
_CHAIN_RE = re.compile(r"\b(?:\w+\.){2,}\w+\b")
_CONFIG_BAG_RE = re.compile(
    r"\b(?:config|configs|options|opts|params|ctx|context)\b",
    re.IGNORECASE,
)


def _abs(filepath: str) -> str:
    """Resolve filepath to absolute using resolve_path."""
    return resolve_path(filepath)


def build_holistic_context(
    path: Path,
    lang: object,
    state: dict,
    files: list[str] | None = None,
) -> dict[str, object]:
    """Gather codebase-wide data for holistic review."""
    return build_holistic_context_model(path, lang, state, files=files).to_dict()


def build_holistic_context_model(
    path: Path,
    lang,
    state: dict,
    files: list[str] | None = None,
) -> HolisticContext:
    """Gather holistic context and return a typed context contract."""
    if files is None:
        files = lang.file_finder(path) if lang.file_finder else []

    already_cached = bool(_utils_mod._cache_enabled)
    if not already_cached:
        enable_file_cache()
    try:
        return _build_holistic_context_inner(files, lang, state)
    finally:
        if not already_cached:
            disable_file_cache()


def _read_file_contents(files: list[str]) -> dict[str, str]:
    file_contents: dict[str, str] = {}
    for filepath in files:
        content = read_file_text(_abs(filepath))
        if content is not None:
            file_contents[filepath] = content
    return file_contents


def _architecture_context(lang, file_contents: dict[str, str]) -> dict:
    arch: dict = {}
    if not lang.dep_graph:
        return arch

    importer_counts = {}
    for filepath, entry in lang.dep_graph.items():
        entry_importer_count = importer_count(entry)
        if entry_importer_count > 0:
            importer_counts[rel(filepath)] = entry_importer_count
    top_imported = sorted(importer_counts.items(), key=lambda item: -item[1])[:10]
    arch["god_modules"] = [
        {"file": filepath, "importers": count, "excerpt": file_excerpt(filepath) or ""}
        for filepath, count in top_imported
        if count >= 5
    ]
    arch["top_imported"] = dict(top_imported)
    return arch


def _coupling_context(file_contents: dict[str, str]) -> dict:
    coupling: dict = {}
    module_level_io = []
    for filepath, content in file_contents.items():
        for idx, raw_line in enumerate(content.splitlines()[:50]):
            stripped = raw_line.strip()
            if stripped.startswith(
                ("def ", "class ", "async def ", "if ", "#", "@", "import ", "from ")
            ):
                continue
            if re.search(
                r"\b(?:open|connect|requests?\.|urllib|subprocess|os\.system)\b",
                stripped,
            ):
                module_level_io.append(
                    {
                        "file": rel(filepath),
                        "line": idx + 1,
                        "code": stripped[:100],
                    }
                )
    if module_level_io:
        coupling["module_level_io"] = module_level_io[:20]
    return coupling


def _naming_conventions_context(file_contents: dict[str, str]) -> dict:
    dir_styles: dict[str, Counter] = {}
    for filepath, content in file_contents.items():
        parts = Path(filepath).parts
        if len(parts) < 2:
            continue
        dir_name = parts[-2] + "/"
        counter = dir_styles.setdefault(dir_name, Counter())
        for name in _FUNC_NAME_RE.findall(content):
            if "_" in name and name.islower():
                counter["snake_case"] += 1
            elif name[0].islower() and any(ch.isupper() for ch in name):
                counter["camelCase"] += 1
            elif name[0].isupper():
                counter["PascalCase"] += 1
    return {
        name: dict(counter.most_common(3))
        for name, counter in dir_styles.items()
        if sum(counter.values()) >= 3
    }


def _sibling_behavior_context(file_contents: dict[str, str]) -> dict:
    dir_imports: dict[str, dict[str, set[str]]] = {}
    for filepath, content in file_contents.items():
        parts = Path(filepath).parts
        if len(parts) < 2:
            continue
        dir_name = parts[-2] + "/"
        file_rel = rel(filepath)
        dir_imports.setdefault(dir_name, {})[file_rel] = _extract_imported_names(
            content
        )

    sibling_behavior: dict = {}
    for dir_name, file_names_map in dir_imports.items():
        total = len(file_names_map)
        if total < 3:
            continue
        name_counts: Counter = Counter()
        for names in file_names_map.values():
            for name in names:
                name_counts[name] += 1
        threshold = total * 0.6
        shared = {
            name: count for name, count in name_counts.items() if count >= threshold
        }
        if not shared:
            continue
        outliers = []
        for file_rel, names in file_names_map.items():
            missing = [name for name in shared if name not in names]
            if missing:
                outliers.append({"file": file_rel, "missing": sorted(missing)})
        if not outliers:
            continue
        sibling_behavior[dir_name] = {
            "shared_patterns": {
                name: {"count": count, "total": total}
                for name, count in sorted(shared.items(), key=lambda item: -item[1])
            },
            "outliers": sorted(
                outliers, key=lambda item: len(item["missing"]), reverse=True
            ),
        }
    return sibling_behavior


def _error_strategy_context(file_contents: dict[str, str]) -> dict:
    dir_errors: dict[str, Counter] = {}
    for filepath, content in file_contents.items():
        parts = Path(filepath).parts
        if len(parts) < 2:
            continue
        dir_name = parts[-2] + "/"
        counter = dir_errors.setdefault(dir_name, Counter())
        for pattern_name, pattern in _ERROR_PATTERNS.items():
            matches = pattern.findall(content)
            if matches:
                counter[pattern_name] += len(matches)
    return {
        name: dict(counter.most_common(5))
        for name, counter in dir_errors.items()
        if sum(counter.values()) >= 2
    }


def _count_signature_params(params_blob: str) -> int:
    """Best-effort parameter counting for function signatures."""
    cleaned = params_blob.strip()
    if not cleaned:
        return 0
    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    filtered = [part for part in parts if part not in {"self", "cls", "this"}]
    return len(filtered)


def _extract_type_names(blob: str) -> list[str]:
    """Extract candidate type names from implements/inherits blobs."""
    names: list[str] = []
    for raw in re.split(r"[,\s()]+", blob):
        token = raw.strip()
        if not token:
            continue
        token = token.split(".")[-1]
        token = token.split("<")[0]
        token = token.strip(":")
        if not token or not re.match(r"^[A-Za-z_]\w*$", token):
            continue
        names.append(token)
    return names


def _score_clamped(raw: float) -> int:
    """Clamp score-like values to [0, 100]."""
    return int(max(0, min(100, round(raw))))


def _abstractions_context(file_contents: dict[str, str]) -> dict:
    util_files = []
    wrappers_by_file: list[dict[str, object]] = []
    interface_declarations: dict[str, set[str]] = defaultdict(set)
    implementations: dict[str, set[str]] = defaultdict(set)
    indirection_hotspots: list[dict[str, object]] = []
    wide_param_bags: list[dict[str, object]] = []

    total_function_signatures = 0
    total_wrappers = 0

    for filepath, content in file_contents.items():
        rpath = rel(filepath)
        basename = Path(rpath).stem.lower()
        if basename in {"utils", "helpers", "util", "helper", "common", "misc"}:
            util_files.append(
                {
                    "file": rpath,
                    "loc": len(content.splitlines()),
                    "excerpt": file_excerpt(filepath) or "",
                }
            )

        signatures = _DEF_SIGNATURE_RE.findall(content)
        total_function_signatures += len(signatures)

        py_wrappers = [
            (wrapper, target)
            for wrapper, target in _PY_PASSTHROUGH_RE.findall(content)
            if wrapper != target
        ]
        ts_wrappers = [
            (wrapper, target)
            for wrapper, target in _TS_PASSTHROUGH_RE.findall(content)
            if wrapper != target
        ]
        wrapper_pairs = py_wrappers + ts_wrappers
        if wrapper_pairs:
            total_wrappers += len(wrapper_pairs)
            wrappers_by_file.append(
                {
                    "file": rpath,
                    "count": len(wrapper_pairs),
                    "samples": [f"{w}->{t}" for w, t in wrapper_pairs[:5]],
                }
            )

        for match in _INTERFACE_RE.finditer(content):
            iface = match.group(1) or match.group(2)
            if iface:
                interface_declarations[iface].add(rpath)

        for match in _IMPLEMENTS_RE.finditer(content):
            for iface in _extract_type_names(match.group(1)):
                implementations[iface].add(rpath)
        for match in _INHERITS_RE.finditer(content):
            blob = match.group(1) or match.group(2) or ""
            for iface in _extract_type_names(blob):
                implementations[iface].add(rpath)

        chain_matches = _CHAIN_RE.findall(content)
        max_chain_depth = max((token.count(".") for token in chain_matches), default=0)
        if max_chain_depth >= 3 or len(chain_matches) >= 6:
            indirection_hotspots.append(
                {
                    "file": rpath,
                    "max_chain_depth": max_chain_depth,
                    "chain_count": len(chain_matches),
                }
            )

        wide_functions = sum(
            1 for params_blob in signatures if _count_signature_params(params_blob) >= 7
        )
        bag_mentions = len(_CONFIG_BAG_RE.findall(content))
        if wide_functions > 0 or bag_mentions >= 10:
            wide_param_bags.append(
                {
                    "file": rpath,
                    "wide_functions": wide_functions,
                    "config_bag_mentions": bag_mentions,
                }
            )

    one_impl_interfaces: list[dict[str, object]] = []
    for iface, declared_in in interface_declarations.items():
        implemented_in = sorted(implementations.get(iface, set()))
        if len(implemented_in) != 1:
            continue
        one_impl_interfaces.append(
            {
                "interface": iface,
                "declared_in": sorted(declared_in),
                "implemented_in": implemented_in,
            }
        )

    wrappers_by_file.sort(key=lambda item: -int(item["count"]))
    indirection_hotspots.sort(
        key=lambda item: (-int(item["max_chain_depth"]), -int(item["chain_count"]))
    )
    wide_param_bags.sort(
        key=lambda item: (
            -int(item["wide_functions"]),
            -int(item["config_bag_mentions"]),
        )
    )
    one_impl_interfaces.sort(key=lambda item: str(item["interface"]))

    wrapper_rate = total_wrappers / max(total_function_signatures, 1)
    abstraction_leverage = _score_clamped(
        100 - (wrapper_rate * 120) - (len(util_files) * 1.5)
    )
    indirection_cost = _score_clamped(
        100
        - (sum(item["max_chain_depth"] for item in indirection_hotspots[:20]) * 2.5)
        - (sum(item["wide_functions"] for item in wide_param_bags[:20]) * 2.0)
    )
    interface_honesty = _score_clamped(100 - (len(one_impl_interfaces) * 8))

    util_files = sorted(util_files, key=lambda item: -item["loc"])[:20]
    context: dict[str, object] = {
        "util_files": util_files,
        "summary": {
            "wrapper_rate": round(wrapper_rate, 3),
            "total_wrappers": total_wrappers,
            "total_function_signatures": total_function_signatures,
            "one_impl_interface_count": len(one_impl_interfaces),
            "indirection_hotspot_count": len(indirection_hotspots),
            "wide_param_bag_count": len(wide_param_bags),
        },
        "sub_axes": {
            "abstraction_leverage": abstraction_leverage,
            "indirection_cost": indirection_cost,
            "interface_honesty": interface_honesty,
        },
    }
    if wrappers_by_file:
        context["pass_through_wrappers"] = wrappers_by_file[:20]
    if one_impl_interfaces:
        context["one_impl_interfaces"] = one_impl_interfaces[:20]
    if indirection_hotspots:
        context["indirection_hotspots"] = indirection_hotspots[:20]
    if wide_param_bags:
        context["wide_param_bags"] = wide_param_bags[:20]
    return context


def _dependencies_context(state: dict) -> dict:
    cycle_findings = [
        finding
        for finding in state.get("findings", {}).values()
        if finding.get("detector") == "cycles" and finding.get("status") == "open"
    ]
    if not cycle_findings:
        return {}
    return {
        "existing_cycles": len(cycle_findings),
        "cycle_summaries": [
            finding["summary"][:120] for finding in cycle_findings[:10]
        ],
    }


def _testing_context(lang, state: dict, file_contents: dict[str, str]) -> dict:
    testing: dict = {"total_files": len(file_contents)}
    if not lang.dep_graph:
        return testing

    tc_findings = {
        finding["file"]
        for finding in state.get("findings", {}).values()
        if finding.get("detector") == "test_coverage"
        and finding.get("status") == "open"
    }
    if not tc_findings:
        return testing

    critical_untested = []
    for filepath in tc_findings:
        entry = lang.dep_graph.get(resolve_path(filepath), {})
        entry_importer_count = importer_count(entry)
        if entry_importer_count >= 3:
            critical_untested.append(
                {"file": filepath, "importers": entry_importer_count}
            )
    testing["critical_untested"] = sorted(
        critical_untested,
        key=lambda item: -item["importers"],
    )[:10]
    return testing


def _api_surface_context(lang, file_contents: dict[str, str]) -> dict:
    api_surface_fn = getattr(lang, "review_api_surface_fn", None)
    if not callable(api_surface_fn):
        return {}
    computed = api_surface_fn(file_contents)
    return computed if isinstance(computed, dict) else {}


def _build_holistic_context_inner(
    files: list[str], lang, state: dict
) -> HolisticContext:
    """Inner holistic context builder (runs with file cache enabled)."""
    file_contents = _read_file_contents(files)

    context = HolisticContext(
        architecture=_architecture_context(lang, file_contents),
        coupling=_coupling_context(file_contents),
        conventions={
            "naming_by_directory": _naming_conventions_context(file_contents),
            "sibling_behavior": _sibling_behavior_context(file_contents),
        },
        errors={
            "strategy_by_directory": _error_strategy_context(file_contents),
        },
        abstractions=_abstractions_context(file_contents),
        dependencies=_dependencies_context(state),
        testing=_testing_context(lang, state, file_contents),
        api_surface=_api_surface_context(lang, file_contents),
        structure=compute_structure_context(file_contents, lang),
    )

    auth_ctx = gather_auth_context(file_contents, rel_fn=rel)
    if auth_ctx:
        context.authorization = auth_ctx

    ai_debt = gather_ai_debt_signals(file_contents, rel_fn=rel)
    if ai_debt.get("file_signals"):
        context.ai_debt_signals = ai_debt

    migration = gather_migration_signals(file_contents, lang, rel_fn=rel)
    if migration:
        context.migration_signals = migration

    total_loc = sum(len(content.splitlines()) for content in file_contents.values())
    context.codebase_stats = {
        "total_files": len(file_contents),
        "total_loc": total_loc,
    }
    return context
