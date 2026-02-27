"""Sync stale subjective dimensions into the plan queue.

Handles both directions:
  1. **Cleanup** — remove ``subjective::*`` IDs whose dimension is no longer stale.
  2. **Inject**  — when the queue is empty after cleanup, add stale dimensions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from desloppify.engine._plan.schema import PlanModel, ensure_plan_defaults
from desloppify.engine._state.schema import StateModel

SUBJECTIVE_PREFIX = "subjective::"


@dataclass
class StaleDimensionSyncResult:
    """What changed during a stale-dimension sync."""

    injected: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)

    @property
    def changes(self) -> int:
        return len(self.injected) + len(self.pruned)


def _current_stale_ids(state: StateModel) -> set[str]:
    """Return the set of ``subjective::<slug>`` IDs that are currently stale."""
    from desloppify.engine._work_queue.helpers import slugify
    from desloppify.engine.planning.scorecard_projection import (
        scorecard_subjective_entries,
    )

    dim_scores = state.get("dimension_scores", {}) or {}
    if not dim_scores:
        return set()

    stale: set[str] = set()
    for entry in scorecard_subjective_entries(state, dim_scores=dim_scores):
        if not entry.get("stale"):
            continue
        dim_key = entry.get("dimension_key", "")
        if dim_key:
            stale.add(f"{SUBJECTIVE_PREFIX}{slugify(dim_key)}")
    return stale


def sync_stale_dimensions(
    plan: PlanModel,
    state: StateModel,
) -> StaleDimensionSyncResult:
    """Keep the plan queue in sync with stale subjective dimensions.

    1. Remove any ``subjective::*`` IDs from ``queue_order`` that are no
       longer stale (the user refreshed them, or mechanical evidence changed).
    2. If the queue is empty after cleanup, inject all currently-stale
       dimension IDs so the plan surfaces them as actionable work.
    """
    ensure_plan_defaults(plan)
    result = StaleDimensionSyncResult()
    stale_ids = _current_stale_ids(state)
    order: list[str] = plan["queue_order"]

    # --- Cleanup: prune resolved subjective IDs --------------------------
    to_remove: list[str] = [
        fid for fid in order
        if fid.startswith(SUBJECTIVE_PREFIX) and fid not in stale_ids
    ]
    for fid in to_remove:
        order.remove(fid)
        result.pruned.append(fid)

    # --- Inject: populate when queue is empty ----------------------------
    if not order and stale_ids:
        existing = set(order)
        for sid in sorted(stale_ids):
            if sid not in existing:
                order.append(sid)
                result.injected.append(sid)

    return result


__all__ = [
    "StaleDimensionSyncResult",
    "sync_stale_dimensions",
]
