"""Compatibility wrappers for review finding import workflows."""

from __future__ import annotations

from desloppify.state import utc_now
from desloppify.utils import PROJECT_ROOT
from desloppify.intelligence.review.importing.holistic import import_holistic_findings as _import_holistic_impl
from desloppify.intelligence.review.importing.holistic import resolve_holistic_coverage_findings as _resolve_holistic_coverage_impl
from desloppify.intelligence.review.importing.holistic import update_holistic_review_cache as _update_holistic_cache_impl
from desloppify.intelligence.review.importing.per_file import _extract_findings_and_assessments as _extract_findings_and_assessments_impl
from desloppify.intelligence.review.importing.per_file import import_review_findings as _import_review_impl
from desloppify.intelligence.review.importing.per_file import update_review_cache as _update_review_cache_impl
from desloppify.intelligence.review.importing.shared import extract_reviewed_files as _extract_reviewed_files_impl
from desloppify.intelligence.review.importing.shared import store_assessments as _store_assessments_impl

def _store_assessments(state: dict, assessments: dict, source: str):
    return _store_assessments_impl(
        state,
        assessments,
        source,
        utc_now_fn=utc_now,
    )


def _extract_findings_and_assessments(
    data: list[dict] | dict,
) -> tuple[list[dict], dict | None]:
    return _extract_findings_and_assessments_impl(data)


def _extract_reviewed_files(data: list[dict] | dict) -> list[str]:
    return _extract_reviewed_files_impl(data)


def import_review_findings(
    findings_data: list[dict] | dict,
    state: dict[str, object],
    lang_name: str,
) -> dict[str, object]:
    return _import_review_impl(
        findings_data,
        state,
        lang_name,
        project_root=PROJECT_ROOT,
        utc_now_fn=utc_now,
    )


def _update_review_cache(
    state: dict, findings_data: list[dict], *, reviewed_files: list[str] | None = None
):
    return _update_review_cache_impl(
        state,
        findings_data,
        reviewed_files=reviewed_files,
        project_root=PROJECT_ROOT,
        utc_now_fn=utc_now,
    )


def import_holistic_findings(
    findings_data: list[dict] | dict,
    state: dict[str, object],
    lang_name: str,
) -> dict[str, object]:
    return _import_holistic_impl(
        findings_data,
        state,
        lang_name,
        project_root=PROJECT_ROOT,
        utc_now_fn=utc_now,
    )


def _update_holistic_review_cache(
    state: dict, findings_data: list[dict], *, lang_name: str | None = None
):
    return _update_holistic_cache_impl(
        state,
        findings_data,
        lang_name=lang_name,
        utc_now_fn=utc_now,
    )


def _resolve_holistic_coverage_findings(state: dict, diff: dict) -> None:
    return _resolve_holistic_coverage_impl(state, diff, utc_now_fn=utc_now)
