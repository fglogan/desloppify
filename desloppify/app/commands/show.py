"""show command: dig into findings by file, directory, detector, or pattern."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

from desloppify import state as state_mod
from desloppify.intelligence.narrative import compute_narrative
from desloppify.engine.planning.core import CONFIDENCE_ORDER
from desloppify.utils import check_tool_staleness, colorize, read_code_snippet, safe_write_text
from desloppify.engine.work_queue_internal.core import QueueBuildOptions, build_work_queue
from desloppify.app.commands.helpers.lang import resolve_lang
from desloppify.app.commands.helpers.query import write_query

_write_query = write_query
from desloppify.app.commands.helpers.rendering import print_ranked_actions
from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.helpers.score import target_strict_score_from_config
from desloppify.app.commands.helpers.state import require_completed_scan
from desloppify.app.commands.helpers.subjective import print_subjective_followup
from desloppify.app.commands.scan import scan_reporting_dimensions as reporting_dimensions_mod

_DETAIL_DISPLAY = [
    ("line", "line", None),
    ("lines", "lines", lambda v: ", ".join(str(line_no) for line_no in v[:5])),
    ("category", "category", None),
    ("importers", "importers", None),
    ("count", "count", None),
    ("kind", "kind", None),
    ("signals", "signals", lambda v: ", ".join(v[:3])),
    ("concerns", "concerns", lambda v: ", ".join(v[:3])),
    ("hook_total", "hooks", None),
    ("prop_count", "props", None),
    ("smell_id", "smell", None),
    ("target", "target", None),
    ("sole_tool", "sole tool", None),
    ("direction", "direction", None),
    ("family", "family", None),
    ("patterns_used", "patterns", lambda v: ", ".join(v)),
    (
        "related_files",
        "related files",
        lambda v: ", ".join(v[:5]) + (f" +{len(v) - 5}" if len(v) > 5 else ""),
    ),
    ("review", "review", lambda v: v[:80]),
    ("majority", "majority", None),
    ("minority", "minority", None),
    ("outliers", "outliers", lambda v: ", ".join(v[:5])),
]


def _format_detail(detail: dict) -> list[str]:
    """Build display parts from a finding's detail dict."""
    parts = []
    for key, label, formatter in _DETAIL_DISPLAY:
        value = detail.get(key)
        if value is None or value == 0:
            if key == "importers" and value is not None:
                parts.append(f"{label}: {value}")
            continue
        parts.append(f"{label}: {formatter(value) if formatter else value}")

    if detail.get("fn_a"):
        a, b = detail["fn_a"], detail["fn_b"]
        parts.append(
            f"{a['name']}:{a.get('line', '')} ↔ {b['name']}:{b.get('line', '')}"
        )

    return parts


def _resolve_show_scope(args) -> tuple[bool, str | None, str, str]:
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


def _load_matches(
    state: dict, *, scope: str, status_filter: str, chronic: bool
) -> list[dict]:
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


def _resolve_noise(config: dict, matches: list[dict]):
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


def _write_show_query(args, state: dict, payload: dict) -> None:
    lang = resolve_lang(args)
    lang_name = lang.name if lang else None
    narrative = compute_narrative(state, lang=lang_name, command="show")
    _write_query({"command": "show", **payload, "narrative": narrative})


def _show_subjective_followup(state: dict, target_strict_score: float) -> None:
    """Show subjective follow-up guidance for the current state."""
    dim_scores = state.get("dimension_scores", {}) or {}
    if not dim_scores:
        return

    subjective = reporting_dimensions_mod.scorecard_subjective_entries(
        state,
        dim_scores=dim_scores,
    )
    if not subjective:
        return

    followup = reporting_dimensions_mod.build_subjective_followup(
        state,
        subjective,
        threshold=target_strict_score,
        max_quality_items=3,
        max_integrity_items=5,
    )
    if print_subjective_followup(followup):
        print()


def _show_agent_plan(narrative: dict, matches: list[dict]) -> None:
    """Render a compact plan from current findings + narrative actions."""
    actions = narrative.get("actions", [])
    if not actions and not matches:
        return

    print(
        colorize(
            "  AGENT PLAN (use `desloppify next --count 20` to inspect more items):",
            "yellow",
        )
    )
    if actions:
        top = actions[0]
        print(
            colorize(
                f"  Agent focus: `{top['command']}` — {top['description']}", "cyan"
            )
        )
    elif matches:
        first = matches[0]
        print(
            colorize(
                "  Agent focus: `desloppify next --count 20` — "
                f"inspect and resolve `{first.get('id', '')}`",
                "cyan",
            )
        )

    if print_ranked_actions(actions):
        print()


def _write_show_output_file(
    output_file: str, payload: dict, surfaced_count: int
) -> bool:
    try:
        safe_write_text(output_file, json.dumps(payload, indent=2) + "\n")
        print(colorize(f"Wrote {surfaced_count} findings to {output_file}", "green"))
    except OSError as e:
        payload["output_error"] = str(e)
        print(colorize(f"Could not write to {output_file}: {e}", "red"))
        return False
    return True


def _group_matches_by_file(matches: list[dict]) -> list[tuple[str, list]]:
    by_file: dict[str, list] = defaultdict(list)
    for finding in matches:
        by_file[finding["file"]].append(finding)
    return sorted(by_file.items(), key=lambda item: -len(item[1]))


def _render_findings(
    matches: list[dict],
    *,
    pattern: str,
    status_filter: str,
    show_code: bool,
    top: int,
    hidden_by_detector: dict[str, int],
    hidden_total: int,
    noise_budget: int,
    global_noise_budget: int,
    budget_warning: str | None,
) -> None:
    sorted_files = _group_matches_by_file(matches)
    print(
        colorize(
            f"\n  {len(matches)} {status_filter} findings matching '{pattern}'\n",
            "bold",
        )
    )
    if budget_warning:
        print(colorize(f"  {budget_warning}\n", "yellow"))
    if hidden_total:
        global_label = (
            f", {global_noise_budget} global" if global_noise_budget > 0 else ""
        )
        hidden_parts = ", ".join(
            f"{det}: +{count}" for det, count in hidden_by_detector.items()
        )
        print(
            colorize(
                f"  Noise budget: {noise_budget}/detector{global_label} ({hidden_total} hidden: {hidden_parts})\n",
                "dim",
            )
        )

    shown_files = sorted_files[:top]
    remaining_files = sorted_files[top:]
    remaining_findings = sum(len(files) for _, files in remaining_files)

    for filepath, findings in shown_files:
        findings.sort(
            key=lambda finding: (
                finding["tier"],
                CONFIDENCE_ORDER.get(finding["confidence"], 9),
            )
        )
        display_path = "Codebase-wide" if filepath == "." else filepath
        print(
            colorize(f"  {display_path}", "cyan")
            + colorize(f"  ({len(findings)} findings)", "dim")
        )

        for finding in findings:
            status_icon = {
                "open": "○",
                "fixed": "✓",
                "wontfix": "—",
                "false_positive": "✗",
                "auto_resolved": "◌",
            }.get(finding["status"], "?")
            zone = finding.get("zone", "production")
            zone_tag = colorize(f" [{zone}]", "dim") if zone != "production" else ""
            print(
                f"    {status_icon} T{finding['tier']} [{finding['confidence']}] {finding['summary']}{zone_tag}"
            )

            detail_parts = _format_detail(finding.get("detail", {}))
            if detail_parts:
                print(colorize(f"      {' · '.join(detail_parts)}", "dim"))
            if show_code:
                detail = finding.get("detail", {})
                target_line = (
                    detail.get("line") or (detail.get("lines", [None]) or [None])[0]
                )
                if target_line and finding["file"] not in (".", ""):
                    snippet = read_code_snippet(finding["file"], target_line)
                    if snippet:
                        print(snippet)
            if finding.get("reopen_count", 0) >= 2:
                print(
                    colorize(
                        f"      ⟳ reopened {finding['reopen_count']} times — fix properly or wontfix",
                        "red",
                    )
                )
            if finding.get("note"):
                print(colorize(f"      note: {finding['note']}", "dim"))
            print(colorize(f"      {finding['id']}", "dim"))
        print()

    if remaining_findings:
        print(
            colorize(
                f"  ... and {len(remaining_files)} more files ({remaining_findings} findings). "
                f"Use --top {top + 20} to see more.\n",
                "dim",
            )
        )

    by_detector: dict[str, int] = defaultdict(int)
    by_tier: dict[int, int] = defaultdict(int)
    for finding in matches:
        by_detector[finding["detector"]] += 1
        by_tier[finding["tier"]] += 1

    print(colorize("  Summary:", "bold"))
    print(
        colorize(
            f"    By tier:     {', '.join(f'T{tier}:{count}' for tier, count in sorted(by_tier.items()))}",
            "dim",
        )
    )
    print(
        colorize(
            f"    By detector: {', '.join(f'{detector}:{count}' for detector, count in sorted(by_detector.items(), key=lambda item: -item[1]))}",
            "dim",
        )
    )
    if hidden_total:
        print(
            colorize(
                f"    Hidden:      {', '.join(f'{detector}:+{count}' for detector, count in hidden_by_detector.items())}",
                "dim",
            )
        )
    print()


def cmd_show(args) -> None:
    """Show all findings for a file, directory, detector, or pattern."""
    runtime = command_runtime(args)
    state = runtime.state
    config = runtime.config

    if not require_completed_scan(state):
        return

    stale_warning = check_tool_staleness(state)
    if stale_warning:
        print(colorize(f"  {stale_warning}", "yellow"))

    show_code = getattr(args, "code", False)
    chronic = getattr(args, "chronic", False)
    ok, pattern, status_filter, scope = _resolve_show_scope(args)
    if not ok or pattern is None:
        return

    matches = _load_matches(
        state, scope=scope, status_filter=status_filter, chronic=chronic
    )
    lang = resolve_lang(args)
    lang_name = lang.name if lang else None
    narrative = compute_narrative(state, lang=lang_name, command="show")

    if not matches:
        print(colorize(f"No {status_filter} findings matching: {pattern}", "yellow"))
        _write_query(
            {
                "command": "show",
                "query": pattern,
                "status_filter": status_filter,
                "total": 0,
                "findings": [],
                "narrative": narrative,
            }
        )
        return

    (
        surfaced_matches,
        hidden_by_detector,
        noise_budget,
        global_noise_budget,
        budget_warning,
    ) = _resolve_noise(
        config,
        matches,
    )
    hidden_total = sum(hidden_by_detector.values())

    payload = _build_show_payload(
        surfaced_matches,
        pattern,
        status_filter,
        ShowPayloadMeta(
            total_matches=len(matches),
            hidden_by_detector=hidden_by_detector,
            noise_budget=noise_budget,
            global_noise_budget=global_noise_budget,
        ),
    )
    _write_query({"command": "show", **payload, "narrative": narrative})

    output_file = getattr(args, "output", None)
    if output_file:
        if _write_show_output_file(output_file, payload, len(surfaced_matches)):
            return
        raise SystemExit(1)

    top = getattr(args, "top", 20) or 20
    _render_findings(
        surfaced_matches,
        pattern=pattern,
        status_filter=status_filter,
        show_code=show_code,
        top=top,
        hidden_by_detector=hidden_by_detector,
        hidden_total=hidden_total,
        noise_budget=noise_budget,
        global_noise_budget=global_noise_budget,
        budget_warning=budget_warning,
    )
    _show_agent_plan(narrative, surfaced_matches)
    _show_subjective_followup(
        state,
        target_strict_score_from_config(config, fallback=95.0),
    )


@dataclass(frozen=True)
class ShowPayloadMeta:
    total_matches: int | None = None
    hidden_by_detector: dict[str, int] | None = None
    noise_budget: int | None = None
    global_noise_budget: int | None = None


def _build_show_payload(
    matches: list[dict],
    pattern: str,
    status_filter: str,
    meta: ShowPayloadMeta | None = None,
    **legacy_meta: object,
) -> dict:
    """Build the structured JSON payload shared by query file and --output."""
    if meta is not None and legacy_meta:
        raise ValueError(
            "Pass either meta=ShowPayloadMeta(...) or legacy keyword metadata, not both."
        )

    resolved_meta = meta
    if resolved_meta is None:
        total_matches = legacy_meta.get("total_matches")
        hidden_by_detector = legacy_meta.get("hidden_by_detector")
        noise_budget = legacy_meta.get("noise_budget")
        global_noise_budget = legacy_meta.get("global_noise_budget")

        resolved_meta = ShowPayloadMeta(
            total_matches=total_matches if isinstance(total_matches, int) else None,
            hidden_by_detector=hidden_by_detector
            if isinstance(hidden_by_detector, dict)
            else None,
            noise_budget=noise_budget if isinstance(noise_budget, int) else None,
            global_noise_budget=(
                global_noise_budget if isinstance(global_noise_budget, int) else None
            ),
        )

    by_file: dict[str, list] = defaultdict(list)
    by_detector: dict[str, int] = defaultdict(int)
    by_tier: dict[int, int] = defaultdict(int)
    for finding in matches:
        by_file[finding["file"]].append(finding)
        by_detector[finding["detector"]] += 1
        by_tier[finding["tier"]] += 1

    payload = {
        "query": pattern,
        "status_filter": status_filter,
        "total": len(matches),
        "summary": {
            "by_tier": {f"T{tier}": count for tier, count in sorted(by_tier.items())},
            "by_detector": dict(sorted(by_detector.items(), key=lambda item: -item[1])),
            "files": len(by_file),
        },
        "by_file": {
            fp: [
                {
                    "id": f["id"],
                    "tier": f["tier"],
                    "confidence": f["confidence"],
                    "summary": f["summary"],
                    "detail": f.get("detail", {}),
                }
                for f in fs
            ]
            for fp, fs in sorted(by_file.items(), key=lambda x: -len(x[1]))
        },
    }
    if resolved_meta.total_matches is not None:
        payload["total_matching"] = resolved_meta.total_matches
    if resolved_meta.hidden_by_detector:
        payload["hidden"] = {
            "by_detector": resolved_meta.hidden_by_detector,
            "total": sum(resolved_meta.hidden_by_detector.values()),
        }
    if resolved_meta.noise_budget is not None:
        payload["noise_budget"] = resolved_meta.noise_budget
    if resolved_meta.global_noise_budget is not None:
        payload["noise_global_budget"] = resolved_meta.global_noise_budget
    return payload
