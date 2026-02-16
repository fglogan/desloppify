"""status command: score dashboard with per-tier progress."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict

from ..utils import LOC_COMPACT_THRESHOLD, colorize, get_area, print_table
from ._helpers import state_path, _write_query


def cmd_status(args: argparse.Namespace) -> None:
    """Show score dashboard."""
    from ..state import (
        load_state,
        suppression_metrics,
        get_overall_score,
        get_objective_score,
        get_strict_score,
        get_strict_all_detected_score,
    )

    sp = state_path(args)
    state = load_state(sp)
    stats = state.get("stats", {})
    suppression = suppression_metrics(state)
    ignore_integrity = state.get("ignore_integrity", {}) or {}
    strict_all_detected = get_strict_all_detected_score(state)
    detector_transparency = _build_detector_transparency(
        state,
        ignore_integrity=ignore_integrity,
    )

    if getattr(args, "json", False):
        print(json.dumps({"overall_score": get_overall_score(state),
                          "objective_score": get_objective_score(state),
                          "strict_score": get_strict_score(state),
                          "strict_all_detected": strict_all_detected,
                          "dimension_scores": state.get("dimension_scores"),
                          "potentials": state.get("potentials"),
                          "codebase_metrics": state.get("codebase_metrics"),
                          "stats": stats,
                          "suppression": suppression,
                          "detector_transparency": detector_transparency,
                          "scan_count": state.get("scan_count", 0),
                          "last_scan": state.get("last_scan")}, indent=2))
        return

    if not state.get("last_scan"):
        print(colorize("No scans yet. Run: desloppify scan", "yellow"))
        return

    from ..utils import check_tool_staleness
    stale_warning = check_tool_staleness(state)
    if stale_warning:
        print(colorize(f"  {stale_warning}", "yellow"))

    overall_score = get_overall_score(state)
    objective_score = get_objective_score(state)
    strict_score = get_strict_score(state)
    dim_scores = state.get("dimension_scores", {})
    by_tier = stats.get("by_tier", {})

    if overall_score is not None and objective_score is not None and strict_score is not None:
        score_line = (
            f"\n  Scores: overall {overall_score:.1f}/100 · "
            f"objective {objective_score:.1f}/100 · "
            f"strict_visible {strict_score:.1f}/100"
        )
        if strict_all_detected is not None:
            score_line += f" · strict_all_detected {strict_all_detected:.1f}/100"
        print(colorize(
            score_line,
            "bold",
        ))
    else:
        print(colorize("\n  Scores unavailable", "bold"))
        print(colorize("  Run a full scan to compute overall/objective/strict scores.", "yellow"))

    # Codebase metrics
    metrics = state.get("codebase_metrics", {})
    total_files = sum(m.get("total_files", 0) for m in metrics.values())
    total_loc = sum(m.get("total_loc", 0) for m in metrics.values())
    total_dirs = sum(m.get("total_directories", 0) for m in metrics.values())
    if total_files:
        loc_str = f"{total_loc:,}" if total_loc < LOC_COMPACT_THRESHOLD else f"{total_loc // 1000}K"
        print(colorize(f"  {total_files} files · {loc_str} LOC · {total_dirs} dirs · "
                f"Last scan: {state.get('last_scan', 'never')}", "dim"))
    else:
        print(colorize(f"  Scans: {state.get('scan_count', 0)} | Last: {state.get('last_scan', 'never')}", "dim"))

    # Completeness indicator
    completeness = state.get("scan_completeness", {})
    incomplete = [lang for lang, s in completeness.items() if s != "full"]
    if incomplete:
        print(colorize(f"  * Incomplete scan ({', '.join(incomplete)} — slow phases skipped)", "yellow"))

    print(colorize("  " + "─" * 60, "dim"))

    # Dimension table (when available)
    if dim_scores:
        _show_dimension_table(dim_scores)
    else:
        # Fall back to tier-based display
        rows = []
        for tier_num in [1, 2, 3, 4]:
            ts = by_tier.get(str(tier_num), {})
            t_open = ts.get("open", 0)
            t_fixed = ts.get("fixed", 0) + ts.get("auto_resolved", 0)
            t_fp = ts.get("false_positive", 0)
            t_wontfix = ts.get("wontfix", 0)
            t_total = sum(ts.values())
            strict_pct = round((t_fixed + t_fp) / t_total * 100) if t_total else 100
            bar_len = 20
            filled = round(strict_pct / 100 * bar_len)
            bar = colorize("█" * filled, "green") + colorize("░" * (bar_len - filled), "dim")
            rows.append([f"Tier {tier_num}", bar, f"{strict_pct}%",
                         str(t_open), str(t_fixed), str(t_wontfix)])

        print_table(["Tier", "Strict Progress", "%", "Open", "Fixed", "Debt"], rows,
                    [40, 22, 5, 6, 6, 6])

    _show_structural_areas(state)
    _show_review_summary(state)
    _show_detector_transparency(detector_transparency)

    # Focus suggestion (lowest-scoring dimension)
    if dim_scores:
        _show_focus_suggestion(dim_scores, state)

    # Computed narrative headline
    from ..narrative import compute_narrative
    from ._helpers import resolve_lang
    lang = resolve_lang(args)
    lang_name = lang.name if lang else None
    narrative = compute_narrative(state, lang=lang_name, command="status")
    if narrative.get("headline"):
        print(colorize(f"  → {narrative['headline']}", "cyan"))
        print()

    ignores = args._config.get("ignore", [])
    if ignores:
        _show_ignore_summary(
            ignores,
            suppression,
            ignore_meta=args._config.get("ignore_metadata", {}),
            score_integrity=state.get("score_integrity", {}),
            include_suppressed=getattr(args, "include_suppressed", False),
            ignore_integrity=ignore_integrity,
        )

    review_age = args._config.get("review_max_age_days", 30)
    if review_age != 30:
        label = "never" if review_age == 0 else f"{review_age} days"
        print(colorize(f"  Review staleness: {label}", "dim"))
    print()

    _write_query({"command": "status",
                  "overall_score": overall_score,
                  "objective_score": objective_score,
                  "strict_score": strict_score,
                  "strict_all_detected": strict_all_detected,
                  "dimension_scores": dim_scores,
                  "stats": stats, "scan_count": state.get("scan_count", 0),
                  "last_scan": state.get("last_scan"),
                  "by_tier": by_tier, "ignores": ignores,
                  "suppression": suppression,
                  "detector_transparency": detector_transparency,
                  "potentials": state.get("potentials"),
                  "codebase_metrics": state.get("codebase_metrics"),
                  "narrative": narrative})


def _show_ignore_summary(
    ignores: list[str],
    suppression: dict,
    *,
    ignore_meta: dict | None = None,
    score_integrity: dict | None = None,
    include_suppressed: bool = False,
    ignore_integrity: dict | None = None,
) -> None:
    """Show ignore list plus suppression accountability from recent scans."""
    ignore_meta = ignore_meta if isinstance(ignore_meta, dict) else {}
    score_integrity = score_integrity if isinstance(score_integrity, dict) else {}
    ignore_integrity = ignore_integrity if isinstance(ignore_integrity, dict) else {}
    print(colorize(f"\n  Ignore list ({len(ignores)}):", "dim"))
    for p in ignores[:10]:
        note = (ignore_meta.get(p) or {}).get("note", "")
        if note:
            print(colorize(f"    {p}  # {note}", "dim"))
        else:
            print(colorize(f"    {p}", "dim"))

    last_ignored = int(suppression.get("last_ignored", 0) or 0)
    last_raw = int(suppression.get("last_raw_findings", 0) or 0)
    last_pct = float(suppression.get("last_suppressed_pct", 0.0) or 0.0)

    if last_raw > 0:
        style = "red" if last_pct >= 30 else "yellow" if last_pct >= 10 else "dim"
        print(colorize(
            f"  Ignore suppression (last scan): {last_ignored}/{last_raw} findings hidden ({last_pct:.1f}%)",
            style,
        ))
    elif suppression.get("recent_scans", 0):
        print(colorize("  Ignore suppression (last scan): 0 findings hidden", "dim"))

    recent_scans = int(suppression.get("recent_scans", 0) or 0)
    recent_raw = int(suppression.get("recent_raw_findings", 0) or 0)
    if recent_scans > 1 and recent_raw > 0:
        recent_ignored = int(suppression.get("recent_ignored", 0) or 0)
        recent_pct = float(suppression.get("recent_suppressed_pct", 0.0) or 0.0)
        print(colorize(
            f"    Recent ({recent_scans} scans): {recent_ignored}/{recent_raw} findings hidden ({recent_pct:.1f}%)",
            "dim",
        ))

    warn = score_integrity.get("ignore_suppression_warning")
    if isinstance(warn, dict):
        print(colorize(
            f"  Ignore warning: {warn.get('suppressed_pct', 0):.1f}% findings hidden "
            f"({warn.get('ignored', 0)} ignored, {warn.get('ignore_patterns', 0)} patterns)",
            "yellow",
        ))

    if include_suppressed:
        by_detector = ignore_integrity.get("ignored_by_detector", {})
        if isinstance(by_detector, dict) and by_detector:
            pairs = ", ".join(
                f"{det}:{count}" for det, count in sorted(by_detector.items(), key=lambda x: (-x[1], x[0]))
            )
            print(colorize(f"  Suppressed by detector (last scan): {pairs}", "dim"))


def _build_detector_transparency(
    state: dict,
    *,
    ignore_integrity: dict | None = None,
) -> dict:
    """Build strict-failure visibility metrics by detector."""
    from ..state import path_scoped_findings
    from ..zones import EXCLUDED_ZONE_VALUES

    ignore_integrity = ignore_integrity if isinstance(ignore_integrity, dict) else {}
    suppressed_raw = ignore_integrity.get("ignored_by_detector", {})
    suppressed_by_detector = (
        {k: int(v or 0) for k, v in suppressed_raw.items()}
        if isinstance(suppressed_raw, dict)
        else {}
    )

    visible_by_detector: dict[str, int] = defaultdict(int)
    excluded_by_detector: dict[str, int] = defaultdict(int)
    strict_statuses = {"open", "wontfix"}

    scoped = path_scoped_findings(state.get("findings", {}), state.get("scan_path"))
    for finding in scoped.values():
        if finding.get("status") not in strict_statuses:
            continue
        detector = finding.get("detector", "unknown")
        zone = finding.get("zone", "production")
        if zone in EXCLUDED_ZONE_VALUES:
            excluded_by_detector[detector] += 1
        else:
            visible_by_detector[detector] += 1

    detectors = sorted(
        set(visible_by_detector) | set(excluded_by_detector) | set(suppressed_by_detector)
    )
    rows = []
    for detector in detectors:
        visible = visible_by_detector.get(detector, 0)
        suppressed = suppressed_by_detector.get(detector, 0)
        excluded = excluded_by_detector.get(detector, 0)
        total = visible + suppressed + excluded
        rows.append({
            "detector": detector,
            "visible": visible,
            "suppressed": suppressed,
            "excluded": excluded,
            "total_detected": total,
        })
    rows.sort(key=lambda row: (-row["total_detected"], row["detector"]))

    return {
        "rows": rows,
        "totals": {
            "visible": sum(row["visible"] for row in rows),
            "suppressed": sum(row["suppressed"] for row in rows),
            "excluded": sum(row["excluded"] for row in rows),
            "detectors": len(rows),
        },
    }


def _show_detector_transparency(transparency: dict) -> None:
    """Render detector-level strict visibility metrics."""
    if not isinstance(transparency, dict):
        return
    rows = transparency.get("rows", [])
    totals = transparency.get("totals", {})
    if not rows:
        return

    suppressed_total = int(totals.get("suppressed", 0) or 0)
    excluded_total = int(totals.get("excluded", 0) or 0)
    if suppressed_total <= 0 and excluded_total <= 0:
        return

    table_rows = [
        [
            row["detector"],
            str(row["visible"]),
            str(row["suppressed"]),
            str(row["excluded"]),
            str(row["total_detected"]),
        ]
        for row in rows
        if row["suppressed"] > 0 or row["excluded"] > 0
    ]
    if not table_rows:
        return

    print(colorize("\n  Strict Transparency (last scan):", "bold"))
    print_table(
        ["Detector", "Visible", "Suppressed", "Excluded", "All"],
        table_rows,
        [24, 8, 11, 9, 6],
    )

    visible_total = int(totals.get("visible", 0) or 0)
    hidden_total = suppressed_total + excluded_total
    all_total = visible_total + hidden_total
    if all_total > 0:
        hidden_pct = round(hidden_total / all_total * 100, 1)
        style = "red" if hidden_pct >= 40 else "yellow" if hidden_pct >= 20 else "dim"
        print(colorize(
            f"  Hidden strict failures: {hidden_total}/{all_total} ({hidden_pct:.1f}%)",
            style,
        ))


def _show_dimension_table(dim_scores: dict):
    """Show dimension health table with dual scores and progress bars."""
    from ..scoring import DIMENSIONS
    from ..registry import dimension_action_type

    print()
    bar_len = 20
    # Header
    print(colorize(f"  {'Dimension':<22} {'Checks':>7}  {'Health':>6}  {'Strict':>6}  {'Bar':<{bar_len+2}} {'Tier'}  {'Action'}", "dim"))
    print(colorize("  " + "─" * 86, "dim"))

    # Find lowest strict score for focus arrow (includes subjective dimensions)
    lowest_name = None
    lowest_score = 101
    for name, ds in dim_scores.items():
        strict_val = ds.get("strict", ds["score"])
        if strict_val < lowest_score:
            lowest_score = strict_val
            lowest_name = name

    for dim in DIMENSIONS:
        ds = dim_scores.get(dim.name)
        if not ds:
            continue
        score_val = ds["score"]
        strict_val = ds.get("strict", score_val)
        checks = ds["checks"]

        filled = round(score_val / 100 * bar_len)
        if score_val >= 98:
            bar = colorize("█" * filled + "░" * (bar_len - filled), "green")
        elif score_val >= 93:
            bar = colorize("█" * filled, "green") + colorize("░" * (bar_len - filled), "dim")
        else:
            bar = colorize("█" * filled, "yellow") + colorize("░" * (bar_len - filled), "dim")

        focus = colorize(" ←", "yellow") if dim.name == lowest_name else "  "
        checks_str = f"{checks:>7,}"
        action = dimension_action_type(dim.name)
        print(f"  {dim.name:<22} {checks_str}  {score_val:5.1f}%  {strict_val:5.1f}%  {bar}  T{dim.tier}  {action}{focus}")


    # Subjective dimensions (not in DIMENSIONS list)
    static_names = {d.name for d in DIMENSIONS}
    assessment_dims = [(name, ds) for name, ds in sorted(dim_scores.items())
                       if name not in static_names]
    if assessment_dims:
        print(colorize("  ── Subjective Dimensions ─────────────────────────────────────────────", "dim"))
        for name, ds in assessment_dims:
            score_val = ds["score"]
            strict_val = ds.get("strict", score_val)
            tier = ds.get("tier", 4)

            filled = round(score_val / 100 * bar_len)
            if score_val >= 98:
                bar = colorize("█" * filled + "░" * (bar_len - filled), "green")
            elif score_val >= 93:
                bar = colorize("█" * filled, "green") + colorize("░" * (bar_len - filled), "dim")
            else:
                bar = colorize("█" * filled, "yellow") + colorize("░" * (bar_len - filled), "dim")

            focus = colorize(" ←", "yellow") if name == lowest_name else "  "
            checks_str = f"{'—':>7}"
            print(f"  {name:<22} {checks_str}  {score_val:5.1f}%  {strict_val:5.1f}%  {bar}  T{tier}  {'review'}{focus}")
    print(colorize("  Health = open penalized | Strict = open + wontfix penalized", "dim"))
    print(colorize("  Action: fix=auto-fixer | move=reorganize | refactor=manual rewrite | manual=review & fix", "dim"))
    print()


def _show_focus_suggestion(dim_scores: dict, state: dict):
    """Show the lowest-scoring dimension as the focus area."""
    lowest_name = None
    lowest_score = 101
    lowest_issues = 0
    for name, ds in dim_scores.items():
        strict_val = ds.get("strict", ds["score"])
        if strict_val < lowest_score:
            lowest_score = strict_val
            lowest_name = name
            lowest_issues = ds["issues"]

    if lowest_name and lowest_score < 100:
        ds = dim_scores[lowest_name]
        # Subjective dimensions have "subjective_assessment" as their only detector
        is_subjective = "subjective_assessment" in ds.get("detectors", {})
        if is_subjective:
            suffix = ""
            if lowest_issues:
                suffix = f", {lowest_issues} review finding{'s' if lowest_issues != 1 else ''}"
            print(colorize(f"  Focus: {lowest_name} ({lowest_score:.1f}%) — "
                    f"re-review to improve{suffix}", "cyan"))
            print()
            return

        # Mechanical dimension — estimate impact
        from ..scoring import merge_potentials, compute_score_impact
        potentials = merge_potentials(state.get("potentials", {}))
        from ..scoring import DIMENSIONS
        target_dim = next((d for d in DIMENSIONS if d.name == lowest_name), None)
        if target_dim:
            impact = 0.0
            for det in target_dim.detectors:
                impact = compute_score_impact(
                    {k: {"score": v["score"], "tier": v.get("tier", 3),
                          "detectors": v.get("detectors", {})}
                     for k, v in dim_scores.items()
                     if "score" in v},
                    potentials, det, lowest_issues)
                if impact > 0:
                    break

            impact_str = f" for +{impact:.1f} pts" if impact > 0 else ""
            print(colorize(f"  Focus: {lowest_name} ({lowest_score:.1f}%) — "
                    f"fix {lowest_issues} items{impact_str}", "cyan"))
            print()


def _show_structural_areas(state: dict):
    """Show structural debt grouped by area when T3/T4 debt is significant."""
    from ..state import path_scoped_findings
    findings = path_scoped_findings(state.get("findings", {}), state.get("scan_path"))

    structural = [f for f in findings.values()
                  if f["tier"] in (3, 4) and f["status"] in ("open", "wontfix")]

    if len(structural) < 5:
        return

    areas: dict[str, list] = defaultdict(list)
    for f in structural:
        areas[get_area(f["file"])].append(f)

    if len(areas) < 2:
        return

    sorted_areas = sorted(areas.items(),
                          key=lambda x: -sum(f["tier"] for f in x[1]))

    print(colorize("\n  ── Structural Debt by Area ──", "bold"))
    print(colorize("  Create a task doc for each area → farm to sub-agents for decomposition", "dim"))
    print()

    rows = []
    for area, area_findings in sorted_areas[:15]:
        t3 = sum(1 for f in area_findings if f["tier"] == 3)
        t4 = sum(1 for f in area_findings if f["tier"] == 4)
        open_count = sum(1 for f in area_findings if f["status"] == "open")
        debt_count = sum(1 for f in area_findings if f["status"] == "wontfix")
        weight = sum(f["tier"] for f in area_findings)
        rows.append([area, str(len(area_findings)), f"T3:{t3} T4:{t4}",
                      str(open_count), str(debt_count), str(weight)])

    print_table(["Area", "Items", "Tiers", "Open", "Debt", "Weight"], rows,
                [42, 6, 10, 5, 5, 7])

    remaining = len(sorted_areas) - 15
    if remaining > 0:
        print(colorize(f"\n  ... and {remaining} more areas", "dim"))

    print(colorize("\n  Workflow:", "dim"))
    print(colorize("    1. desloppify show <area> --status wontfix --top 50", "dim"))
    print(colorize("    2. Create tasks/<date>-<area-name>.md with decomposition plan", "dim"))
    print(colorize("    3. Farm each task doc to a sub-agent for implementation", "dim"))
    print()


def _show_review_summary(state: dict):
    """Show review findings summary if any exist."""
    findings = state.get("findings", {})
    review_open = [f for f in findings.values()
                   if f.get("status") == "open" and f.get("detector") == "review"]
    if not review_open:
        return
    uninvestigated = sum(1 for f in review_open
                         if not f.get("detail", {}).get("investigation"))
    parts = [f"{len(review_open)} finding{'s' if len(review_open) != 1 else ''} open"]
    if uninvestigated:
        parts.append(f"{uninvestigated} uninvestigated")
    print(colorize(f"  Review: {', '.join(parts)} — `desloppify issues`", "cyan"))
    # Explain relationship between audit coverage dimension and review findings
    dim_scores = state.get("dimension_scores", {})
    if "Test health" in dim_scores:
        print(colorize("  Test health tracks coverage + review; review findings track issues found.", "dim"))
    print()
