"""Resolve findings or apply ignore-pattern suppressions."""

from __future__ import annotations

import argparse
import copy
import sys
from dataclasses import dataclass

from desloppify.core import config as config_mod
from desloppify.intelligence import narrative as narrative_mod
from desloppify import state as state_mod
from desloppify.utils import colorize
from desloppify.engine.work_queue_internal.core import ATTEST_EXAMPLE
from desloppify.app.commands.helpers.lang import resolve_lang
from desloppify.app.commands.helpers.query import write_query

_write_query = write_query
from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.helpers.state import state_path

_REQUIRED_ATTESTATION_PHRASES = ("i have actually", "not gaming")
_ATTESTATION_KEYWORD_HINT = ("I have actually", "not gaming")


@dataclass(frozen=True)
class ResolveQueryContext:
    patterns: list[str]
    status: str
    resolved: list[str]
    next_command: str
    prev_overall: float | None
    prev_objective: float | None
    prev_strict: float | None
    prev_verified: float | None
    attestation: str | None
    narrative: dict
    state: dict


def _missing_attestation_keywords(attestation: str | None) -> list[str]:
    normalized = " ".join((attestation or "").strip().lower().split())
    return [
        phrase for phrase in _REQUIRED_ATTESTATION_PHRASES if phrase not in normalized
    ]


def _validate_attestation(attestation: str | None) -> bool:
    return not _missing_attestation_keywords(attestation)


def _show_attestation_requirement(
    label: str, attestation: str | None, example: str
) -> None:
    missing = _missing_attestation_keywords(attestation)
    if not attestation:
        print(colorize(f"{label} requires --attest.", "yellow"))
    elif missing:
        missing_str = ", ".join(f"'{keyword}'" for keyword in missing)
        print(
            colorize(
                f"{label} attestation is missing required keyword(s): {missing_str}.",
                "yellow",
            )
        )
    print(
        colorize(
            f"Required keywords: '{_ATTESTATION_KEYWORD_HINT[0]}' and '{_ATTESTATION_KEYWORD_HINT[1]}'.",
            "yellow",
        )
    )
    print(colorize(f'Example: --attest "{example}"', "dim"))


def _assessment_score(value: object) -> float:
    raw = value.get("score", 0) if isinstance(value, dict) else value
    try:
        score = float(raw)
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(100.0, score))


def _validate_resolve_inputs(args: argparse.Namespace, attestation: str | None) -> None:
    if args.status == "wontfix" and not args.note:
        print(
            colorize(
                "Wontfix items become technical debt. Add --note to record your reasoning for future review.",
                "yellow",
            )
        )
        sys.exit(1)
    if not _validate_attestation(attestation):
        _show_attestation_requirement("Manual resolve", attestation, ATTEST_EXAMPLE)
        sys.exit(1)


def _previous_score_snapshot(
    state: dict,
) -> tuple[float | None, float | None, float | None, float | None]:
    return (
        state_mod.get_overall_score(state),
        state_mod.get_objective_score(state),
        state_mod.get_strict_score(state),
        state_mod.get_verified_strict_score(state),
    )


def _resolve_all_patterns(
    state: dict, args: argparse.Namespace, *, attestation: str | None
) -> list[str]:
    all_resolved: list[str] = []
    for pattern in args.patterns:
        resolved = state_mod.resolve_findings(
            state,
            pattern,
            args.status,
            args.note,
            attestation=attestation,
        )
        all_resolved.extend(resolved)
    return all_resolved


def _preview_resolve_count(state: dict, patterns: list[str]) -> int:
    """Count unique open findings matching the provided patterns."""
    matched_ids: set[str] = set()
    for pattern in patterns:
        for finding in state_mod.match_findings(state, pattern, status_filter="open"):
            finding_id = finding.get("id")
            if finding_id:
                matched_ids.add(finding_id)
    return len(matched_ids)


def _estimate_wontfix_strict_delta(
    state: dict, args: argparse.Namespace, *, attestation: str | None
) -> float:
    """Estimate strict score drop if this resolve command is applied as wontfix."""
    before = state_mod.get_strict_score(state)
    if before is None:
        return 0.0

    preview_state = copy.deepcopy(state)
    _resolve_all_patterns(preview_state, args, attestation=attestation)
    after = state_mod.get_strict_score(preview_state)
    if after is None:
        return 0.0
    return max(0.0, before - after)


def _enforce_batch_wontfix_confirmation(
    state: dict,
    args: argparse.Namespace,
    *,
    attestation: str | None,
) -> None:
    if args.status != "wontfix":
        return

    preview_count = _preview_resolve_count(state, args.patterns)
    if preview_count <= 10:
        return
    if getattr(args, "confirm_batch_wontfix", False):
        return

    strict_delta = _estimate_wontfix_strict_delta(state, args, attestation=attestation)
    print(
        colorize(
            f"Large wontfix batch detected ({preview_count} findings).",
            "yellow",
        )
    )
    if strict_delta > 0:
        print(
            colorize(
                f"Estimated strict-score debt added now: {strict_delta:.1f} points.",
                "yellow",
            )
        )
    print(
        colorize(
            "Re-run with --confirm-batch-wontfix if this debt is intentional.",
            "yellow",
        )
    )
    sys.exit(1)


def _print_resolve_summary(*, status: str, all_resolved: list[str]) -> None:
    print(colorize(f"\nResolved {len(all_resolved)} finding(s) as {status}:", "green"))
    for fid in all_resolved[:20]:
        print(f"  {fid}")
    if len(all_resolved) > 20:
        print(f"  ... and {len(all_resolved) - 20} more")


def _print_wontfix_batch_warning(
    state: dict, *, status: str, resolved_count: int
) -> None:
    if status != "wontfix" or resolved_count <= 10:
        return
    wontfix_count = sum(
        1 for f in state["findings"].values() if f["status"] == "wontfix"
    )
    actionable = sum(
        1
        for f in state["findings"].values()
        if f["status"]
        in ("open", "wontfix", "fixed", "auto_resolved", "false_positive")
    )
    wontfix_pct = round(wontfix_count / actionable * 100) if actionable else 0
    print(
        colorize(
            f"\n  \u26a0 Wontfix debt is now {wontfix_count} findings ({wontfix_pct}% of actionable).",
            "yellow",
        )
    )
    print(
        colorize(
            '    The strict score reflects this. Run `desloppify show "*" --status wontfix` to review.',
            "dim",
        )
    )


def _delta_suffix(delta: float) -> str:
    if abs(delta) < 0.05:
        return ""
    return f" ({'+' if delta > 0 else ''}{delta:.1f})"


def _print_score_movement(
    *,
    status: str,
    prev_overall: float | None,
    prev_objective: float | None,
    prev_strict: float | None,
    prev_verified: float | None,
    state: dict,
) -> None:
    new_overall = state_mod.get_overall_score(state)
    new_objective = state_mod.get_objective_score(state)
    new_strict = state_mod.get_strict_score(state)
    new_verified = state_mod.get_verified_strict_score(state)
    if (
        new_overall is None
        or new_objective is None
        or new_strict is None
        or new_verified is None
    ):
        print(colorize("\n  Scores unavailable — run `desloppify scan`.", "yellow"))
        return

    overall_delta = new_overall - (prev_overall or 0)
    objective_delta = new_objective - (prev_objective or 0)
    strict_delta = new_strict - (prev_strict or 0)
    verified_delta = new_verified - (prev_verified or 0)
    print(
        f"\n  Scores: overall {new_overall:.1f}/100{_delta_suffix(overall_delta)}"
        + colorize(
            f"  objective {new_objective:.1f}/100{_delta_suffix(objective_delta)}",
            "dim",
        )
        + colorize(f"  strict {new_strict:.1f}/100{_delta_suffix(strict_delta)}", "dim")
        + colorize(
            f"  verified {new_verified:.1f}/100{_delta_suffix(verified_delta)}", "dim"
        )
    )
    if status == "fixed":
        print(
            colorize(
                "  Verified score updates after a scan confirms the finding disappeared.",
                "yellow",
            )
        )


def _print_subjective_reset_hint(
    *,
    args: argparse.Namespace,
    state: dict,
    all_resolved: list[str],
    prev_subjective_scores: dict[str, float],
) -> None:
    has_review = any(
        state["findings"].get(fid, {}).get("detector") == "review"
        for fid in all_resolved
    )
    if (
        args.status != "fixed"
        or not has_review
        or not state.get("subjective_assessments")
    ):
        return

    reset_dims = sorted(
        dim
        for dim in {
            str(
                state["findings"].get(fid, {}).get("detail", {}).get("dimension", "")
            ).strip()
            for fid in all_resolved
            if state["findings"].get(fid, {}).get("detector") == "review"
        }
        if dim
        and prev_subjective_scores.get(dim, 0.0) > 0.0
        and _assessment_score((state.get("subjective_assessments") or {}).get(dim))
        <= 0.0
    )
    if not reset_dims:
        return

    shown = ", ".join(reset_dims[:3])
    if len(reset_dims) > 3:
        shown = f"{shown}, +{len(reset_dims) - 3} more"
    print(
        colorize(
            f"  Reset subjective score(s) to 0 pending re-review: {shown}", "yellow"
        )
    )
    print(
        colorize(
            "  Next subjective step: "
            + f"`desloppify review --prepare --dimensions {','.join(reset_dims)}`",
            "dim",
        )
    )


def _print_next_command(state: dict) -> str:
    remaining = sum(
        1
        for finding in state["findings"].values()
        if finding["status"] == "open" and finding.get("detector") == "review"
    )
    next_command = "desloppify scan"
    if remaining > 0:
        s = "s" if remaining != 1 else ""
        print(
            colorize(
                f"\n  {remaining} review finding{s} remaining — run `desloppify issues`",
                "dim",
            )
        )
        next_command = "desloppify issues"
    print(colorize(f"  Next command: `{next_command}`", "dim"))
    print()
    return next_command


def _write_resolve_query_entry(
    context: ResolveQueryContext,
) -> None:
    _write_query(
        {
            "command": "resolve",
            "patterns": context.patterns,
            "status": context.status,
            "resolved": context.resolved,
            "count": len(context.resolved),
            "next_command": context.next_command,
            "overall_score": state_mod.get_overall_score(context.state),
            "objective_score": state_mod.get_objective_score(context.state),
            "strict_score": state_mod.get_strict_score(context.state),
            "verified_strict_score": state_mod.get_verified_strict_score(context.state),
            "prev_overall_score": context.prev_overall,
            "prev_objective_score": context.prev_objective,
            "prev_strict_score": context.prev_strict,
            "prev_verified_strict_score": context.prev_verified,
            "attestation": context.attestation,
            "narrative": context.narrative,
        }
    )


def cmd_resolve(args: argparse.Namespace) -> None:
    """Resolve finding(s) matching one or more patterns."""
    attestation = getattr(args, "attest", None)
    _validate_resolve_inputs(args, attestation)

    sp = state_path(args)
    state = state_mod.load_state(sp)
    _enforce_batch_wontfix_confirmation(state, args, attestation=attestation)
    prev_overall, prev_objective, prev_strict, prev_verified = _previous_score_snapshot(
        state
    )
    prev_subjective_scores = {
        str(dim): _assessment_score(payload)
        for dim, payload in (state.get("subjective_assessments") or {}).items()
        if isinstance(dim, str)
    }

    all_resolved = _resolve_all_patterns(state, args, attestation=attestation)
    if not all_resolved:
        print(
            colorize(f"No open findings matching: {' '.join(args.patterns)}", "yellow")
        )
        return

    state_mod.save_state(state, sp)
    _print_resolve_summary(status=args.status, all_resolved=all_resolved)
    _print_wontfix_batch_warning(
        state, status=args.status, resolved_count=len(all_resolved)
    )
    _print_score_movement(
        status=args.status,
        prev_overall=prev_overall,
        prev_objective=prev_objective,
        prev_strict=prev_strict,
        prev_verified=prev_verified,
        state=state,
    )
    _print_subjective_reset_hint(
        args=args,
        state=state,
        all_resolved=all_resolved,
        prev_subjective_scores=prev_subjective_scores,
    )

    # Computed narrative: milestone + context for LLM
    lang = resolve_lang(args)
    lang_name = lang.name if lang else None
    narrative = narrative_mod.compute_narrative(
        state, lang=lang_name, command="resolve"
    )
    if narrative.get("milestone"):
        print(colorize(f"  → {narrative['milestone']}", "green"))

    next_command = _print_next_command(state)
    _write_resolve_query_entry(
        ResolveQueryContext(
            patterns=args.patterns,
            status=args.status,
            resolved=all_resolved,
            next_command=next_command,
            prev_overall=prev_overall,
            prev_objective=prev_objective,
            prev_strict=prev_strict,
            prev_verified=prev_verified,
            attestation=attestation,
            narrative=narrative,
            state=state,
        )
    )


def cmd_ignore_pattern(args: argparse.Namespace) -> None:
    """Add a pattern to the ignore list."""
    attestation = getattr(args, "attest", None)
    if not _validate_attestation(attestation):
        _show_attestation_requirement("Ignore", attestation, ATTEST_EXAMPLE)
        sys.exit(1)

    sp = state_path(args)
    state = state_mod.load_state(sp)

    config = command_runtime(args).config
    config_mod.add_ignore_pattern(config, args.pattern)
    config_mod.save_config(config)

    removed = state_mod.remove_ignored_findings(state, args.pattern)
    state.setdefault("attestation_log", []).append(
        {
            "timestamp": state.get("last_scan"),
            "command": "ignore",
            "pattern": args.pattern,
            "attestation": attestation,
            "affected": removed,
        }
    )
    state_mod.save_state(state, sp)

    if len(normalized) == 1:
        print(colorize(f"Added ignore pattern: {normalized[0]}", "green"))
    else:
        print(colorize(f"Added {len(normalized)} ignore patterns:", "green"))
        for pattern in normalized:
            print(f"  {pattern}")
    print(colorize(f"  Note: {note}", "dim"))
    if removed:
        print(f"  Removed {removed} matching findings from state.")
    overall = state_mod.get_overall_score(state)
    objective = state_mod.get_objective_score(state)
    strict = state_mod.get_strict_score(state)
    verified = state_mod.get_verified_strict_score(state)
    if (
        overall is not None
        and objective is not None
        and strict is not None
        and verified is not None
    ):
        print(
            f"  Scores: overall {overall:.1f}/100"
            + colorize(f"  objective: {objective:.1f}/100", "dim")
            + colorize(f"  strict: {strict:.1f}/100", "dim")
            + colorize(f"  verified: {verified:.1f}/100", "dim")
        )
    print()

    lang = resolve_lang(args)
    lang_name = lang.name if lang else None
    narrative = narrative_mod.compute_narrative(state, lang=lang_name, command="ignore")
    _write_query(
        {
            "command": "ignore",
            "pattern": args.pattern,
            "removed": removed,
            "overall_score": overall,
            "objective_score": objective,
            "strict_score": strict,
            "verified_strict_score": verified,
            "attestation": attestation,
            "narrative": narrative,
        }
    )
