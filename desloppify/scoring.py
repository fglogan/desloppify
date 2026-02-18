"""Objective dimension-based scoring system facade."""

from __future__ import annotations

from desloppify.engine.scoring_internal.detection import detector_pass_rate as _detector_pass_rate
from desloppify.engine.scoring_internal.detection import merge_potentials
from desloppify.engine.scoring_internal.policy.core import FILE_BASED_DETECTORS, SECURITY_EXCLUDED_ZONES, CONFIDENCE_WEIGHTS, DIMENSIONS, HOLISTIC_MULTIPLIER, HOLISTIC_POTENTIAL, MECHANICAL_DIMENSION_WEIGHTS, MECHANICAL_WEIGHT_FRACTION, MIN_SAMPLE, SUBJECTIVE_CHECKS, SUBJECTIVE_DIMENSION_WEIGHTS, SUBJECTIVE_WEIGHT_FRACTION, TIER_WEIGHTS, DetectorScoringPolicy, Dimension, ScoreMode
from desloppify.engine.scoring_internal.results.core import ScoreBundle, compute_dimension_scores_by_mode, compute_dimension_scores, compute_health_breakdown, compute_health_score, compute_score_bundle, compute_score_impact, get_dimension_for_detector
from desloppify.engine.scoring_internal.subjective.core import DISPLAY_NAMES

_FILE_BASED_DETECTORS = FILE_BASED_DETECTORS
_SECURITY_EXCLUDED_ZONES = SECURITY_EXCLUDED_ZONES
_compute_dimension_scores_by_mode = compute_dimension_scores_by_mode

__all__ = [
    "CONFIDENCE_WEIGHTS",
    "DIMENSIONS",
    "DISPLAY_NAMES",
    "HOLISTIC_MULTIPLIER",
    "HOLISTIC_POTENTIAL",
    "MECHANICAL_DIMENSION_WEIGHTS",
    "MECHANICAL_WEIGHT_FRACTION",
    "MIN_SAMPLE",
    "SUBJECTIVE_CHECKS",
    "SUBJECTIVE_DIMENSION_WEIGHTS",
    "SUBJECTIVE_WEIGHT_FRACTION",
    "TIER_WEIGHTS",
    "DetectorScoringPolicy",
    "Dimension",
    "ScoreBundle",
    "ScoreMode",
    "_FILE_BASED_DETECTORS",
    "_SECURITY_EXCLUDED_ZONES",
    "_compute_dimension_scores_by_mode",
    "_detector_pass_rate",
    "compute_dimension_scores",
    "compute_health_breakdown",
    "compute_health_score",
    "compute_score_bundle",
    "compute_score_impact",
    "get_dimension_for_detector",
    "merge_potentials",
]
