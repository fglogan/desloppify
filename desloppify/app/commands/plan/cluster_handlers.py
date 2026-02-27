"""Plan cluster subcommand handlers."""

from __future__ import annotations

import argparse

from desloppify.app.commands.helpers.runtime import command_runtime
from desloppify.app.commands.helpers.state import require_completed_scan
from desloppify.app.commands.plan._resolve import resolve_ids_from_patterns
from desloppify.core.output_api import colorize
from desloppify.engine.plan import (
    add_to_cluster,
    create_cluster,
    delete_cluster,
    load_plan,
    move_cluster,
    remove_from_cluster,
    save_plan,
)


def _cmd_cluster_create(args: argparse.Namespace) -> None:
    name: str = getattr(args, "cluster_name", "")
    description: str | None = getattr(args, "description", None)
    plan = load_plan()
    try:
        create_cluster(plan, name, description)
    except ValueError as ex:
        print(colorize(f"  {ex}", "red"))
        return
    save_plan(plan)
    print(colorize(f"  Created cluster: {name}", "green"))


def _cmd_cluster_add(args: argparse.Namespace) -> None:
    state = command_runtime(args).state
    if not require_completed_scan(state):
        return

    cluster_name: str = getattr(args, "cluster_name", "")
    patterns: list[str] = getattr(args, "patterns", [])

    finding_ids = resolve_ids_from_patterns(state, patterns)
    if not finding_ids:
        print(colorize("  No matching findings found.", "yellow"))
        return

    plan = load_plan()
    try:
        count = add_to_cluster(plan, cluster_name, finding_ids)
    except ValueError as ex:
        print(colorize(f"  {ex}", "red"))
        return
    save_plan(plan)
    print(colorize(f"  Added {count} item(s) to cluster {cluster_name}.", "green"))


def _cmd_cluster_remove(args: argparse.Namespace) -> None:
    state = command_runtime(args).state
    if not require_completed_scan(state):
        return

    cluster_name: str = getattr(args, "cluster_name", "")
    patterns: list[str] = getattr(args, "patterns", [])

    finding_ids = resolve_ids_from_patterns(state, patterns)
    if not finding_ids:
        print(colorize("  No matching findings found.", "yellow"))
        return

    plan = load_plan()
    try:
        count = remove_from_cluster(plan, cluster_name, finding_ids)
    except ValueError as ex:
        print(colorize(f"  {ex}", "red"))
        return
    save_plan(plan)
    print(colorize(f"  Removed {count} item(s) from cluster {cluster_name}.", "green"))


def _cmd_cluster_delete(args: argparse.Namespace) -> None:
    cluster_name: str = getattr(args, "cluster_name", "")
    plan = load_plan()
    try:
        orphaned = delete_cluster(plan, cluster_name)
    except ValueError as ex:
        print(colorize(f"  {ex}", "red"))
        return
    save_plan(plan)
    print(colorize(f"  Deleted cluster {cluster_name} ({len(orphaned)} items orphaned).", "green"))


def _cmd_cluster_move(args: argparse.Namespace) -> None:
    cluster_name: str = getattr(args, "cluster_name", "")
    position: str = getattr(args, "position", "top")
    target: str | None = getattr(args, "target", None)

    plan = load_plan()

    offset: int | None = None
    if position in ("up", "down") and target is not None:
        try:
            offset = int(target)
        except (ValueError, TypeError):
            print(colorize(f"  Invalid offset: {target}", "red"))
            return
        target = None

    try:
        count = move_cluster(plan, cluster_name, position, target=target, offset=offset)
    except ValueError as ex:
        print(colorize(f"  {ex}", "red"))
        return
    save_plan(plan)
    print(colorize(f"  Moved cluster {cluster_name} ({count} items) to {position}.", "green"))


def _cmd_cluster_list(args: argparse.Namespace) -> None:
    plan = load_plan()
    clusters = plan.get("clusters", {})
    active = plan.get("active_cluster")
    if not clusters:
        print("  No clusters defined.")
        return
    print(colorize("  Clusters:", "bold"))
    for name, cluster in clusters.items():
        member_count = len(cluster.get("finding_ids", []))
        desc = cluster.get("description") or ""
        marker = " (focused)" if name == active else ""
        desc_str = f" — {desc}" if desc else ""
        print(f"    {name}: {member_count} items{desc_str}{marker}")


def cmd_cluster_dispatch(args: argparse.Namespace) -> None:
    """Route cluster subcommands."""
    cluster_action = getattr(args, "cluster_action", None)
    dispatch = {
        "create": _cmd_cluster_create,
        "add": _cmd_cluster_add,
        "remove": _cmd_cluster_remove,
        "delete": _cmd_cluster_delete,
        "move": _cmd_cluster_move,
        "list": _cmd_cluster_list,
    }
    handler = dispatch.get(cluster_action)
    if handler is None:
        _cmd_cluster_list(args)
        return
    handler(args)


__all__ = ["cmd_cluster_dispatch"]
