"""Tests for stale subjective dimension sync in the plan."""

from __future__ import annotations

from desloppify.engine._plan.reconcile import reconcile_plan_after_scan
from desloppify.engine._plan.schema import empty_plan
from desloppify.engine._plan.stale_dimensions import sync_stale_dimensions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan_with_queue(*ids: str) -> dict:
    plan = empty_plan()
    plan["queue_order"] = list(ids)
    return plan


def _state_with_stale_dimensions(*dim_keys: str, score: float = 50.0) -> dict:
    """Build a minimal state with stale subjective dimensions."""
    dim_scores: dict = {}
    assessments: dict = {}
    for dim_key in dim_keys:
        dim_scores[dim_key] = {
            "score": score,
            "strict": score,
            "checks": 1,
            "issues": 0,
            "detectors": {
                "subjective_assessment": {
                    "dimension_key": dim_key,
                    "placeholder": False,
                }
            },
        }
        assessments[dim_key] = {
            "score": score,
            "needs_review_refresh": True,
            "refresh_reason": "mechanical_findings_changed",
            "stale_since": "2025-01-01T00:00:00+00:00",
        }
    return {
        "findings": {},
        "scan_count": 5,
        "dimension_scores": dim_scores,
        "subjective_assessments": assessments,
    }


# ---------------------------------------------------------------------------
# Injection: empty queue + stale dimensions
# ---------------------------------------------------------------------------

def test_injects_when_queue_empty():
    plan = _plan_with_queue()
    state = _state_with_stale_dimensions("design_coherence", "error_consistency")

    result = sync_stale_dimensions(plan, state)
    assert len(result.injected) == 2
    assert "subjective::design_coherence" in plan["queue_order"]
    assert "subjective::error_consistency" in plan["queue_order"]
    assert result.changes == 2


def test_no_injection_when_queue_has_real_items():
    plan = _plan_with_queue("some_finding::file.py::abc123")
    state = _state_with_stale_dimensions("design_coherence")

    result = sync_stale_dimensions(plan, state)
    assert result.injected == []
    assert "subjective::design_coherence" not in plan["queue_order"]


def test_no_injection_when_no_stale_dimensions():
    plan = _plan_with_queue()
    state = _state_with_stale_dimensions("design_coherence")
    state["subjective_assessments"]["design_coherence"]["needs_review_refresh"] = False

    result = sync_stale_dimensions(plan, state)
    assert result.injected == []
    assert plan["queue_order"] == []


def test_no_injection_when_no_dimension_scores():
    plan = _plan_with_queue()
    state = {"findings": {}, "scan_count": 5}

    result = sync_stale_dimensions(plan, state)
    assert result.injected == []
    assert result.pruned == []


# ---------------------------------------------------------------------------
# Cleanup: prune resolved stale IDs
# ---------------------------------------------------------------------------

def test_prunes_resolved_dimension_ids():
    plan = _plan_with_queue(
        "subjective::design_coherence",
        "subjective::error_consistency",
    )
    # Only design_coherence is still stale; error_consistency was refreshed
    state = _state_with_stale_dimensions("design_coherence")

    result = sync_stale_dimensions(plan, state)
    assert result.pruned == ["subjective::error_consistency"]
    assert plan["queue_order"] == ["subjective::design_coherence"]


def test_prune_does_not_touch_real_finding_ids():
    plan = _plan_with_queue(
        "structural::file.py::abc123",
        "subjective::design_coherence",
    )
    # design_coherence is no longer stale
    state = {"findings": {}, "scan_count": 5, "dimension_scores": {}}

    result = sync_stale_dimensions(plan, state)
    assert "subjective::design_coherence" in result.pruned
    assert plan["queue_order"] == ["structural::file.py::abc123"]


# ---------------------------------------------------------------------------
# Full lifecycle: inject → refresh → prune → re-inject
# ---------------------------------------------------------------------------

def test_full_lifecycle():
    plan = _plan_with_queue()
    state = _state_with_stale_dimensions("design_coherence", "error_consistency")

    # 1. Empty queue, stale dims → inject both
    r1 = sync_stale_dimensions(plan, state)
    assert len(r1.injected) == 2
    assert plan["queue_order"] == [
        "subjective::design_coherence",
        "subjective::error_consistency",
    ]

    # 2. User refreshes design_coherence (no longer stale)
    state["subjective_assessments"]["design_coherence"]["needs_review_refresh"] = False

    r2 = sync_stale_dimensions(plan, state)
    assert r2.pruned == ["subjective::design_coherence"]
    # error_consistency still there — queue not empty, so no new injection
    assert plan["queue_order"] == ["subjective::error_consistency"]
    assert r2.injected == []

    # 3. User refreshes error_consistency too → queue empties, nothing stale
    state["subjective_assessments"]["error_consistency"]["needs_review_refresh"] = False

    r3 = sync_stale_dimensions(plan, state)
    assert r3.pruned == ["subjective::error_consistency"]
    assert plan["queue_order"] == []
    assert r3.injected == []

    # 4. New mechanical change makes design_coherence stale again
    state["subjective_assessments"]["design_coherence"]["needs_review_refresh"] = True

    r4 = sync_stale_dimensions(plan, state)
    assert r4.injected == ["subjective::design_coherence"]
    assert plan["queue_order"] == ["subjective::design_coherence"]


# ---------------------------------------------------------------------------
# Reconcile must not supersede synthetic IDs
# ---------------------------------------------------------------------------

def test_reconcile_ignores_synthetic_ids():
    """Reconciliation must not treat subjective::* IDs as dead findings."""
    plan = _plan_with_queue("subjective::design_coherence")
    state = _state_with_stale_dimensions("design_coherence")

    result = reconcile_plan_after_scan(plan, state)
    assert result.superseded == []
    assert "subjective::design_coherence" in plan["queue_order"]
    assert "subjective::design_coherence" not in plan.get("superseded", {})
