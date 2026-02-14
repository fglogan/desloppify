"""Objective dimension-based scoring system.

Groups detectors into dimensions (coherent aspects of code quality),
computes per-dimension pass rates from potentials, and produces a
tier-weighted overall health score.
"""

from __future__ import annotations

from dataclasses import dataclass

from .enums import Confidence, Tier
from .zones import EXCLUDED_ZONE_VALUES


@dataclass
class Dimension:
    name: str
    tier: int
    detectors: list[str]


DIMENSIONS = [
    Dimension("Import hygiene",      1, ["unused"]),
    Dimension("Debug cleanliness",   1, ["logs"]),
    Dimension("API surface",         2, ["exports", "deprecated"]),
    Dimension("File health",         3, ["structural"]),
    Dimension("Component design",    3, ["props"]),
    Dimension("Coupling",            3, ["single_use", "coupling"]),
    Dimension("Organization",        3, ["orphaned", "flat_dirs", "naming", "facade", "stale_exclude"]),
    Dimension("Code quality",        3, ["smells", "react", "dict_keys", "global_mutable_config"]),
    Dimension("Duplication",         3, ["dupes"]),
    Dimension("Pattern consistency", 3, ["patterns"]),
    Dimension("Dependency health",   4, ["cycles"]),
    Dimension("Test health",         4, ["test_coverage"]),
    Dimension("Security",            4, ["security"]),
    Dimension("Audit coverage",        4, ["subjective_review"]),
]

TIER_WEIGHTS = {Tier.AUTO_FIX: 1, Tier.QUICK_FIX: 2, Tier.JUDGMENT: 3, Tier.MAJOR_REFACTOR: 4}
CONFIDENCE_WEIGHTS = {Confidence.HIGH: 1.0, Confidence.MEDIUM: 0.7, Confidence.LOW: 0.3}

# Minimum checks for full dimension weight — below this, weight is dampened
# proportionally. Prevents small-sample dimensions from swinging the overall score.
MIN_SAMPLE = 200

# Detectors where potential = file count but findings are per-(file, sub-type).
# Per-file weighted failures are capped at 1.0 to match the file-based denominator.
_FILE_BASED_DETECTORS = {"smells", "dict_keys", "test_coverage", "security", "review", "subjective_review"}

# Zones excluded from scoring (imported from zones.py canonical source)
_EXCLUDED_ZONES = EXCLUDED_ZONE_VALUES

# Security findings are only excluded in generated/vendor zones (secrets in tests are real risks)
_SECURITY_EXCLUDED_ZONES = {"generated", "vendor"}

# Holistic review scoring: findings with file="." and detail.holistic=True
# bypass per-file caps and get a 10x weight multiplier.
HOLISTIC_MULTIPLIER = 10.0
HOLISTIC_POTENTIAL = 10

# Number of checks per assessed review dimension (controls sample dampening).
# Each assessment dimension gets this many checks, making:
#   sample_factor = ASSESSMENT_CHECKS / MIN_SAMPLE
#   effective_weight = tier_weight * sample_factor
# This keeps individual assessment dimensions lightweight, but assessing more
# dimensions increases total assessment weight proportionally.
ASSESSMENT_CHECKS = 10

# Statuses that count as failures
_LENIENT_FAILURES = {"open"}
_STRICT_FAILURES = {"open", "wontfix"}


def merge_potentials(potentials_by_lang: dict) -> dict[str, int]:
    """Sum potentials across languages per detector."""
    merged: dict[str, int] = {}
    for lang_potentials in potentials_by_lang.values():
        for detector, count in lang_potentials.items():
            merged[detector] = merged.get(detector, 0) + count
    return merged


def _detector_pass_rate(
    detector: str,
    findings: dict,
    potential: int,
    *,
    strict: bool = False,
) -> tuple[float, int, float]:
    """Pass rate for one detector.

    Returns (pass_rate, issue_count, weighted_failures).
    Zero potential -> (1.0, 0, 0.0).

    For file-based detectors (potential = file count, multiple findings per file),
    per-file weighted failures are capped at 1.0 to prevent unit mismatch.
    """
    if potential <= 0:
        return 1.0, 0, 0.0

    failure_set = _STRICT_FAILURES if strict else _LENIENT_FAILURES
    issue_count = 0
    excluded_zones = _SECURITY_EXCLUDED_ZONES if detector == "security" else _EXCLUDED_ZONES

    if detector in _FILE_BASED_DETECTORS:
        # Group by file, cap per-file weight at 1.0
        # For test_coverage: use loc_weight from finding detail instead of confidence
        # so large untested files impact the score more than small ones.
        # Holistic findings (file="." + detail.holistic=True) bypass per-file caps
        # and get HOLISTIC_MULTIPLIER weight.
        use_loc_weight = (detector == "test_coverage")
        by_file: dict[str, float] = {}
        file_cap: dict[str, float] = {}  # per-file cap for loc_weight mode
        holistic_sum = 0.0
        for f in findings.values():
            if f.get("detector") != detector:
                continue
            if f.get("zone", "production") in excluded_zones:
                continue
            if f["status"] in failure_set:
                # Holistic findings: no per-file cap, 10x multiplier
                if f.get("file") == "." and f.get("detail", {}).get("holistic"):
                    weight = CONFIDENCE_WEIGHTS.get(f.get("confidence", "medium"), 0.7)
                    holistic_sum += weight * HOLISTIC_MULTIPLIER
                    issue_count += 1
                    continue
                if use_loc_weight:
                    weight = f.get("detail", {}).get("loc_weight", 1.0)
                else:
                    weight = CONFIDENCE_WEIGHTS.get(f.get("confidence", "medium"), 0.7)
                file_key = f.get("file", "")
                by_file[file_key] = by_file.get(file_key, 0) + weight
                # Track the single-finding weight as the per-file cap
                # (all findings for the same file have the same loc_weight)
                if use_loc_weight and file_key not in file_cap:
                    file_cap[file_key] = weight
                issue_count += 1
        if use_loc_weight:
            # Cap per-file at the file's loc_weight contribution to potential.
            # A file can have multiple findings (e.g. tested by 3 files with issues)
            # but should never contribute more than its potential share.
            weighted_failures = sum(
                min(w, file_cap.get(fk, w)) for fk, w in by_file.items())
        else:
            weighted_failures = sum(min(1.0, w) for w in by_file.values())
        weighted_failures += holistic_sum
    else:
        weighted_failures = 0.0
        for f in findings.values():
            if f.get("detector") != detector:
                continue
            if f.get("zone", "production") in excluded_zones:
                continue
            if f["status"] in failure_set:
                weight = CONFIDENCE_WEIGHTS.get(f.get("confidence", "medium"), 0.7)
                weighted_failures += weight
                issue_count += 1

    pass_rate = max(0.0, (potential - weighted_failures) / potential)
    return pass_rate, issue_count, weighted_failures


def compute_dimension_scores(
    findings: dict,
    potentials: dict[str, int],
    *,
    strict: bool = False,
    review_assessments: dict | None = None,
) -> dict[str, dict]:
    """Compute per-dimension scores from findings and potentials.

    Returns {dimension_name: {"score": float, "checks": int, "issues": int, "detectors": dict}}.
    Dimensions with no active detectors (all potentials = 0 or missing) are excluded.

    If *review_assessments* is provided, each assessed dimension becomes a
    first-class scoring dimension (tier 4) with score driven by the assessment,
    not by findings.
    """
    results: dict[str, dict] = {}
    failure_set = _STRICT_FAILURES if strict else _LENIENT_FAILURES

    for dim in DIMENSIONS:
        total_checks = 0
        total_issues = 0
        total_weighted_failures = 0.0
        detector_detail = {}

        for det in dim.detectors:
            pot = potentials.get(det, 0)
            if pot <= 0:
                continue
            rate, issues, weighted = _detector_pass_rate(
                det, findings, pot, strict=strict)
            total_checks += pot
            total_issues += issues
            total_weighted_failures += weighted
            detector_detail[det] = {
                "potential": pot, "pass_rate": rate,
                "issues": issues, "weighted_failures": weighted,
            }

        if total_checks <= 0:
            continue

        # Potential-weighted pass rate: treats the dimension as one big pool
        dim_score = max(0.0, (total_checks - total_weighted_failures) / total_checks) * 100

        results[dim.name] = {
            "score": round(dim_score, 1),
            "tier": dim.tier,
            "checks": total_checks,
            "issues": total_issues,
            "detectors": detector_detail,
        }

    # Append assessment dimensions — each one a first-class scoring dimension.
    # Unassessed dimensions default to 0% (same as test coverage when no tests exist).
    from .review import DEFAULT_DIMENSIONS
    assessed = review_assessments or {}
    existing_lower = {k.lower() for k in results}

    for dim_name in DEFAULT_DIMENSIONS:
        display = dim_name.replace("_", " ").title()
        if display.lower() in existing_lower:
            display = f"{display} (review)"

        assessment = assessed.get(dim_name)

        # Count open review findings for this dimension
        issue_count = sum(
            1 for f in findings.values()
            if f.get("detector") == "review"
            and f["status"] in failure_set
            and f.get("detail", {}).get("dimension") == dim_name
        )

        # Skip unassessed dimensions with no open findings
        if assessment is None and issue_count == 0:
            continue

        score = max(0, min(100, assessment.get("score", 0))) if assessment else 0.0
        pass_rate = score / 100.0

        results[display] = {
            "score": round(float(score), 1),
            "tier": 4,
            "checks": ASSESSMENT_CHECKS,
            "issues": issue_count,
            "detectors": {"review_assessment": {
                "potential": ASSESSMENT_CHECKS,
                "pass_rate": round(pass_rate, 4),
                "issues": issue_count,
                "weighted_failures": round(ASSESSMENT_CHECKS * (1 - pass_rate), 4),
            }},
        }

    # Also include any extra assessed dimensions not in DEFAULT_DIMENSIONS
    for dim_name, assessment in assessed.items():
        if dim_name in DEFAULT_DIMENSIONS:
            continue
        display = dim_name.replace("_", " ").title()
        if display.lower() in existing_lower:
            display = f"{display} (review)"
        issue_count = sum(
            1 for f in findings.values()
            if f.get("detector") == "review"
            and f["status"] in failure_set
            and f.get("detail", {}).get("dimension") == dim_name
        )
        # Skip unassessed extras with no open findings (shouldn't happen but guard)
        if issue_count == 0 and not assessment:
            continue
        score = max(0, min(100, assessment.get("score", 0)))
        pass_rate = score / 100.0
        results[display] = {
            "score": round(float(score), 1),
            "tier": 4,
            "checks": ASSESSMENT_CHECKS,
            "issues": issue_count,
            "detectors": {"review_assessment": {
                "potential": ASSESSMENT_CHECKS,
                "pass_rate": round(pass_rate, 4),
                "issues": issue_count,
                "weighted_failures": round(ASSESSMENT_CHECKS * (1 - pass_rate), 4),
            }},
        }

    return results


def compute_objective_score(dimension_scores: dict) -> float:
    """Tier-weighted average of dimension scores, dampened by sample size.

    Dimensions with fewer than MIN_SAMPLE checks get proportionally reduced
    weight, preventing small-sample dimensions from swinging the overall score.
    """
    if not dimension_scores:
        return 100.0

    weighted_sum = 0.0
    weight_total = 0.0
    for name, data in dimension_scores.items():
        tier = data["tier"]
        w = TIER_WEIGHTS.get(tier, 2)
        # Dampen weight for small-sample dimensions
        sample_factor = min(1.0, data.get("checks", 0) / MIN_SAMPLE)
        effective_weight = w * sample_factor
        weighted_sum += data["score"] * effective_weight
        weight_total += effective_weight

    if weight_total == 0:
        return 100.0
    return round(weighted_sum / weight_total, 1)


def compute_score_impact(
    dimension_scores: dict,
    potentials: dict[str, int],
    detector: str,
    issues_to_fix: int,
) -> float:
    """Estimate score improvement from fixing N issues in a detector.

    Returns estimated point increase in the objective score.
    """
    # Find which dimension this detector belongs to.
    # Assessment-based dimensions (detector="review_assessment") have no entry
    # in DIMENSIONS — score changes only via re-review, so impact is 0.
    target_dim = None
    for dim in DIMENSIONS:
        if detector in dim.detectors:
            target_dim = dim
            break
    if target_dim is None or target_dim.name not in dimension_scores:
        return 0.0

    pot = potentials.get(detector, 0)
    if pot <= 0:
        return 0.0

    dim_data = dimension_scores[target_dim.name]
    old_score = compute_objective_score(dimension_scores)

    # Simulate fixing: reduce weighted failures by issues_to_fix * avg_weight
    det_data = dim_data["detectors"].get(detector)
    if not det_data:
        return 0.0

    old_weighted = det_data["weighted_failures"]
    # Assume fixes are high-confidence (weight=1.0) — conservative estimate
    new_weighted = max(0.0, old_weighted - issues_to_fix * 1.0)

    # Recompute dimension score with potential-weighted averaging
    total_pot = 0
    total_new_wf = 0.0
    for det in target_dim.detectors:
        d = dim_data["detectors"].get(det)
        if not d:
            continue
        total_pot += d["potential"]
        if det == detector:
            total_new_wf += new_weighted
        else:
            total_new_wf += d["weighted_failures"]
    if total_pot <= 0:
        return 0.0
    new_dim_score = max(0.0, (total_pot - total_new_wf) / total_pot) * 100

    # Recompute overall with the new dimension score
    simulated = {k: dict(v) for k, v in dimension_scores.items()}
    simulated[target_dim.name] = {**dim_data, "score": round(new_dim_score, 1)}
    new_score = compute_objective_score(simulated)

    return round(new_score - old_score, 1)


def get_dimension_for_detector(detector: str) -> Dimension | None:
    """Look up which dimension a detector belongs to."""
    for dim in DIMENSIONS:
        if detector in dim.detectors:
            return dim
    return None
