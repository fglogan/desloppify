"""Context building for review: ReviewContext, shared helpers, heuristic signals."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .. import utils as _utils_mod
from ..utils import rel, resolve_path, _read_file_text, \
    enable_file_cache, disable_file_cache


# ── ReviewContext dataclass ───────────────────────────────────────

@dataclass
class ReviewContext:
    """Codebase-wide context for contextual file evaluation."""
    naming_vocabulary: dict = field(default_factory=dict)
    error_conventions: dict = field(default_factory=dict)
    module_patterns: dict = field(default_factory=dict)
    import_graph_summary: dict = field(default_factory=dict)
    zone_distribution: dict = field(default_factory=dict)
    existing_findings: dict = field(default_factory=dict)
    codebase_stats: dict = field(default_factory=dict)
    sibling_conventions: dict = field(default_factory=dict)
    ai_debt_signals: dict = field(default_factory=dict)
    auth_patterns: dict = field(default_factory=dict)
    error_strategies: dict = field(default_factory=dict)


# ── Shared helpers ────────────────────────────────────────────────

def _abs(filepath: str) -> str:
    """Resolve filepath to absolute using resolve_path."""
    return resolve_path(filepath)


def _file_excerpt(filepath: str, max_lines: int = 30) -> str | None:
    """Read first *max_lines* of a file, returning the text or None."""
    content = _read_file_text(_abs(filepath))
    if content is None:
        return None
    lines = content.splitlines(keepends=True)
    if len(lines) <= max_lines:
        return content
    return "".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"


def _dep_graph_lookup(graph: dict, filepath: str) -> dict:
    """Look up a file in the dep graph, trying absolute and relative keys."""
    abs_path = resolve_path(filepath)
    entry = graph.get(abs_path)
    if entry is not None:
        return entry
    # Try relative path
    rpath = rel(filepath)
    entry = graph.get(rpath)
    if entry is not None:
        return entry
    return {}


def _importer_count(entry: dict) -> int:
    """Extract importer count from a dep graph entry."""
    importers = entry.get("importers", set())
    if isinstance(importers, set):
        return len(importers)
    return entry.get("importer_count", 0)


# ── Regex patterns for code analysis ─────────────────────────────

_FUNC_NAME_RE = re.compile(
    r"(?:function|def|async\s+def|async\s+function)\s+(\w+)"
)
_CLASS_NAME_RE = re.compile(r"(?:class|interface|type)\s+(\w+)")

_ERROR_PATTERNS = {
    "try_catch": re.compile(r"\b(?:try\s*\{|try\s*:)"),
    "returns_null": re.compile(r"\breturn\s+(?:null|None|undefined)\b"),
    "result_type": re.compile(r"\b(?:Result|Either|Ok|Err)\b"),
    "throws": re.compile(r"\b(?:throw\s+new|raise\s+\w)"),
}

_NAME_PREFIX_RE = re.compile(
    r"^(get|set|is|has|can|should|use|create|make|build|parse|format|"
    r"validate|check|find|fetch|load|save|update|delete|remove|add|"
    r"handle|on|init|setup|render|compute|calculate|transform|convert|"
    r"to|from|with|ensure|assert|process|run|do|manage|execute)"
)

_FROM_IMPORT_RE = re.compile(
    r"^(?:from\s+\S+\s+import\s+(.+)|import\s+(.+))$", re.MULTILINE
)


def _extract_imported_names(content: str) -> set[str]:
    """Extract imported symbol names from a file's import statements."""
    names: set[str] = set()
    for m in _FROM_IMPORT_RE.finditer(content):
        raw = m.group(1) or m.group(2)
        if raw is None:
            continue
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            token = part.split()[0]
            if token.startswith("(") or token == "\\":
                continue
            token = token.strip("()")
            if token.isidentifier():
                names.add(token)
    return names


# ── Per-file review context builder ──────────────────────────────

def build_review_context(path: Path, lang, state: dict,
                         files: list[str] | None = None) -> ReviewContext:
    """Gather codebase conventions for contextual evaluation.

    If *files* is provided, skip file_finder (avoids redundant filesystem walks).
    """
    if files is None:
        files = lang.file_finder(path) if lang.file_finder else []
    ctx = ReviewContext()

    if not files:
        return ctx

    already_cached = _utils_mod._cache_enabled
    if not already_cached:
        enable_file_cache()
    try:
        return _build_review_context_inner(files, lang, state, ctx)
    finally:
        if not already_cached:
            disable_file_cache()


def _build_review_context_inner(files: list[str], lang, state: dict,
                                ctx: ReviewContext) -> ReviewContext:
    """Inner context builder (runs with file cache enabled)."""
    is_ts = lang.name == "typescript"

    # Pre-read all file contents once (cache will store them)
    file_contents: dict[str, str] = {}
    for filepath in files:
        content = _read_file_text(_abs(filepath))
        if content is not None:
            file_contents[filepath] = content

    # 1. Naming vocabulary — extract function/class names, count prefixes
    prefix_counter: Counter = Counter()
    total_names = 0
    for content in file_contents.values():
        for name in _FUNC_NAME_RE.findall(content) + _CLASS_NAME_RE.findall(content):
            total_names += 1
            m = _NAME_PREFIX_RE.match(name)
            if m:
                prefix_counter[m.group(1)] += 1
    ctx.naming_vocabulary = {
        "prefixes": dict(prefix_counter.most_common(20)),
        "total_names": total_names,
    }

    # 2. Error handling conventions — scan for patterns
    error_counts: Counter = Counter()
    for content in file_contents.values():
        for pattern_name, pattern in _ERROR_PATTERNS.items():
            if pattern.search(content):
                error_counts[pattern_name] += 1
    ctx.error_conventions = dict(error_counts)

    # 3. Module patterns — what each directory typically uses
    dir_patterns: dict[str, Counter] = {}
    for filepath, content in file_contents.items():
        parts = Path(filepath).parts
        if len(parts) < 2:
            continue
        dir_name = parts[-2] + "/"
        counter = dir_patterns.setdefault(dir_name, Counter())
        if is_ts:
            if re.search(r"\bexport\s+default\b", content):
                counter["default_export"] += 1
            if re.search(r"\bexport\s+(?:function|const|class)\b", content):
                counter["named_export"] += 1
        else:
            if re.search(r"\bdef\s+\w+", content):
                counter["functions"] += 1
            if re.search(r"^__all__\s*=", content, re.MULTILINE):
                counter["explicit_api"] += 1
        if re.search(r"\bclass\s+\w+", content):
            counter["class_based"] += 1
    ctx.module_patterns = {
        d: dict(c.most_common(3)) for d, c in dir_patterns.items() if sum(c.values()) >= 3
    }

    # 4. Import graph summary — top files by importer count
    if lang._dep_graph:
        graph = lang._dep_graph
        importer_counts = {}
        for f, entry in graph.items():
            ic = _importer_count(entry)
            if ic > 0:
                importer_counts[rel(f)] = ic
        top = sorted(importer_counts.items(), key=lambda x: -x[1])[:20]
        ctx.import_graph_summary = {"top_imported": dict(top)}

    # 5. Zone distribution
    if lang._zone_map is not None:
        ctx.zone_distribution = lang._zone_map.counts()

    # 6. Existing findings per file (summaries only)
    findings = state.get("findings", {})
    by_file: dict[str, list[str]] = {}
    for f in findings.values():
        if f["status"] == "open":
            by_file.setdefault(f["file"], []).append(
                f"{f['detector']}: {f['summary'][:80]}"
            )
    ctx.existing_findings = by_file

    # 7. Codebase stats
    total_loc = sum(len(c.splitlines()) for c in file_contents.values())
    ctx.codebase_stats = {
        "total_files": len(file_contents),
        "total_loc": total_loc,
        "avg_file_loc": total_loc // len(file_contents) if file_contents else 0,
    }

    # 8. Sibling function conventions — what naming/patterns neighbors in same dir use
    dir_functions: dict[str, Counter] = {}
    for filepath, content in file_contents.items():
        parts = Path(filepath).parts
        if len(parts) < 2:
            continue
        dir_name = parts[-2] + "/"
        counter = dir_functions.setdefault(dir_name, Counter())
        for name in _FUNC_NAME_RE.findall(content):
            m = _NAME_PREFIX_RE.match(name)
            if m:
                counter[m.group(1)] += 1
    ctx.sibling_conventions = {
        d: dict(c.most_common(5))
        for d, c in dir_functions.items() if sum(c.values()) >= 3
    }

    # 9. AI debt signals
    ctx.ai_debt_signals = _gather_ai_debt_signals(file_contents)

    # 10. Auth patterns
    ctx.auth_patterns = _gather_auth_context(file_contents)

    # 11. Error strategies per file
    strategies: dict[str, str] = {}
    for filepath, content in file_contents.items():
        strat = _classify_error_strategy(content)
        if strat:
            strategies[rel(filepath)] = strat
    ctx.error_strategies = strategies

    return ctx


def _serialize_context(ctx: ReviewContext) -> dict:
    """Convert ReviewContext to a JSON-serializable dict."""
    d = {
        "naming_vocabulary": ctx.naming_vocabulary,
        "error_conventions": ctx.error_conventions,
        "module_patterns": ctx.module_patterns,
        "import_graph_summary": ctx.import_graph_summary,
        "zone_distribution": ctx.zone_distribution,
        "existing_findings": ctx.existing_findings,
        "codebase_stats": ctx.codebase_stats,
        "sibling_conventions": ctx.sibling_conventions,
    }
    if ctx.ai_debt_signals:
        d["ai_debt_signals"] = ctx.ai_debt_signals
    if ctx.auth_patterns:
        d["auth_patterns"] = ctx.auth_patterns
    if ctx.error_strategies:
        d["error_strategies"] = ctx.error_strategies
    return d


# ── Heuristic signal gatherers ────────────────────────────────────

_COMMENT_RE = re.compile(r"^\s*(?:#|//|/\*|\*)")
_LOG_RE = re.compile(
    r"\b(?:console\.(?:log|warn|error|debug|info)|print\(|logging\.(?:debug|info|warning|error))\b"
)
_GUARD_RE = re.compile(
    r"\b(?:if\s*\(\s*\w+\s*(?:===?\s*null|!==?\s*null|===?\s*undefined|!==?\s*undefined)"
    r"|try\s*\{|try\s*:)\b"
)
_FUNC_BODY_RE = re.compile(
    r"(?:def\s+\w+|function\s+\w+|=>\s*\{)", re.MULTILINE
)


def _gather_ai_debt_signals(file_contents: dict[str, str]) -> dict:
    """Compute per-file AI-debt heuristic signals.

    Returns ``{"file_signals": {path: {signal: value}}, "codebase_avg_comment_ratio": float}``.
    Top 20 files by signal count.
    """
    all_ratios: list[float] = []
    file_signals: dict[str, dict[str, float]] = {}

    for filepath, content in file_contents.items():
        rpath = rel(filepath)
        lines = content.splitlines()
        if not lines:
            continue

        total = len(lines)
        comment_lines = sum(1 for ln in lines if _COMMENT_RE.match(ln))
        comment_ratio = comment_lines / total

        all_ratios.append(comment_ratio)

        log_count = len(_LOG_RE.findall(content))
        func_count = len(_FUNC_BODY_RE.findall(content))
        log_density = log_count / max(func_count, 1)

        guard_count = len(_GUARD_RE.findall(content))
        guard_density = guard_count / max(func_count, 1)

        signals: dict[str, float] = {}
        if comment_ratio > 0.3:
            signals["comment_ratio"] = round(comment_ratio, 2)
        if log_density > 3.0:
            signals["log_density"] = round(log_density, 1)
        if guard_density > 2.0:
            signals["guard_density"] = round(guard_density, 1)

        if signals:
            file_signals[rpath] = signals

    # Top 20 by signal count
    top = dict(sorted(file_signals.items(), key=lambda x: -len(x[1]))[:20])
    avg_ratio = sum(all_ratios) / len(all_ratios) if all_ratios else 0.0

    return {
        "file_signals": top,
        "codebase_avg_comment_ratio": round(avg_ratio, 3),
    }


_ROUTE_AUTH_RE = re.compile(
    r"@(?:app|router|api)\.(?:get|post|put|patch|delete|route)\b"
    r"|app\.(?:get|post|put|patch|delete)\("
    r"|export\s+(?:async\s+)?function\s+(?:GET|POST|PUT|PATCH|DELETE)\b"
    r"|@router\.(?:get|post|put|patch|delete)\b",
    re.MULTILINE,
)
_AUTH_DECORATOR_RE = re.compile(
    r"@(?:login_required|require_auth|auth_required|requires_auth|authenticated)\b"
    r"|\brequireAuth\b|\bwithAuth\b|\bgetServerSession\b|\buseAuth\b"
    r"|\brequest\.user\b|\bsession\.user\b|\bgetUser\b",
)
_RLS_TABLE_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)", re.IGNORECASE)
_RLS_ENABLE_RE = re.compile(
    r"ALTER\s+TABLE\s+(\w+)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY"
    r"|CREATE\s+POLICY\s+\w+\s+ON\s+(\w+)",
    re.IGNORECASE,
)
_SERVICE_ROLE_RE = re.compile(r"service_role|SERVICE_ROLE|serviceRole")
_SUPABASE_CLIENT_RE = re.compile(r"\bcreateClient\b")


def _gather_auth_context(file_contents: dict[str, str]) -> dict:
    """Compute auth/RLS context from file contents.

    Returns route auth coverage, RLS coverage, service role usage, and auth patterns.
    """
    route_auth: dict[str, dict] = {}
    rls_tables: set[str] = set()
    rls_enabled: set[str] = set()
    service_role_files: list[str] = []
    auth_patterns: dict[str, int] = {}

    for filepath, content in file_contents.items():
        rpath = rel(filepath)

        # Route auth coverage
        route_matches = _ROUTE_AUTH_RE.findall(content)
        if route_matches:
            auth_matches = _AUTH_DECORATOR_RE.findall(content)
            handler_count = len(route_matches)
            auth_count = len(auth_matches)
            route_auth[rpath] = {
                "handlers": handler_count,
                "with_auth": min(auth_count, handler_count),
                "without_auth": max(0, handler_count - auth_count),
            }

        # RLS coverage (SQL/migration files)
        for m in _RLS_TABLE_RE.finditer(content):
            rls_tables.add(m.group(1))
        for m in _RLS_ENABLE_RE.finditer(content):
            table = m.group(1) or m.group(2)
            if table:
                rls_enabled.add(table)

        # Service role usage
        if _SERVICE_ROLE_RE.search(content) and _SUPABASE_CLIENT_RE.search(content):
            service_role_files.append(rpath)

        # Auth check patterns
        auth_count = len(_AUTH_DECORATOR_RE.findall(content))
        if auth_count > 0:
            auth_patterns[rpath] = auth_count

    result: dict = {}
    if route_auth:
        result["route_auth_coverage"] = route_auth
    if rls_tables:
        result["rls_coverage"] = {
            "with_rls": sorted(rls_tables & rls_enabled),
            "without_rls": sorted(rls_tables - rls_enabled),
        }
    if service_role_files:
        result["service_role_usage"] = service_role_files
    if auth_patterns:
        result["auth_patterns"] = auth_patterns
    return result


_DEPRECATED_RE = re.compile(r"@[Dd]eprecated\b|DEPRECATED", re.MULTILINE)
_MIGRATION_TODO_RE = re.compile(
    r"(?:TODO|FIXME|HACK)\b[^:\n]*\b(?:migrat|legacy|deprecat|old.?api|remove.?after)\b",
    re.IGNORECASE,
)

# Old+new pattern pairs: (name, old_pattern, new_pattern)
_PATTERN_PAIRS_TS = [
    ("class→functional components", re.compile(r"\bclass\s+\w+\s+extends\s+(?:React\.)?Component\b"),
     re.compile(r"\bfunction\s+\w+\s*\([^)]*\)\s*\{.*?return\s*\(?\s*<", re.DOTALL)),
    ("axios→fetch", re.compile(r"\baxios\b"), re.compile(r"\bfetch\(")),
    ("moment→dayjs", re.compile(r"\bmoment\b"), re.compile(r"\bdayjs\b")),
    ("var→let/const", re.compile(r"\bvar\s+\w+"), re.compile(r"\b(?:let|const)\s+\w+")),
    ("require→import", re.compile(r"\brequire\("), re.compile(r"\bimport\s+")),
]
_PATTERN_PAIRS_PY = [
    ("os.path→pathlib", re.compile(r"\bos\.path\b"), re.compile(r"\bpathlib\b|\bPath\(")),
    ("format()→f-string", re.compile(r"\.format\("), re.compile(r'\bf"')),
    ("unittest→pytest", re.compile(r"\bunittest\b"), re.compile(r"\bpytest\b")),
    ("print→logging", re.compile(r"\bprint\("), re.compile(r"\blogging\.\w+\(")),
]


def _gather_migration_signals(file_contents: dict[str, str],
                               lang_name: str) -> dict:
    """Compute migration/deprecated signals from file contents.

    Returns deprecated markers, migration TODOs, pattern pairs, mixed extensions.
    """
    deprecated_files: dict[str, int] = {}
    migration_todos: list[dict] = []
    stems_by_ext: dict[str, set[str]] = {}  # stem -> set of extensions

    for filepath, content in file_contents.items():
        rpath = rel(filepath)

        # Deprecated markers
        dep_count = len(_DEPRECATED_RE.findall(content))
        if dep_count > 0:
            deprecated_files[rpath] = dep_count

        # Migration TODOs
        for m in _MIGRATION_TODO_RE.finditer(content):
            migration_todos.append({"file": rpath, "text": m.group(0)[:120]})

        # Track stems for mixed extension detection
        p = Path(rpath)
        stem = p.stem
        ext = p.suffix
        if ext in (".js", ".ts", ".jsx", ".tsx"):
            stems_by_ext.setdefault(stem, set()).add(ext)

    # Pattern pair detection
    pairs = _PATTERN_PAIRS_TS if lang_name == "typescript" else _PATTERN_PAIRS_PY
    pattern_results: list[dict] = []
    for name, old_re, new_re in pairs:
        old_count = sum(1 for c in file_contents.values() if old_re.search(c))
        new_count = sum(1 for c in file_contents.values() if new_re.search(c))
        if old_count > 0 and new_count > 0:
            pattern_results.append({
                "name": name, "old_count": old_count, "new_count": new_count,
            })

    # Mixed extensions
    mixed_stems = sorted(stem for stem, exts in stems_by_ext.items()
                         if len(exts) >= 2)

    result: dict = {}
    if deprecated_files:
        result["deprecated_markers"] = {
            "total": sum(deprecated_files.values()),
            "files": deprecated_files,
        }
    if migration_todos:
        result["migration_todos"] = migration_todos[:30]
    if pattern_results:
        result["pattern_pairs"] = pattern_results
    if mixed_stems:
        result["mixed_extensions"] = mixed_stems[:20]
    return result


def _classify_error_strategy(content: str) -> str | None:
    """Classify a file's primary error handling strategy."""
    throws = len(re.findall(r"\b(?:throw\s+new|raise\s+\w)", content))
    returns_null = len(re.findall(r"\breturn\s+(?:null|None|undefined)\b", content))
    result_type = len(re.findall(r"\b(?:Result|Either|Ok|Err)\b", content))
    try_catch = len(re.findall(r"\b(?:try\s*\{|try\s*:)", content))

    counts = {"throw": throws, "return_null": returns_null,
              "result_type": result_type, "try_catch": try_catch}
    total = sum(counts.values())
    if total == 0:
        return None
    dominant = max(counts, key=counts.get)  # type: ignore[arg-type]
    # "mixed" if no strategy accounts for >60% of occurrences
    if counts[dominant] / total < 0.6:
        return "mixed"
    return dominant


# ── Holistic context builder ─────────────────────────────────────

def build_holistic_context(path: Path, lang, state: dict,
                           files: list[str] | None = None) -> dict:
    """Gather codebase-wide data for holistic review.

    Returns a dict with structured data per dimension.
    """
    if files is None:
        files = lang.file_finder(path) if lang.file_finder else []

    already_cached = _utils_mod._cache_enabled
    if not already_cached:
        enable_file_cache()
    try:
        return _build_holistic_context_inner(files, lang, state)
    finally:
        if not already_cached:
            disable_file_cache()


def _build_holistic_context_inner(files: list[str], lang, state: dict) -> dict:
    """Inner holistic context builder (runs with file cache enabled)."""
    ctx: dict = {}

    # Pre-read file contents
    file_contents: dict[str, str] = {}
    for filepath in files:
        content = _read_file_text(_abs(filepath))
        if content is not None:
            file_contents[filepath] = content

    # 1. Architecture: god modules, dep chains
    arch: dict = {}
    if lang._dep_graph:
        graph = lang._dep_graph
        importer_counts = {}
        for f, entry in graph.items():
            ic = _importer_count(entry)
            if ic > 0:
                importer_counts[rel(f)] = ic
        top_imported = sorted(importer_counts.items(), key=lambda x: -x[1])[:10]
        arch["god_modules"] = [
            {"file": f, "importers": c,
             "excerpt": _file_excerpt(f) or ""}
            for f, c in top_imported if c >= 5
        ]
        arch["top_imported"] = dict(top_imported)
    ctx["architecture"] = arch

    # 2. Coupling: import-time side effects detection
    coupling: dict = {}
    module_level_io = []
    for filepath, content in file_contents.items():
        lines = content.splitlines()
        for i, line in enumerate(lines[:50]):
            stripped = line.strip()
            if stripped.startswith(("def ", "class ", "async def ", "if ", "#", "@", "import ", "from ")):
                continue
            if re.search(r"\b(?:open|connect|requests?\.|urllib|subprocess|os\.system)\b", stripped):
                module_level_io.append({"file": rel(filepath), "line": i + 1, "code": stripped[:100]})
    if module_level_io:
        coupling["module_level_io"] = module_level_io[:20]
    ctx["coupling"] = coupling

    # 3. Conventions: naming style per directory
    conventions: dict = {}
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
            elif name[0].islower() and any(c.isupper() for c in name):
                counter["camelCase"] += 1
            elif name[0].isupper():
                counter["PascalCase"] += 1
    conventions["naming_by_directory"] = {
        d: dict(c.most_common(3)) for d, c in dir_styles.items() if sum(c.values()) >= 3
    }

    # 3b. Sibling behavior: imports shared across files in same directory
    dir_imports: dict[str, dict[str, set[str]]] = {}
    for filepath, content in file_contents.items():
        parts = Path(filepath).parts
        if len(parts) < 2:
            continue
        dir_name = parts[-2] + "/"
        rpath = rel(filepath)
        names = _extract_imported_names(content)
        dir_imports.setdefault(dir_name, {})[rpath] = names

    sibling_behavior: dict = {}
    for dir_name, file_names_map in dir_imports.items():
        total = len(file_names_map)
        if total < 3:
            continue
        name_counts: Counter = Counter()
        for names in file_names_map.values():
            for n in names:
                name_counts[n] += 1
        threshold = total * 0.6
        shared = {n: cnt for n, cnt in name_counts.items() if cnt >= threshold}
        if not shared:
            continue
        outliers = []
        for rpath, names in file_names_map.items():
            missing = [n for n in shared if n not in names]
            if missing:
                outliers.append({"file": rpath, "missing": sorted(missing)})
        if outliers:
            sibling_behavior[dir_name] = {
                "shared_patterns": {n: {"count": cnt, "total": total}
                                    for n, cnt in sorted(shared.items(),
                                                         key=lambda x: -x[1])},
                "outliers": sorted(outliers, key=lambda x: len(x["missing"]),
                                   reverse=True),
            }
    conventions["sibling_behavior"] = sibling_behavior
    ctx["conventions"] = conventions

    # 4. Error handling: strategy distribution per directory
    errors: dict = {}
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
    errors["strategy_by_directory"] = {
        d: dict(c.most_common(5)) for d, c in dir_errors.items() if sum(c.values()) >= 2
    }
    ctx["errors"] = errors

    # 5. Abstractions: util/helper file inventory
    abstractions: dict = {}
    util_files = []
    for filepath in file_contents:
        rpath = rel(filepath)
        basename = Path(rpath).stem.lower()
        if basename in ("utils", "helpers", "util", "helper", "common", "misc"):
            loc = len(file_contents[filepath].splitlines())
            util_files.append({"file": rpath, "loc": loc,
                               "excerpt": _file_excerpt(filepath) or ""})
    abstractions["util_files"] = sorted(util_files, key=lambda x: -x["loc"])[:20]
    ctx["abstractions"] = abstractions

    # 6. Dependencies: cycles from existing findings
    deps: dict = {}
    cycle_findings = [f for f in state.get("findings", {}).values()
                      if f.get("detector") == "cycles" and f["status"] == "open"]
    if cycle_findings:
        deps["existing_cycles"] = len(cycle_findings)
        deps["cycle_summaries"] = [f["summary"][:120] for f in cycle_findings[:10]]
    ctx["dependencies"] = deps

    # 7. Testing: coverage gaps
    testing: dict = {}
    if lang._dep_graph:
        tc_findings = {f["file"] for f in state.get("findings", {}).values()
                       if f.get("detector") == "test_coverage" and f["status"] == "open"}
        if tc_findings:
            graph = lang._dep_graph
            critical_untested = []
            for filepath in tc_findings:
                entry = graph.get(resolve_path(filepath), {})
                ic = _importer_count(entry)
                if ic >= 3:
                    critical_untested.append({"file": filepath, "importers": ic})
            testing["critical_untested"] = sorted(critical_untested, key=lambda x: -x["importers"])[:10]
    testing["total_files"] = len(file_contents)
    ctx["testing"] = testing

    # 8. API surface: export patterns
    api: dict = {}
    is_ts = lang.name == "typescript"
    if is_ts:
        sync_async_mix = []
        for filepath, content in file_contents.items():
            has_sync = bool(re.search(r"\bexport\s+function\s+\w+", content))
            has_async = bool(re.search(r"\bexport\s+async\s+function\s+\w+", content))
            if has_sync and has_async:
                sync_async_mix.append(rel(filepath))
        if sync_async_mix:
            api["sync_async_mix"] = sync_async_mix[:20]
    ctx["api_surface"] = api

    # 9. Authorization context
    auth_ctx = _gather_auth_context(file_contents)
    if auth_ctx:
        ctx["authorization"] = auth_ctx

    # 10. AI debt signals
    ai_debt = _gather_ai_debt_signals(file_contents)
    if ai_debt.get("file_signals"):
        ctx["ai_debt_signals"] = ai_debt

    # 11. Migration signals
    migration = _gather_migration_signals(file_contents, lang.name)
    if migration:
        ctx["migration_signals"] = migration

    # Codebase stats
    total_loc = sum(len(c.splitlines()) for c in file_contents.values())
    ctx["codebase_stats"] = {
        "total_files": len(file_contents),
        "total_loc": total_loc,
    }

    return ctx
