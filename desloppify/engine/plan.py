"""Public plan API facade.

Plan internals live in ``desloppify.engine._plan``; this module exposes
the stable, non-private API used by commands and rendering helpers.
"""

from __future__ import annotations

# --- schema -----------------------------------------------------------------
from desloppify.engine._plan.schema import (
    PLAN_VERSION,
    Cluster,
    ItemOverride,
    PlanModel,
    SkipEntry,
    SupersededEntry,
    VALID_SKIP_KINDS,
    empty_plan,
    ensure_plan_defaults,
    validate_plan,
)

# --- persistence ------------------------------------------------------------
from desloppify.engine._plan.persistence import (
    PLAN_FILE,
    has_living_plan,
    load_plan,
    plan_path_for_state,
    save_plan,
)

# --- operations -------------------------------------------------------------
from desloppify.engine._plan.operations import (
    add_to_cluster,
    annotate_finding,
    clear_focus,
    create_cluster,
    defer_items,
    delete_cluster,
    describe_finding,
    move_cluster,
    move_items,
    purge_ids,
    remove_from_cluster,
    reset_plan,
    resurface_stale_skips,
    set_focus,
    skip_items,
    undefer_items,
    unskip_items,
)

# --- reconcile --------------------------------------------------------------
from desloppify.engine._plan.reconcile import (
    ReconcileResult,
    reconcile_plan_after_scan,
)

# --- stale dimensions -------------------------------------------------------
from desloppify.engine._plan.stale_dimensions import (
    StaleDimensionSyncResult,
    sync_stale_dimensions,
)

__all__ = [
    # schema
    "PLAN_VERSION",
    "Cluster",
    "ItemOverride",
    "PlanModel",
    "SkipEntry",
    "SupersededEntry",
    "VALID_SKIP_KINDS",
    "empty_plan",
    "ensure_plan_defaults",
    "validate_plan",
    # persistence
    "PLAN_FILE",
    "has_living_plan",
    "load_plan",
    "plan_path_for_state",
    "save_plan",
    # operations
    "add_to_cluster",
    "annotate_finding",
    "clear_focus",
    "create_cluster",
    "defer_items",
    "delete_cluster",
    "describe_finding",
    "move_cluster",
    "move_items",
    "purge_ids",
    "remove_from_cluster",
    "reset_plan",
    "resurface_stale_skips",
    "set_focus",
    "skip_items",
    "undefer_items",
    "unskip_items",
    # reconcile
    "ReconcileResult",
    "reconcile_plan_after_scan",
    # stale dimensions
    "StaleDimensionSyncResult",
    "sync_stale_dimensions",
]
