"""Plan override subcommand handlers: describe, annotate, skip, unskip, done, reopen, focus."""

from __future__ import annotations

import argparse
import sys

from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.helpers.state import require_completed_scan
from desloppify.app.commands.plan._resolve import resolve_ids_from_patterns
from desloppify.core.output_api import colorize
from desloppify.engine.plan import (
    clear_focus,
    load_plan,
    save_plan,
    set_focus,
    skip_items,
    unskip_items,
)


def cmd_plan_describe(args: argparse.Namespace) -> None:
    """Set augmented description on findings."""
    state = command_runtime(args).state
    if not require_completed_scan(state):
        return

    patterns: list[str] = getattr(args, "patterns", [])
    text: str = getattr(args, "text", "")

    finding_ids = resolve_ids_from_patterns(state, patterns)
    if not finding_ids:
        print(colorize("  No matching findings found.", "yellow"))
        return

    from desloppify.engine.plan import describe_finding

    plan = load_plan()
    for fid in finding_ids:
        describe_finding(plan, fid, text or None)
    save_plan(plan)
    print(colorize(f"  Set description on {len(finding_ids)} finding(s).", "green"))


def cmd_plan_annotate(args: argparse.Namespace) -> None:
    """Set note on findings."""
    state = command_runtime(args).state
    if not require_completed_scan(state):
        return

    patterns: list[str] = getattr(args, "patterns", [])
    note: str | None = getattr(args, "note", None)

    finding_ids = resolve_ids_from_patterns(state, patterns)
    if not finding_ids:
        print(colorize("  No matching findings found.", "yellow"))
        return

    from desloppify.engine.plan import annotate_finding

    plan = load_plan()
    for fid in finding_ids:
        annotate_finding(plan, fid, note)
    save_plan(plan)
    print(colorize(f"  Set note on {len(finding_ids)} finding(s).", "green"))


# ---------------------------------------------------------------------------
# Skip / unskip
# ---------------------------------------------------------------------------

def cmd_plan_skip(args: argparse.Namespace) -> None:
    """Skip findings — unified command for temporary/permanent/false-positive."""
    from desloppify.app.commands.resolve.selection import (
        _show_attestation_requirement,
        _validate_attestation,
    )
    from desloppify.engine.work_queue import ATTEST_EXAMPLE

    state = command_runtime(args).state
    if not require_completed_scan(state):
        return

    patterns: list[str] = getattr(args, "patterns", [])
    reason: str | None = getattr(args, "reason", None)
    review_after: int | None = getattr(args, "review_after", None)
    permanent: bool = getattr(args, "permanent", False)
    false_positive: bool = getattr(args, "false_positive", False)
    note: str | None = getattr(args, "note", None)
    attestation: str | None = getattr(args, "attest", None)

    # Determine skip kind
    if false_positive:
        kind = "false_positive"
    elif permanent:
        kind = "permanent"
    else:
        kind = "temporary"

    # Validate requirements for permanent/false_positive
    if kind in ("permanent", "false_positive"):
        if not _validate_attestation(attestation):
            _show_attestation_requirement(
                "Permanent skip" if kind == "permanent" else "False positive",
                attestation,
                ATTEST_EXAMPLE,
            )
            return
        if kind == "permanent" and not note:
            print(
                colorize("  --permanent requires --note to explain the decision.", "yellow"),
                file=sys.stderr,
            )
            return

    finding_ids = resolve_ids_from_patterns(state, patterns)
    if not finding_ids:
        print(colorize("  No matching findings found.", "yellow"))
        return

    # For permanent/false_positive: delegate to state layer for score impact
    if kind in ("permanent", "false_positive"):
        from desloppify import state as state_mod
        from desloppify.app.commands.helpers.state import state_path

        state_file = state_path(args)
        state_data = state_mod.load_state(state_file)
        status = "wontfix" if kind == "permanent" else "false_positive"
        resolved: list[str] = []
        for fid in finding_ids:
            resolved.extend(
                state_mod.resolve_findings(
                    state_data, fid, status, note or "", attestation=attestation
                )
            )
        if resolved:
            state_mod.save_state(state_data, state_file)

    scan_count = state.get("scan_count", 0)
    plan = load_plan()
    count = skip_items(
        plan,
        finding_ids,
        kind=kind,
        reason=reason,
        note=note,
        attestation=attestation,
        review_after=review_after,
        scan_count=scan_count,
    )
    save_plan(plan)

    label = {"temporary": "Skipped", "permanent": "Wontfixed", "false_positive": "Marked false positive"}
    print(colorize(f"  {label[kind]} {count} item(s).", "green"))
    if review_after:
        print(colorize(f"  Will re-surface after {review_after} scan(s).", "dim"))


def cmd_plan_unskip(args: argparse.Namespace) -> None:
    """Unskip findings — bring back to queue."""
    state = command_runtime(args).state
    if not require_completed_scan(state):
        return

    patterns: list[str] = getattr(args, "patterns", [])
    # For unskip we need to match against all statuses (skipped items may be wontfix/fp)
    finding_ids = resolve_ids_from_patterns(state, patterns, status_filter="all")
    if not finding_ids:
        print(colorize("  No matching findings found.", "yellow"))
        return

    plan = load_plan()
    count, need_reopen = unskip_items(plan, finding_ids)
    save_plan(plan)

    # Reopen permanent/false_positive items in state
    if need_reopen:
        from desloppify import state as state_mod
        from desloppify.app.commands.helpers.state import state_path

        state_file = state_path(args)
        state_data = state_mod.load_state(state_file)
        reopened: list[str] = []
        for fid in need_reopen:
            reopened.extend(state_mod.resolve_findings(state_data, fid, "open"))
        if reopened:
            state_mod.save_state(state_data, state_file)
        print(colorize(f"  Reopened {len(reopened)} finding(s) in state.", "dim"))

    print(colorize(f"  Unskipped {count} item(s) — back in queue.", "green"))


# ---------------------------------------------------------------------------
# Done / reopen
# ---------------------------------------------------------------------------

def cmd_plan_done(args: argparse.Namespace) -> None:
    """Mark findings as fixed from plan context."""
    from desloppify import state as state_mod
    from desloppify.app.commands.helpers.state import state_path
    from desloppify.app.commands.resolve.selection import (
        _show_attestation_requirement,
        _validate_attestation,
    )
    from desloppify.engine.plan import purge_ids
    from desloppify.engine.work_queue import ATTEST_EXAMPLE

    attestation: str | None = getattr(args, "attest", None)
    patterns: list[str] = getattr(args, "patterns", [])

    if not _validate_attestation(attestation):
        _show_attestation_requirement("Done", attestation, ATTEST_EXAMPLE)
        return

    state_file = state_path(args)
    state_data = state_mod.load_state(state_file)

    resolved: list[str] = []
    for pattern in patterns:
        resolved.extend(
            state_mod.resolve_findings(state_data, pattern, "fixed", attestation=attestation)
        )

    if not resolved:
        print(colorize("  No open findings matching: " + " ".join(patterns), "yellow"))
        return

    state_mod.save_state(state_data, state_file)

    plan = load_plan()
    purged = purge_ids(plan, resolved)
    if purged:
        save_plan(plan)

    print(colorize(f"  Marked {len(resolved)} finding(s) as fixed.", "green"))
    if purged:
        print(colorize(f"  Plan updated: {purged} item(s) purged.", "dim"))


def cmd_plan_reopen(args: argparse.Namespace) -> None:
    """Reopen resolved findings from plan context."""
    from desloppify import state as state_mod
    from desloppify.app.commands.helpers.state import state_path

    patterns: list[str] = getattr(args, "patterns", [])

    state_file = state_path(args)
    state_data = state_mod.load_state(state_file)

    reopened: list[str] = []
    for pattern in patterns:
        reopened.extend(
            state_mod.resolve_findings(state_data, pattern, "open")
        )

    if not reopened:
        print(colorize("  No resolved findings matching: " + " ".join(patterns), "yellow"))
        return

    state_mod.save_state(state_data, state_file)

    # Remove from skipped if present
    plan = load_plan()
    skipped = plan.get("skipped", {})
    removed = 0
    for fid in reopened:
        if fid in skipped:
            skipped.pop(fid)
            if fid not in plan.get("queue_order", []):
                plan["queue_order"].append(fid)
            removed += 1
    if removed:
        save_plan(plan)

    print(colorize(f"  Reopened {len(reopened)} finding(s).", "green"))
    if removed:
        print(colorize(f"  Plan updated: {removed} item(s) moved back to queue.", "dim"))


# ---------------------------------------------------------------------------
# Deprecated: defer / undefer / wontfix
# ---------------------------------------------------------------------------

def cmd_plan_defer(args: argparse.Namespace) -> None:
    """Defer findings (hide from next).

    .. deprecated:: Use ``plan skip`` instead.
    """
    print(
        colorize("  Warning: `plan defer` is deprecated. Use `plan skip` instead.", "yellow"),
        file=sys.stderr,
    )
    state = command_runtime(args).state
    if not require_completed_scan(state):
        return

    patterns: list[str] = getattr(args, "patterns", [])
    finding_ids = resolve_ids_from_patterns(state, patterns)
    if not finding_ids:
        print(colorize("  No matching findings found.", "yellow"))
        return

    scan_count = state.get("scan_count", 0)
    plan = load_plan()
    count = skip_items(plan, finding_ids, kind="temporary", scan_count=scan_count)
    save_plan(plan)
    print(colorize(f"  Skipped {count} item(s).", "green"))


def cmd_plan_undefer(args: argparse.Namespace) -> None:
    """Undefer findings (bring back to queue).

    .. deprecated:: Use ``plan unskip`` instead.
    """
    print(
        colorize("  Warning: `plan undefer` is deprecated. Use `plan unskip` instead.", "yellow"),
        file=sys.stderr,
    )
    state = command_runtime(args).state
    if not require_completed_scan(state):
        return

    patterns: list[str] = getattr(args, "patterns", [])
    finding_ids = resolve_ids_from_patterns(state, patterns, status_filter="all")
    if not finding_ids:
        print(colorize("  No matching findings found.", "yellow"))
        return

    plan = load_plan()
    count, _ = unskip_items(plan, finding_ids)
    save_plan(plan)
    print(colorize(f"  Unskipped {count} item(s).", "green"))


def cmd_plan_wontfix(args: argparse.Namespace) -> None:
    """Wontfix findings via the plan interface.

    .. deprecated:: Use ``plan skip --permanent`` instead.
    """
    print(
        colorize("  Warning: `plan wontfix` is deprecated. Use `plan skip --permanent` instead.", "yellow"),
        file=sys.stderr,
    )
    from desloppify import state as state_mod
    from desloppify.app.commands.helpers.state import state_path
    from desloppify.app.commands.resolve.selection import (
        _show_attestation_requirement,
        _validate_attestation,
    )
    from desloppify.engine.plan import purge_ids
    from desloppify.engine.work_queue import ATTEST_EXAMPLE

    attestation: str = getattr(args, "attest", "")
    note: str = getattr(args, "note", "")
    patterns: list[str] = getattr(args, "patterns", [])

    if not _validate_attestation(attestation):
        _show_attestation_requirement("Wontfix", attestation, ATTEST_EXAMPLE)
        return

    state_file = state_path(args)
    state = state_mod.load_state(state_file)

    resolved: list[str] = []
    for pattern in patterns:
        resolved.extend(
            state_mod.resolve_findings(state, pattern, "wontfix", note, attestation=attestation)
        )

    if not resolved:
        print(colorize("  No open findings matching: " + " ".join(patterns), "yellow"))
        return

    state_mod.save_state(state, state_file)

    plan = load_plan()
    purged = purge_ids(plan, resolved)
    if purged:
        save_plan(plan)

    print(colorize(f"  Wontfixed {len(resolved)} finding(s).", "green"))
    if purged:
        print(colorize(f"  Plan updated: {purged} item(s) removed from queue.", "dim"))


def cmd_plan_focus(args: argparse.Namespace) -> None:
    """Set or clear the active cluster focus."""
    clear_flag = getattr(args, "clear", False)
    cluster_name: str | None = getattr(args, "cluster_name", None)

    plan = load_plan()
    if clear_flag:
        clear_focus(plan)
        save_plan(plan)
        print(colorize("  Focus cleared.", "green"))
        return

    if not cluster_name:
        active = plan.get("active_cluster")
        if active:
            print(f"  Focused on: {active}")
        else:
            print("  No active focus.")
        return

    try:
        set_focus(plan, cluster_name)
    except ValueError as ex:
        print(colorize(f"  {ex}", "red"))
        return
    save_plan(plan)
    print(colorize(f"  Focused on: {cluster_name}", "green"))


__all__ = [
    "cmd_plan_annotate",
    "cmd_plan_defer",
    "cmd_plan_describe",
    "cmd_plan_done",
    "cmd_plan_focus",
    "cmd_plan_reopen",
    "cmd_plan_skip",
    "cmd_plan_undefer",
    "cmd_plan_unskip",
    "cmd_plan_wontfix",
]
