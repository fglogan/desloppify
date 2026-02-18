"""Holistic review finding import workflow."""

from __future__ import annotations

import hashlib
from typing import Any

from desloppify.scoring import HOLISTIC_POTENTIAL
from desloppify.state import make_finding, merge_scan, utc_now
from desloppify.utils import PROJECT_ROOT
from desloppify.intelligence.review.dimensions.data import load_holistic_dimensions_for_lang
from desloppify.intelligence.review.importing.shared import extract_reviewed_files, store_assessments
from desloppify.intelligence.review.selection import hash_file


def _extract_findings_and_assessments(
    data: list[dict] | dict,
) -> tuple[list[dict], dict | None, list[str]]:
    """Parse import payload in legacy/list or current/object format."""
    if isinstance(data, list):
        return data, None, []
    if isinstance(data, dict):
        findings = data.get("findings", [])
        assessments = data.get("assessments") or None
        reviewed_files = extract_reviewed_files(data)
        return (
            findings if isinstance(findings, list) else [],
            assessments,
            reviewed_files,
        )
    return [], None, []


def update_reviewed_file_cache(
    state: dict[str, Any],
    reviewed_files: list[str],
    *,
    project_root=PROJECT_ROOT,
    utc_now_fn=utc_now,
) -> None:
    """Refresh per-file review cache entries from holistic payload metadata."""
    if not reviewed_files:
        return
    review_cache = state.setdefault("review_cache", {})
    file_cache = review_cache.setdefault("files", {})
    now = utc_now_fn()
    for file_path in reviewed_files:
        absolute = project_root / file_path
        content_hash = hash_file(str(absolute)) if absolute.exists() else ""
        previous = file_cache.get(file_path, {})
        existing_count = (
            previous.get("finding_count", 0) if isinstance(previous, dict) else 0
        )
        file_cache[file_path] = {
            "content_hash": content_hash,
            "reviewed_at": now,
            "finding_count": existing_count if isinstance(existing_count, int) else 0,
        }


def import_holistic_findings(
    findings_data: list[dict] | dict,
    state: dict[str, Any],
    lang_name: str,
    *,
    project_root=PROJECT_ROOT,
    utc_now_fn=utc_now,
) -> dict[str, Any]:
    """Import holistic (codebase-wide) findings into state."""
    findings_list, assessments, reviewed_files = _extract_findings_and_assessments(
        findings_data
    )
    if assessments:
        store_assessments(
            state,
            assessments,
            source="holistic",
            utc_now_fn=utc_now_fn,
        )

    _, holistic_prompts, _ = load_holistic_dimensions_for_lang(lang_name)
    required = ("dimension", "identifier", "summary", "confidence")

    review_findings: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for idx, finding in enumerate(findings_list):
        missing = [key for key in required if key not in finding]
        if missing:
            skipped.append(
                {
                    "index": idx,
                    "missing": missing,
                    "identifier": finding.get("identifier", "<none>"),
                }
            )
            continue

        confidence = finding.get("confidence", "low")
        if confidence not in ("high", "medium", "low"):
            confidence = "low"

        dimension = finding["dimension"]
        if dimension not in holistic_prompts:
            skipped.append(
                {
                    "index": idx,
                    "missing": [f"invalid dimension: {dimension}"],
                    "identifier": finding.get("identifier", "<none>"),
                }
            )
            continue

        content_hash = hashlib.sha256(finding["summary"].encode()).hexdigest()[:8]
        imported = make_finding(
            detector="review",
            file="",
            name=f"holistic::{dimension}::{finding['identifier']}::{content_hash}",
            tier=3,
            confidence=confidence,
            summary=finding["summary"],
            detail={
                "holistic": True,
                "dimension": dimension,
                "related_files": finding.get("related_files", []),
                "evidence": finding.get("evidence", []),
                "suggestion": finding.get("suggestion", ""),
                "reasoning": finding.get("reasoning", ""),
            },
        )
        imported["lang"] = lang_name
        review_findings.append(imported)

    potentials = state.setdefault("potentials", {}).setdefault(lang_name, {})
    existing_review = potentials.get("review", 0)
    potentials["review"] = max(existing_review, HOLISTIC_POTENTIAL)

    diff = merge_scan(
        state,
        review_findings,
        lang=lang_name,
        potentials={"review": potentials.get("review", 0)},
        merge_potentials=True,
    )

    new_ids = {finding["id"] for finding in review_findings}
    for finding_id, finding in state.get("findings", {}).items():
        if (
            finding["status"] == "open"
            and finding.get("detector") == "review"
            and finding.get("detail", {}).get("holistic")
            and finding_id not in new_ids
        ):
            finding["status"] = "auto_resolved"
            finding["resolved_at"] = utc_now_fn()
            finding["note"] = "not reported in latest holistic re-import"
            diff["auto_resolved"] = diff.get("auto_resolved", 0) + 1

    if skipped:
        diff["skipped"] = len(skipped)
        diff["skipped_details"] = skipped

    update_reviewed_file_cache(
        state,
        reviewed_files,
        project_root=project_root,
        utc_now_fn=utc_now_fn,
    )
    update_holistic_review_cache(
        state,
        findings_list,
        lang_name=lang_name,
        utc_now_fn=utc_now_fn,
    )
    resolve_holistic_coverage_findings(state, diff, utc_now_fn=utc_now_fn)
    return diff


def update_holistic_review_cache(
    state: dict[str, Any],
    findings_data: list[dict],
    *,
    lang_name: str | None = None,
    utc_now_fn=utc_now,
) -> None:
    """Store holistic review metadata in review_cache."""
    review_cache = state.setdefault("review_cache", {})
    now = utc_now_fn()
    _, holistic_prompts, _ = load_holistic_dimensions_for_lang(lang_name or "")

    valid = [
        finding
        for finding in findings_data
        if all(
            key in finding
            for key in ("dimension", "identifier", "summary", "confidence")
        )
        and finding["dimension"] in holistic_prompts
    ]

    total_files = len(review_cache.get("files", {}))
    codebase_metrics = state.get("codebase_metrics", {})
    if isinstance(codebase_metrics, dict):
        lang_metrics = codebase_metrics.get(lang_name) if lang_name else None
        if isinstance(lang_metrics, dict):
            metric_total = lang_metrics.get("total_files")
            if isinstance(metric_total, int) and metric_total > 0:
                total_files = metric_total
        else:
            metric_total = codebase_metrics.get("total_files")
            if isinstance(metric_total, int) and metric_total > 0:
                total_files = metric_total

    review_cache["holistic"] = {
        "reviewed_at": now,
        "file_count_at_review": total_files,
        "finding_count": len(valid),
    }


def resolve_holistic_coverage_findings(
    state: dict[str, Any],
    diff: dict[str, Any],
    *,
    utc_now_fn=utc_now,
) -> None:
    """Resolve stale holistic coverage entries after successful holistic import."""
    now = utc_now_fn()
    for finding in state.get("findings", {}).values():
        if finding.get("status") != "open":
            continue
        if finding.get("detector") != "subjective_review":
            continue

        finding_id = finding.get("id", "")
        if (
            "::holistic_unreviewed" not in finding_id
            and "::holistic_stale" not in finding_id
        ):
            continue

        finding["status"] = "auto_resolved"
        finding["resolved_at"] = now
        finding["note"] = "resolved by holistic review import"
        finding["resolution_attestation"] = {
            "kind": "agent_import",
            "text": "Holistic review refreshed; coverage marker superseded",
            "attested_at": now,
            "scan_verified": False,
        }
        diff["auto_resolved"] = diff.get("auto_resolved", 0) + 1
