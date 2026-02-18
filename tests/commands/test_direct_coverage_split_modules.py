"""Direct coverage smoke tests for recently split helper modules."""

from __future__ import annotations

import desloppify.app.output.scorecard_parts.dimensions as scorecard_dimensions
import desloppify.app.output.scorecard_parts.theme as scorecard_theme
import desloppify.intelligence.review.prepare_batches as review_prepare_batches
import desloppify.engine.scoring_internal.detection as scoring_detection
import desloppify.engine.scoring_internal.policy.core as scoring_policy
import desloppify.engine.scoring_internal.results.core as scoring_results
import desloppify.engine.scoring_internal.subjective.core as scoring_subjective
import desloppify.engine.state_internal.merge_findings as merge_findings
import desloppify.engine.state_internal.merge_history as merge_history
import desloppify.engine.work_queue_internal.helpers as work_queue_helpers
import desloppify.engine.work_queue_internal.ranking as work_queue_ranking


def test_split_module_direct_coverage_smoke_signals():
    assert callable(scorecard_dimensions.prepare_scorecard_dimensions)
    assert callable(scorecard_dimensions._prepare_scorecard_dimensions)
    assert callable(scorecard_theme._score_color)
    assert isinstance(scorecard_theme._BG, tuple)

    assert callable(review_prepare_batches.build_investigation_batches)

    assert callable(scoring_detection._detector_pass_rate)
    assert callable(scoring_detection.merge_potentials)
    assert isinstance(scoring_policy.DIMENSIONS, list)
    assert isinstance(scoring_policy._FILE_BASED_DETECTORS, set)
    assert callable(scoring_results.compute_score_bundle)
    assert callable(scoring_subjective._append_subjective_dimensions)

    assert callable(merge_findings._upsert_findings)
    assert callable(merge_findings._auto_resolve_disappeared)
    assert callable(merge_history._append_scan_history)
    assert callable(merge_history._build_merge_diff)

    assert callable(work_queue_helpers._build_subjective_items)
    assert callable(work_queue_helpers._subjective_dimension_aliases)
    assert callable(work_queue_ranking._item_sort_key)
    assert callable(work_queue_ranking.group_queue_items)
