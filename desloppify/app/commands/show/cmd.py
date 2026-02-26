"""show command: dig into findings by file, directory, detector, or pattern."""

from __future__ import annotations

import argparse

from desloppify import scoring as scoring_mod
from desloppify.app.commands.helpers.lang import resolve_lang
from desloppify.app.commands.helpers.query import write_query
from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.helpers.score import target_strict_score_from_config
from desloppify.app.commands.helpers.state import require_completed_scan
from desloppify.intelligence.narrative import NarrativeContext, compute_narrative
from desloppify.core.output_api import colorize
from desloppify.core.skill_docs import check_skill_version
from desloppify.core.tooling import check_tool_staleness

from .payload import ShowPayloadMeta, build_show_payload
from .render import (
    render_findings,
    show_agent_plan,
    show_subjective_followup,
    write_show_output_file,
)
from .scope import (
    _detector_names_hint,
    load_matches,
    load_matches_for_dimension,
    resolve_noise,
    resolve_show_scope,
)


def _show_concerns(state: dict, lang_name: str | None) -> None:
    """Render current design concerns from mechanical signals."""
    from desloppify.engine.concerns import generate_concerns

    concerns = generate_concerns(state, lang_name=lang_name)
    if not concerns:
        print(colorize("  No design concerns detected.", "green"))
        return

    print(colorize(f"\n  {len(concerns)} design concern(s):\n", "bold"))
    dismissals = state.get("concern_dismissals", {})

    for i, c in enumerate(concerns, 1):
        print(colorize(f"  {i}. [{c.type}] {c.file}", "cyan"))
        print(f"     {c.summary}")
        for ev in c.evidence:
            print(colorize(f"       - {ev}", "dim"))
        print(colorize(f"     ? {c.question}", "yellow"))

        # Check if previously dismissed (but resurface due to changed findings).
        prev = dismissals.get(c.fingerprint)
        if isinstance(prev, dict):
            reasoning = prev.get("reasoning", "")
            if reasoning:
                print(colorize(f"     (previously dismissed: {reasoning})", "dim"))
        print()


def cmd_show(args: argparse.Namespace) -> None:
    """Show all findings for a file, directory, detector, or pattern."""
    runtime = command_runtime(args)
    state = runtime.state
    config = runtime.config

    if not require_completed_scan(state):
        return

    stale_warning = check_tool_staleness(state)
    if stale_warning:
        print(colorize(f"  {stale_warning}", "yellow"))
    skill_warning = check_skill_version()
    if skill_warning:
        print(colorize(f"  {skill_warning}", "yellow"))

    # Handle "show concerns" as a special view.
    pattern_raw = getattr(args, "pattern", "")
    if pattern_raw and pattern_raw.strip().lower() == "concerns":
        lang = resolve_lang(args)
        _show_concerns(state, lang.name if lang else None)
        return

    show_code = getattr(args, "code", False)
    chronic = getattr(args, "chronic", False)
    ok, pattern, status_filter, scope = resolve_show_scope(args)
    if not ok or pattern is None:
        return

    matches = load_matches(state, scope=scope, status_filter=status_filter, chronic=chronic)
    lang = resolve_lang(args)
    lang_name = lang.name if lang else None
    narrative = compute_narrative(
        state,
        context=NarrativeContext(lang=lang_name, command="show"),
    )

    if not matches:
        # Try interpreting the pattern as a dimension name/key
        dim_matches, dim_display = load_matches_for_dimension(
            state, pattern, status_filter=status_filter
        )
        if dim_matches:
            matches = dim_matches
            pattern = dim_display or pattern
        else:
            # Check if this is a subjective dimension (via DISPLAY_NAMES or dimension_scores)
            lowered = pattern_raw.strip().lower().replace(" ", "_") if pattern_raw else ""
            if lowered:
                # 1. Check mechanical dimensions (DIMENSIONS list)
                dim_lookup = {dim.name.lower().replace(" ", "_"): dim for dim in scoring_mod.DIMENSIONS}
                matched_dim = dim_lookup.get(lowered)
                if matched_dim and hasattr(matched_dim, "detectors"):
                    subjective_detectors = {"subjective_assessment", "subjective_review"}
                    if subjective_detectors & set(matched_dim.detectors):
                        matched_dim = None  # fall through to subjective handling below

                # 2. Check DISPLAY_NAMES for subjective dimension keys
                display_name = scoring_mod.DISPLAY_NAMES.get(lowered)
                if not display_name:
                    # Also try matching state dimension_scores keys directly
                    for key in (state.get("dimension_scores") or {}):
                        if key.lower().replace(" ", "_") == lowered:
                            display_name = key
                            break

                if display_name or (matched_dim and hasattr(matched_dim, "detectors")
                                    and {"subjective_assessment", "subjective_review"} & set(matched_dim.detectors)):
                    # Show dimension score if available
                    dim_data = (state.get("dimension_scores") or {}).get(display_name or "", {})
                    if not dim_data and display_name:
                        # Try case-insensitive match on dimension_scores
                        for ds_key, ds_val in (state.get("dimension_scores") or {}).items():
                            if ds_key.lower().replace(" ", "_") == lowered:
                                dim_data = ds_val
                                display_name = ds_key
                                break
                    score_val = dim_data.get("score") if isinstance(dim_data, dict) else None
                    strict_val = dim_data.get("strict", score_val) if isinstance(dim_data, dict) else None
                    if score_val is not None:
                        print(colorize(
                            f"  {display_name}: {score_val:.1f}% health (strict: {strict_val:.1f}%)",
                            "bold",
                        ))
                    print(colorize(
                        f"  '{pattern_raw.strip()}' is a subjective dimension — its score comes from design reviews, not code findings.",
                        "yellow",
                    ))
                    # Count open review findings tagged with this dimension
                    dim_reviews = [
                        f for f in (state.get("findings") or {}).values()
                        if f.get("detector") == "review" and f.get("status") == "open"
                        and lowered in str(f.get("detail", {}).get("dimension", "")).lower().replace(" ", "_")
                    ]
                    if dim_reviews:
                        print(colorize(
                            f"  {len(dim_reviews)} open review finding(s). Run `show review --status open`.",
                            "dim",
                        ))
                    show_subjective_followup(
                        state,
                        target_strict_score_from_config(config, fallback=95.0),
                    )
                    return

            # "show subjective" with no findings still shows the subjective dashboard
            is_subjective_view = pattern_raw and pattern_raw.strip().lower() in (
                "subjective", "subjective_review",
            )
            if is_subjective_view:
                print(colorize(f"No {status_filter} findings matching: {pattern}", "yellow"))
                write_query(
                    {
                        "command": "show",
                        "query": pattern,
                        "status_filter": status_filter,
                        "total": 0,
                        "findings": [],
                        "narrative": narrative,
                    }
                )
                show_subjective_followup(
                    state,
                    target_strict_score_from_config(config, fallback=95.0),
                )
                return

            hint = _detector_names_hint()
            print(
                colorize(
                    f"No {status_filter} findings matching: {pattern}",
                    "yellow",
                )
            )
            print(
                colorize(
                    f"  Try: show <detector>, show <file>, or show subjective. "
                    f"Detectors: {hint}",
                    "dim",
                )
            )
            write_query(
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
    ) = resolve_noise(
        config,
        matches,
    )
    hidden_total = sum(hidden_by_detector.values())

    payload = build_show_payload(
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
    write_query({"command": "show", **payload, "narrative": narrative})

    output_file = getattr(args, "output", None)
    if output_file:
        if write_show_output_file(output_file, payload, len(surfaced_matches)):
            return
        raise SystemExit(1)

    top = getattr(args, "top", 20) or 20
    render_findings(
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
    show_agent_plan(narrative, surfaced_matches)
    show_subjective_followup(
        state,
        target_strict_score_from_config(config, fallback=95.0),
    )

    # Phase 5: naming guide for subjective views
    if pattern_raw and pattern_raw.strip().lower() in ("subjective", "subjective_review"):
        print(colorize("  Related views:", "dim"))
        print(colorize("    `show review --status open`            Per-file design review findings", "dim"))
        print(colorize("    `show subjective_review --status open`  Files needing re-review", "dim"))


__all__ = ["cmd_show"]
