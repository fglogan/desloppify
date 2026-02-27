"""Unified work-queue selection for next/show/plan views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from desloppify.engine._work_queue.helpers import (
    ALL_STATUSES,
    ATTEST_EXAMPLE,
    build_subjective_items,
    scope_matches,
)
from desloppify.engine._work_queue.ranking import (
    build_finding_items,
    choose_fallback_tier,
    group_queue_items,
    item_explain,
    item_sort_key,
    tier_counts,
)
from desloppify.state import StateModel


@dataclass(frozen=True)
class QueueBuildOptions:
    """Configuration for queue construction and tier selection behavior."""

    tier: int | None = None
    count: int | None = 1
    scan_path: str | None = None
    scope: str | None = None
    status: str = "open"
    include_subjective: bool = True
    subjective_threshold: float = 100.0
    chronic: bool = False
    no_tier_fallback: bool = False
    explain: bool = False
    plan: dict | None = None
    include_deferred: bool = False
    cluster: str | None = None


class WorkQueueResult(TypedDict):
    """Typed shape of the dict returned by :func:`build_work_queue`."""

    items: list[dict]
    total: int
    tier_counts: dict[int, int]
    requested_tier: int | None
    selected_tier: int | None
    fallback_reason: str | None
    available_tiers: list[int]
    grouped: dict[str, list[dict]]


def _apply_plan_order(
    items: list[dict],
    plan: dict,
    *,
    include_deferred: bool = False,
    cluster: str | None = None,
) -> list[dict]:
    """Reorder items according to the living plan.

    1. Items in ``queue_order`` appear first, in that order.
    2. Remaining items keep their mechanical sort.
    3. Skipped items are appended last (or excluded).
    4. Each item is annotated with plan metadata.
    """
    queue_order: list[str] = plan.get("queue_order", [])
    skipped_map: dict = plan.get("skipped", {})
    skipped_ids: set[str] = set(skipped_map.keys()) | set(plan.get("deferred", []))
    overrides: dict = plan.get("overrides", {})
    clusters: dict = plan.get("clusters", {})
    active_cluster = plan.get("active_cluster")

    # Build lookup
    by_id: dict[str, dict] = {}
    for item in items:
        by_id[item["id"]] = item

    # Annotate items with plan metadata
    for item_id, item in by_id.items():
        override = overrides.get(item_id, {})
        if override.get("description"):
            item["plan_description"] = override["description"]
        if override.get("note"):
            item["plan_note"] = override["note"]
        if override.get("cluster"):
            cluster_name = override["cluster"]
            cluster_data = clusters.get(cluster_name, {})
            item["plan_cluster"] = {
                "name": cluster_name,
                "description": cluster_data.get("description"),
                "total_items": len(cluster_data.get("finding_ids", [])),
                "sibling_ids": cluster_data.get("finding_ids", []),
            }

    # Split into ordered, remaining, skipped
    ordered: list[dict] = []
    ordered_ids: set[str] = set()
    for fid in queue_order:
        if fid in by_id and fid not in skipped_ids:
            ordered.append(by_id[fid])
            ordered_ids.add(fid)

    skipped_items: list[dict] = []
    remaining: list[dict] = []
    for item in items:
        item_id = item["id"]
        if item_id in ordered_ids:
            continue
        if item_id in skipped_ids:
            skipped_items.append(item)
        else:
            remaining.append(item)

    # Assign queue positions
    result = ordered + remaining
    if include_deferred:
        result = result + skipped_items

    for pos, item in enumerate(result):
        item["queue_position"] = pos + 1
        if item["id"] in skipped_ids:
            item["plan_skipped"] = True
            skip_entry = skipped_map.get(item["id"])
            if skip_entry:
                item["plan_skip_kind"] = skip_entry.get("kind", "temporary")
                skip_reason = skip_entry.get("reason")
                if skip_reason:
                    item["plan_skip_reason"] = skip_reason
            # Backwards compat
            item["plan_deferred"] = True

    # Filter to cluster if requested
    effective_cluster = cluster or active_cluster
    if effective_cluster:
        cluster_data = clusters.get(effective_cluster, {})
        cluster_member_ids = set(cluster_data.get("finding_ids", []))
        if cluster_member_ids:
            result = [item for item in result if item["id"] in cluster_member_ids]

    return result


def build_work_queue(
    state: StateModel,
    *,
    options: QueueBuildOptions | None = None,
) -> WorkQueueResult:
    """Build ranked queue items + tier metadata."""
    resolved_options = options or QueueBuildOptions()

    status = resolved_options.status
    if status not in ALL_STATUSES:
        raise ValueError(f"Unsupported status filter: {status}")
    try:
        subjective_threshold_value = float(resolved_options.subjective_threshold)
    except (TypeError, ValueError):
        subjective_threshold_value = 100.0
    subjective_threshold_value = max(0.0, min(100.0, subjective_threshold_value))

    finding_items = build_finding_items(
        state,
        scan_path=resolved_options.scan_path,
        status_filter=status,
        scope=resolved_options.scope,
        chronic=resolved_options.chronic,
    )

    all_items = list(finding_items)
    if (
        resolved_options.include_subjective
        and status in {"open", "all"}
        and not resolved_options.chronic
    ):
        subjective_items = build_subjective_items(
            state,
            state.get("findings", {}),
            threshold=subjective_threshold_value,
        )
        for item in subjective_items:
            if scope_matches(item, resolved_options.scope):
                all_items.append(item)

    all_items.sort(key=item_sort_key)

    # Apply living plan ordering if provided
    if resolved_options.plan:
        all_items = _apply_plan_order(
            all_items,
            resolved_options.plan,
            include_deferred=resolved_options.include_deferred,
            cluster=resolved_options.cluster,
        )

    counts = tier_counts(all_items)

    requested_tier = (
        int(resolved_options.tier) if resolved_options.tier is not None else None
    )
    selected_tier = requested_tier
    fallback_reason = None
    filtered = all_items

    if requested_tier is not None:
        filtered = [
            item
            for item in all_items
            if int(item.get("effective_tier", item.get("tier", 3))) == requested_tier
        ]
        if not filtered and not resolved_options.no_tier_fallback:
            chosen = choose_fallback_tier(requested_tier, counts)
            if chosen is not None:
                selected_tier = chosen
                filtered = [
                    item
                    for item in all_items
                    if int(item.get("effective_tier", item.get("tier", 3))) == chosen
                ]
                fallback_reason = (
                    f"Requested T{requested_tier} has 0 open -> showing T{chosen} "
                    "(nearest non-empty)."
                )
        elif not filtered:
            fallback_reason = f"Requested T{requested_tier} has 0 open."

    total = len(filtered)
    if resolved_options.count is not None and resolved_options.count > 0:
        filtered = filtered[: resolved_options.count]

    if resolved_options.explain:
        for item in filtered:
            item["explain"] = item_explain(item)

    available_tiers = [tier for tier, value in counts.items() if value > 0]
    return {
        "items": filtered,
        "total": total,
        "tier_counts": counts,
        "requested_tier": requested_tier,
        "selected_tier": selected_tier,
        "fallback_reason": fallback_reason,
        "available_tiers": available_tiers,
        "grouped": group_queue_items(filtered, "item"),
    }


__all__ = [
    "ATTEST_EXAMPLE",
    "QueueBuildOptions",
    "WorkQueueResult",
    "build_work_queue",
    "group_queue_items",
]
