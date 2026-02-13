"""Tests for desloppify.narrative — pure narrative computation functions."""

from __future__ import annotations

import pytest

from desloppify.narrative import (
    STRUCTURAL_MERGE,
    _analyze_debt,
    _compute_headline,
    _compute_reminders,
    _count_open_by_detector,
    _detect_milestone,
    _detect_phase,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _finding(
    detector: str,
    *,
    status: str = "open",
    confidence: str = "high",
    file: str = "a.py",
    zone: str = "production",
) -> dict:
    """Build a minimal finding dict."""
    return {
        "detector": detector,
        "status": status,
        "confidence": confidence,
        "file": file,
        "zone": zone,
    }


def _findings_dict(*findings: dict) -> dict:
    """Wrap a list of finding dicts into an id-keyed dict."""
    return {str(i): f for i, f in enumerate(findings)}


def _history_entry(
    objective_strict: float | None = None,
    objective_score: float | None = None,
    lang: str | None = None,
    dimension_scores: dict | None = None,
) -> dict:
    entry: dict = {}
    if objective_strict is not None:
        entry["objective_strict"] = objective_strict
    if objective_score is not None:
        entry["objective_score"] = objective_score
    if lang is not None:
        entry["lang"] = lang
    if dimension_scores is not None:
        entry["dimension_scores"] = dimension_scores
    return entry


# ===================================================================
# _count_open_by_detector
# ===================================================================

class TestCountOpenByDetector:
    def test_empty_findings(self):
        assert _count_open_by_detector({}) == {}

    def test_only_open_counted(self):
        findings = _findings_dict(
            _finding("unused", status="open"),
            _finding("unused", status="resolved"),
            _finding("unused", status="wontfix"),
            _finding("unused", status="false_positive"),
        )
        result = _count_open_by_detector(findings)
        assert result == {"unused": 1}

    def test_multiple_detectors(self):
        findings = _findings_dict(
            _finding("unused", status="open"),
            _finding("unused", status="open"),
            _finding("logs", status="open"),
            _finding("smells", status="open"),
        )
        result = _count_open_by_detector(findings)
        assert result == {"unused": 2, "logs": 1, "smells": 1}

    def test_structural_merge_large(self):
        findings = _findings_dict(
            _finding("large", status="open"),
        )
        result = _count_open_by_detector(findings)
        assert result == {"structural": 1}

    def test_structural_merge_complexity(self):
        findings = _findings_dict(
            _finding("complexity", status="open"),
        )
        result = _count_open_by_detector(findings)
        assert result == {"structural": 1}

    def test_structural_merge_gods(self):
        findings = _findings_dict(
            _finding("gods", status="open"),
        )
        result = _count_open_by_detector(findings)
        assert result == {"structural": 1}

    def test_structural_merge_concerns(self):
        findings = _findings_dict(
            _finding("concerns", status="open"),
        )
        result = _count_open_by_detector(findings)
        assert result == {"structural": 1}

    def test_structural_merge_combines_all_subdetectors(self):
        """All four structural sub-detectors merge into a single count."""
        findings = _findings_dict(
            _finding("large", status="open"),
            _finding("complexity", status="open"),
            _finding("gods", status="open"),
            _finding("concerns", status="open"),
        )
        result = _count_open_by_detector(findings)
        assert result == {"structural": 4}

    def test_structural_merge_set_matches_constant(self):
        assert STRUCTURAL_MERGE == {"large", "complexity", "gods", "concerns"}

    def test_non_structural_not_merged(self):
        """Detectors not in STRUCTURAL_MERGE stay separate."""
        findings = _findings_dict(
            _finding("unused", status="open"),
            _finding("large", status="open"),
        )
        result = _count_open_by_detector(findings)
        assert result == {"unused": 1, "structural": 1}

    def test_missing_detector_key(self):
        findings = {"0": {"status": "open"}}
        result = _count_open_by_detector(findings)
        assert result == {"unknown": 1}


# ===================================================================
# _detect_phase
# ===================================================================

class TestDetectPhase:
    def test_empty_history(self):
        assert _detect_phase([], None) == "first_scan"

    def test_single_entry_history(self):
        history = [_history_entry(objective_strict=50.0)]
        assert _detect_phase(history, 50.0) == "first_scan"

    def test_regression_strict_dropped(self):
        """Strict dropped > 0.5 from previous scan."""
        history = [
            _history_entry(objective_strict=80.0),
            _history_entry(objective_strict=79.0),
        ]
        assert _detect_phase(history, 79.0) == "regression"

    def test_regression_exact_half_point_no_regression(self):
        """Dropping exactly 0.5 is NOT regression (must exceed 0.5)."""
        history = [
            _history_entry(objective_strict=80.0),
            _history_entry(objective_strict=79.5),
        ]
        assert _detect_phase(history, 79.5) != "regression"

    def test_stagnation_three_scans_unchanged(self):
        """Strict unchanged (spread <= 0.5) for 3+ scans."""
        history = [
            _history_entry(objective_strict=75.0),
            _history_entry(objective_strict=75.2),
            _history_entry(objective_strict=75.3),
        ]
        assert _detect_phase(history, 75.3) == "stagnation"

    def test_stagnation_requires_three_scans(self):
        """Only two scans with same score is not stagnation."""
        history = [
            _history_entry(objective_strict=75.0),
            _history_entry(objective_strict=75.0),
        ]
        # Two scans, same score but len(history) < 3 so no stagnation
        # This should trigger early_momentum check (len 2, and first==last)
        # Since first == last (not last > first), it won't be early_momentum
        # Falls through to score thresholds
        assert _detect_phase(history, 75.0) != "stagnation"

    def test_early_momentum_scans_2_to_5_rising(self):
        """Scans 2-5, score rising from first to last."""
        history = [
            _history_entry(objective_strict=60.0),
            _history_entry(objective_strict=70.0),
        ]
        assert _detect_phase(history, 70.0) == "early_momentum"

    def test_early_momentum_at_five_scans(self):
        history = [
            _history_entry(objective_strict=50.0),
            _history_entry(objective_strict=55.0),
            _history_entry(objective_strict=60.0),
            _history_entry(objective_strict=65.0),
            _history_entry(objective_strict=70.0),
        ]
        assert _detect_phase(history, 70.0) == "early_momentum"

    def test_early_momentum_not_at_six_scans(self):
        """More than 5 scans should not be early_momentum."""
        history = [
            _history_entry(objective_strict=50.0),
            _history_entry(objective_strict=55.0),
            _history_entry(objective_strict=60.0),
            _history_entry(objective_strict=65.0),
            _history_entry(objective_strict=70.0),
            _history_entry(objective_strict=75.0),
        ]
        # len=6, not in 2-5 range, falls through
        result = _detect_phase(history, 75.0)
        assert result != "early_momentum"

    def test_declining_trajectory_not_early_momentum(self):
        """Score declining from first scan should NOT return early_momentum."""
        history = [
            _history_entry(objective_strict=80.0),
            _history_entry(objective_strict=75.0),
        ]
        # last (75) < first (80), so not early_momentum
        # Also triggers regression (80 - 75 = 5 > 0.5)
        result = _detect_phase(history, 75.0)
        assert result != "early_momentum"
        assert result == "regression"

    def test_flat_trajectory_not_early_momentum(self):
        """Score equal from first scan should NOT return early_momentum."""
        history = [
            _history_entry(objective_strict=70.0),
            _history_entry(objective_strict=70.0),
        ]
        # last == first, not >
        result = _detect_phase(history, 70.0)
        assert result != "early_momentum"

    def test_maintenance_above_93(self):
        """Score > 93 triggers maintenance phase."""
        history = [
            _history_entry(objective_strict=85.0),
            _history_entry(objective_strict=88.0),
            _history_entry(objective_strict=90.0),
            _history_entry(objective_strict=92.0),
            _history_entry(objective_strict=93.5),
            _history_entry(objective_strict=94.0),
        ]
        assert _detect_phase(history, 94.0) == "maintenance"

    def test_refinement_above_80(self):
        """Score > 80 but <= 93 triggers refinement."""
        history = [
            _history_entry(objective_strict=70.0),
            _history_entry(objective_strict=75.0),
            _history_entry(objective_strict=78.0),
            _history_entry(objective_strict=81.0),
            _history_entry(objective_strict=82.0),
            _history_entry(objective_strict=85.0),
        ]
        assert _detect_phase(history, 85.0) == "refinement"

    def test_middle_grind_below_80(self):
        """Score <= 80 with > 5 scans, no regression/stagnation."""
        history = [
            _history_entry(objective_strict=40.0),
            _history_entry(objective_strict=45.0),
            _history_entry(objective_strict=50.0),
            _history_entry(objective_strict=55.0),
            _history_entry(objective_strict=60.0),
            _history_entry(objective_strict=65.0),
        ]
        assert _detect_phase(history, 65.0) == "middle_grind"

    def test_regression_takes_priority_over_stagnation(self):
        """Regression is checked before stagnation."""
        # Last 3 scans: 80, 80, 79 — stagnation spread 1.0 > 0.5 so not stagnant
        # But prev=80, curr=79 — drop is 1 > 0.5, so regression
        history = [
            _history_entry(objective_strict=80.0),
            _history_entry(objective_strict=80.0),
            _history_entry(objective_strict=79.0),
        ]
        assert _detect_phase(history, 79.0) == "regression"

    def test_stagnation_takes_priority_over_early_momentum(self):
        """Stagnation is checked before early_momentum for short histories."""
        history = [
            _history_entry(objective_strict=70.0),
            _history_entry(objective_strict=70.0),
            _history_entry(objective_strict=70.0),
        ]
        assert _detect_phase(history, 70.0) == "stagnation"

    def test_obj_strict_none_uses_last_history(self):
        """When obj_strict is None, fallback to history[-1].objective_strict."""
        history = [
            _history_entry(objective_strict=50.0),
            _history_entry(objective_strict=55.0),
            _history_entry(objective_strict=60.0),
            _history_entry(objective_strict=65.0),
            _history_entry(objective_strict=70.0),
            _history_entry(objective_strict=75.0),
        ]
        # obj_strict None -> uses history[-1] = 75.0 -> refinement (> 80 would be, but 75 is not)
        # 75 <= 80 -> middle_grind
        result = _detect_phase(history, None)
        assert result == "middle_grind"

    def test_regression_with_none_strict_values(self):
        """If prev or curr strict is None, regression check is skipped."""
        history = [
            _history_entry(),  # no objective_strict
            _history_entry(objective_strict=70.0),
        ]
        result = _detect_phase(history, 70.0)
        # No prev strict to compare, regression check skipped
        # len=2, first has no strict -> early_momentum check: first is None -> skip
        # strict=70 -> not > 93, not > 80 -> middle_grind
        assert result == "middle_grind"


# ===================================================================
# _detect_milestone
# ===================================================================

class TestDetectMilestone:
    def test_crossed_90_strict(self):
        state = {"objective_strict": 91.0, "stats": {"by_tier": {}}}
        history = [
            _history_entry(objective_strict=89.0),
            _history_entry(objective_strict=91.0),
        ]
        result = _detect_milestone(state, None, history)
        assert result == "Crossed 90% strict!"

    def test_crossed_80_strict(self):
        state = {"objective_strict": 82.0, "stats": {"by_tier": {}}}
        history = [
            _history_entry(objective_strict=78.0),
            _history_entry(objective_strict=82.0),
        ]
        result = _detect_milestone(state, None, history)
        assert result == "Crossed 80% strict!"

    def test_crossed_90_takes_priority_over_80(self):
        """If somehow both thresholds are crossed simultaneously, 90 wins."""
        state = {"objective_strict": 91.0, "stats": {"by_tier": {}}}
        history = [
            _history_entry(objective_strict=79.0),
            _history_entry(objective_strict=91.0),
        ]
        result = _detect_milestone(state, None, history)
        assert result == "Crossed 90% strict!"

    def test_already_above_90_no_milestone(self):
        """If already above 90, no crossing milestone."""
        state = {"objective_strict": 95.0, "stats": {"by_tier": {}}}
        history = [
            _history_entry(objective_strict=92.0),
            _history_entry(objective_strict=95.0),
        ]
        result = _detect_milestone(state, None, history)
        assert result is None

    def test_all_t1_t2_cleared(self):
        state = {
            "objective_strict": 70.0,
            "stats": {
                "by_tier": {
                    "1": {"open": 0, "resolved": 5},
                    "2": {"open": 0, "resolved": 3},
                },
            },
        }
        history = [_history_entry(objective_strict=70.0)]
        result = _detect_milestone(state, None, history)
        assert result == "All T1 and T2 items cleared!"

    def test_all_t1_cleared_with_t2_remaining(self):
        state = {
            "objective_strict": 70.0,
            "stats": {
                "by_tier": {
                    "1": {"open": 0, "resolved": 5},
                    "2": {"open": 2, "resolved": 1},
                },
            },
        }
        history = [_history_entry(objective_strict=70.0)]
        result = _detect_milestone(state, None, history)
        assert result == "All T1 items cleared!"

    def test_t1_still_open_no_milestone(self):
        state = {
            "objective_strict": 70.0,
            "stats": {
                "by_tier": {
                    "1": {"open": 3, "resolved": 2},
                    "2": {"open": 1, "resolved": 0},
                },
            },
        }
        history = [_history_entry(objective_strict=70.0)]
        result = _detect_milestone(state, None, history)
        assert result is None

    def test_zero_open_findings(self):
        state = {
            "objective_strict": 100.0,
            "stats": {
                "open": 0,
                "total": 10,
                "by_tier": {},
            },
        }
        history = [_history_entry(objective_strict=100.0)]
        result = _detect_milestone(state, None, history)
        assert result == "Zero open findings!"

    def test_zero_total_findings_no_milestone(self):
        """Zero open AND zero total means nothing was ever found -- no celebration."""
        state = {
            "objective_strict": 100.0,
            "stats": {
                "open": 0,
                "total": 0,
                "by_tier": {},
            },
        }
        history = [_history_entry(objective_strict=100.0)]
        result = _detect_milestone(state, None, history)
        assert result is None

    def test_no_milestone_ordinary_case(self):
        state = {
            "objective_strict": 70.0,
            "stats": {
                "open": 15,
                "total": 50,
                "by_tier": {
                    "1": {"open": 2},
                    "2": {"open": 3},
                },
            },
        }
        history = [_history_entry(objective_strict=70.0)]
        result = _detect_milestone(state, None, history)
        assert result is None

    def test_threshold_milestones_require_two_history_entries(self):
        """Single history entry cannot trigger 90/80 crossing."""
        state = {"objective_strict": 95.0, "stats": {"by_tier": {}}}
        history = [_history_entry(objective_strict=95.0)]
        result = _detect_milestone(state, None, history)
        assert result is None

    def test_t1_t2_cleared_requires_prior_items(self):
        """If there were never T1/T2 items, no clearing milestone."""
        state = {
            "objective_strict": 70.0,
            "stats": {
                "by_tier": {
                    "1": {"open": 0},  # totals sum to 0
                    "2": {"open": 0},
                },
            },
        }
        history = [_history_entry(objective_strict=70.0)]
        result = _detect_milestone(state, None, history)
        assert result is None


# ===================================================================
# _analyze_debt
# ===================================================================

class TestAnalyzeDebt:
    def test_empty_inputs(self):
        result = _analyze_debt({}, {}, [])
        assert result["overall_gap"] == 0.0
        assert result["wontfix_count"] == 0
        assert result["worst_dimension"] is None
        assert result["worst_gap"] == 0.0
        assert result["trend"] == "stable"

    def test_wontfix_count(self):
        findings = _findings_dict(
            _finding("unused", status="wontfix"),
            _finding("unused", status="wontfix"),
            _finding("logs", status="open"),
            _finding("smells", status="resolved"),
        )
        result = _analyze_debt({}, findings, [])
        assert result["wontfix_count"] == 2

    def test_worst_dimension_gap(self):
        dim_scores = {
            "Import hygiene": {"score": 90.0, "strict": 85.0, "tier": 1},
            "Debug cleanliness": {"score": 95.0, "strict": 80.0, "tier": 2},
        }
        result = _analyze_debt(dim_scores, {}, [])
        assert result["worst_dimension"] == "Debug cleanliness"
        assert result["worst_gap"] == 15.0

    def test_overall_gap_weighted(self):
        """Overall gap is tier-weighted average of (lenient - strict)."""
        dim_scores = {
            "Import hygiene": {"score": 90.0, "strict": 80.0, "tier": 1},
        }
        result = _analyze_debt(dim_scores, {}, [])
        # lenient=90, strict=80, gap=10
        assert result["overall_gap"] == 10.0

    def test_trend_growing(self):
        """Gap increased over history -> growing."""
        history = [
            _history_entry(objective_strict=80.0, objective_score=82.0),
            _history_entry(objective_strict=78.0, objective_score=84.0),
            _history_entry(objective_strict=75.0, objective_score=85.0),
        ]
        # gaps: 2.0, 6.0, 10.0 -- last (10) > first (2) + 0.5 -> growing
        result = _analyze_debt({}, {}, history)
        assert result["trend"] == "growing"

    def test_trend_shrinking(self):
        """Gap decreased over history -> shrinking."""
        history = [
            _history_entry(objective_strict=70.0, objective_score=80.0),
            _history_entry(objective_strict=75.0, objective_score=80.0),
            _history_entry(objective_strict=79.0, objective_score=80.0),
        ]
        # gaps: 10.0, 5.0, 1.0 -- last (1) < first (10) - 0.5 -> shrinking
        result = _analyze_debt({}, {}, history)
        assert result["trend"] == "shrinking"

    def test_trend_stable(self):
        """Gap unchanged -> stable."""
        history = [
            _history_entry(objective_strict=75.0, objective_score=80.0),
            _history_entry(objective_strict=75.0, objective_score=80.0),
            _history_entry(objective_strict=75.0, objective_score=80.0),
        ]
        # gaps: 5.0, 5.0, 5.0 -- last == first -> stable
        result = _analyze_debt({}, {}, history)
        assert result["trend"] == "stable"

    def test_trend_requires_three_scans(self):
        """Fewer than 3 scans -> stable (no trend)."""
        history = [
            _history_entry(objective_strict=70.0, objective_score=80.0),
            _history_entry(objective_strict=60.0, objective_score=85.0),
        ]
        result = _analyze_debt({}, {}, history)
        assert result["trend"] == "stable"

    def test_no_gap_when_strict_equals_lenient(self):
        dim_scores = {
            "Import hygiene": {"score": 90.0, "strict": 90.0, "tier": 1},
        }
        result = _analyze_debt(dim_scores, {}, [])
        assert result["overall_gap"] == 0.0
        assert result["worst_dimension"] is None
        assert result["worst_gap"] == 0.0


# ===================================================================
# _compute_reminders
# ===================================================================

class TestComputeReminders:
    def test_returns_tuple(self):
        """Must return (list, dict) tuple."""
        state = {"objective_strict": 50.0}
        result = _compute_reminders(
            state, "typescript", "middle_grind", {}, [], {}, {}, None,
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], list)
        assert isinstance(result[1], dict)

    def test_decay_suppresses_after_three(self):
        """Reminders shown >= 3 times are suppressed."""
        state = {
            "objective_strict": 50.0,
            "reminder_history": {"rescan_needed": 3},
        }
        reminders, history = _compute_reminders(
            state, "typescript", "middle_grind", {},
            [], {}, {}, "fix",
        )
        # "rescan_needed" would fire for command="fix" but history count=3 -> suppressed
        reminder_types = [r["type"] for r in reminders]
        assert "rescan_needed" not in reminder_types

    def test_decay_allows_below_threshold(self):
        """Reminders shown < 3 times are allowed through."""
        state = {
            "objective_strict": 50.0,
            "reminder_history": {"rescan_needed": 2},
        }
        reminders, history = _compute_reminders(
            state, "typescript", "middle_grind", {},
            [], {}, {}, "fix",
        )
        reminder_types = [r["type"] for r in reminders]
        assert "rescan_needed" in reminder_types

    def test_updated_history_increments_count(self):
        """Updated history increments count for shown reminders."""
        state = {
            "objective_strict": 50.0,
            "reminder_history": {"rescan_needed": 1},
        }
        reminders, updated = _compute_reminders(
            state, "typescript", "middle_grind", {},
            [], {}, {}, "fix",
        )
        assert updated["rescan_needed"] == 2

    def test_rescan_reminder_after_fix(self):
        state = {"objective_strict": 50.0}
        reminders, _ = _compute_reminders(
            state, "typescript", "middle_grind", {},
            [], {}, {}, "fix",
        )
        reminder_types = [r["type"] for r in reminders]
        assert "rescan_needed" in reminder_types

    def test_rescan_reminder_after_resolve(self):
        state = {"objective_strict": 50.0}
        reminders, _ = _compute_reminders(
            state, "typescript", "middle_grind", {},
            [], {}, {}, "resolve",
        )
        reminder_types = [r["type"] for r in reminders]
        assert "rescan_needed" in reminder_types

    def test_no_rescan_reminder_after_scan(self):
        state = {"objective_strict": 50.0}
        reminders, _ = _compute_reminders(
            state, "typescript", "middle_grind", {},
            [], {}, {}, "scan",
        )
        reminder_types = [r["type"] for r in reminders]
        assert "rescan_needed" not in reminder_types

    def test_wontfix_growing_reminder(self):
        state = {"objective_strict": 50.0}
        debt = {"trend": "growing"}
        reminders, _ = _compute_reminders(
            state, "typescript", "middle_grind", debt,
            [], {}, {}, None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "wontfix_growing" in reminder_types

    def test_badge_recommendation_above_90(self):
        state = {"objective_strict": 92.0}
        badge = {"generated": True, "in_readme": False}
        reminders, _ = _compute_reminders(
            state, "typescript", "maintenance", {},
            [], {}, badge, None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "badge_recommendation" in reminder_types

    def test_no_badge_recommendation_below_90(self):
        state = {"objective_strict": 85.0}
        badge = {"generated": True, "in_readme": False}
        reminders, _ = _compute_reminders(
            state, "typescript", "refinement", {},
            [], {}, badge, None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "badge_recommendation" not in reminder_types

    def test_no_badge_recommendation_already_in_readme(self):
        state = {"objective_strict": 95.0}
        badge = {"generated": True, "in_readme": True}
        reminders, _ = _compute_reminders(
            state, "typescript", "maintenance", {},
            [], {}, badge, None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "badge_recommendation" not in reminder_types

    def test_auto_fixers_available_typescript(self):
        state = {"objective_strict": 50.0}
        actions = [{"type": "auto_fix", "count": 5, "command": "desloppify fix unused-imports --dry-run"}]
        reminders, _ = _compute_reminders(
            state, "typescript", "middle_grind", {},
            actions, {}, {}, None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "auto_fixers_available" in reminder_types

    def test_no_auto_fixers_for_python(self):
        """Python has no auto-fixers, so auto_fixers_available should not fire."""
        state = {"objective_strict": 50.0}
        actions = [{"type": "auto_fix", "count": 5, "command": "desloppify fix unused-imports --dry-run"}]
        reminders, _ = _compute_reminders(
            state, "python", "middle_grind", {},
            actions, {}, {}, None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "auto_fixers_available" not in reminder_types

    def test_stagnant_dimension_reminder(self):
        state = {"objective_strict": 70.0}
        dimensions = {
            "stagnant_dimensions": [
                {"name": "Import hygiene", "strict": 80.0, "stuck_scans": 4},
            ],
        }
        reminders, _ = _compute_reminders(
            state, "typescript", "stagnation", {},
            [], dimensions, {}, None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "stagnant_nudge" in reminder_types

    def test_dry_run_first_reminder(self):
        state = {"objective_strict": 50.0}
        actions = [{"type": "auto_fix", "count": 3, "command": "desloppify fix unused-imports --dry-run"}]
        reminders, _ = _compute_reminders(
            state, "typescript", "middle_grind", {},
            actions, {}, {}, None,
        )
        reminder_types = [r["type"] for r in reminders]
        assert "dry_run_first" in reminder_types

    def test_does_not_mutate_state(self):
        """The reminder_history on state must not be mutated."""
        original_history = {"rescan_needed": 1}
        state = {
            "objective_strict": 50.0,
            "reminder_history": original_history,
        }
        _, updated = _compute_reminders(
            state, "typescript", "middle_grind", {},
            [], {}, {}, "fix",
        )
        # Original should be unchanged
        assert original_history == {"rescan_needed": 1}
        # Updated should have incremented
        assert updated["rescan_needed"] == 2


# ===================================================================
# _compute_headline
# ===================================================================

class TestComputeHeadline:
    def test_milestone_takes_priority(self):
        """If a milestone is set, it becomes the headline."""
        result = _compute_headline(
            phase="maintenance",
            dimensions={"lowest_dimensions": [{"name": "Org", "issues": 3, "impact": 5.0, "strict": 80}]},
            debt={"overall_gap": 0},
            milestone="Crossed 90% strict!",
            diff=None,
            obj_strict=91.0,
            obj_score=91.0,
            stats={"open": 5},
            history=[],
        )
        assert result == "Crossed 90% strict!"

    def test_first_scan_with_dimensions(self):
        result = _compute_headline(
            phase="first_scan",
            dimensions={"lowest_dimensions": [
                {"name": "A", "issues": 1, "impact": 1.0, "strict": 90},
                {"name": "B", "issues": 2, "impact": 2.0, "strict": 80},
                {"name": "C", "issues": 3, "impact": 3.0, "strict": 70},
            ]},
            debt={"overall_gap": 0},
            milestone=None,
            diff=None,
            obj_strict=70.0,
            obj_score=70.0,
            stats={"open": 15},
            history=[],
        )
        assert result is not None
        assert "First scan complete" in result
        assert "15 open findings" in result
        assert "3 dimensions" in result

    def test_first_scan_no_dimensions(self):
        result = _compute_headline(
            phase="first_scan",
            dimensions={},
            debt={"overall_gap": 0},
            milestone=None,
            diff=None,
            obj_strict=70.0,
            obj_score=70.0,
            stats={"open": 8},
            history=[],
        )
        assert result is not None
        assert "First scan complete" in result
        assert "8 findings detected" in result

    def test_regression_message(self):
        history = [
            _history_entry(objective_strict=80.0),
            _history_entry(objective_strict=75.0),
        ]
        result = _compute_headline(
            phase="regression",
            dimensions={},
            debt={"overall_gap": 0},
            milestone=None,
            diff=None,
            obj_strict=75.0,
            obj_score=75.0,
            stats={"open": 10},
            history=history,
        )
        assert result is not None
        assert "5.0 pts" in result
        assert "normal after structural changes" in result

    def test_stagnation_with_lowest_dim(self):
        history = [
            _history_entry(objective_strict=70.0),
            _history_entry(objective_strict=70.0),
            _history_entry(objective_strict=70.0),
        ]
        dimensions = {
            "lowest_dimensions": [
                {"name": "Organization", "issues": 10, "impact": 5.0, "strict": 60.0},
            ],
        }
        result = _compute_headline(
            phase="stagnation",
            dimensions=dimensions,
            debt={"overall_gap": 0, "wontfix_count": 0},
            milestone=None,
            diff=None,
            obj_strict=70.0,
            obj_score=70.0,
            stats={"open": 10},
            history=history,
        )
        assert result is not None
        assert "plateaued" in result
        assert "Organization" in result
        assert "breakthrough" in result

    def test_stagnation_with_wontfix(self):
        history = [
            _history_entry(objective_strict=70.0),
            _history_entry(objective_strict=70.0),
            _history_entry(objective_strict=70.0),
        ]
        dimensions = {
            "lowest_dimensions": [
                {"name": "Organization", "issues": 10, "impact": 5.0, "strict": 60.0},
            ],
        }
        result = _compute_headline(
            phase="stagnation",
            dimensions=dimensions,
            debt={"overall_gap": 3.0, "wontfix_count": 5},
            milestone=None,
            diff=None,
            obj_strict=70.0,
            obj_score=73.0,
            stats={"open": 10},
            history=history,
        )
        assert result is not None
        assert "wontfix" in result
        assert "5" in result

    def test_leverage_point_headline(self):
        """Lowest dimension with impact > 0 generates a leverage headline."""
        dimensions = {
            "lowest_dimensions": [
                {"name": "Import hygiene", "issues": 20, "impact": 8.5, "strict": 70.0},
            ],
        }
        result = _compute_headline(
            phase="refinement",
            dimensions=dimensions,
            debt={"overall_gap": 0},
            milestone=None,
            diff=None,
            obj_strict=82.0,
            obj_score=82.0,
            stats={"open": 20},
            history=[_history_entry()] * 6,
        )
        assert result is not None
        assert "Import hygiene" in result
        assert "biggest lever" in result
        assert "+8.5 pts" in result

    def test_maintenance_headline(self):
        result = _compute_headline(
            phase="maintenance",
            dimensions={"lowest_dimensions": []},
            debt={"overall_gap": 0},
            milestone=None,
            diff=None,
            obj_strict=95.0,
            obj_score=95.0,
            stats={"open": 2},
            history=[_history_entry()] * 10,
        )
        assert result is not None
        assert "maintenance mode" in result
        assert "95.0" in result

    def test_middle_grind_with_lowest_dim(self):
        dimensions = {
            "lowest_dimensions": [
                {"name": "Debug cleanliness", "issues": 15, "impact": 0, "strict": 55.0},
            ],
        }
        result = _compute_headline(
            phase="middle_grind",
            dimensions=dimensions,
            debt={"overall_gap": 0},
            milestone=None,
            diff=None,
            obj_strict=60.0,
            obj_score=60.0,
            stats={"open": 30},
            history=[_history_entry()] * 6,
        )
        assert result is not None
        assert "30 findings open" in result
        assert "Debug cleanliness" in result
        assert "`desloppify next`" in result

    def test_early_momentum_headline(self):
        result = _compute_headline(
            phase="early_momentum",
            dimensions={"lowest_dimensions": []},
            debt={"overall_gap": 0},
            milestone=None,
            diff=None,
            obj_strict=72.0,
            obj_score=72.0,
            stats={"open": 10},
            history=[_history_entry()] * 3,
        )
        assert result is not None
        assert "72.0" in result
        assert "momentum" in result

    def test_returns_none_when_no_headline_matches(self):
        """Edge case: early_momentum with obj_strict None."""
        result = _compute_headline(
            phase="early_momentum",
            dimensions={"lowest_dimensions": []},
            debt={"overall_gap": 0},
            milestone=None,
            diff=None,
            obj_strict=None,
            obj_score=None,
            stats={"open": 0},
            history=[],
        )
        assert result is None

    def test_gap_callout_headline(self):
        """Debt gap > 5 generates gap callout headline."""
        result = _compute_headline(
            phase="refinement",
            dimensions={"lowest_dimensions": []},
            debt={"overall_gap": 8.0, "worst_dimension": "Organization"},
            milestone=None,
            diff=None,
            obj_strict=82.0,
            obj_score=90.0,
            stats={"open": 10},
            history=[_history_entry()] * 6,
        )
        assert result is not None
        assert "wontfix debt" in result
        assert "Organization" in result
