"""Remediation plan generation wrappers."""

from __future__ import annotations

from pathlib import Path

from desloppify.intelligence.review.prepare_internal.remediation_engine import empty_plan as _empty_plan_impl
from desloppify.intelligence.review.prepare_internal.remediation_engine import generate_remediation_plan as _generate_plan_impl


def _empty_plan(state: dict, lang_name: str) -> str:
    """Back-compat wrapper for empty-plan rendering."""
    return _empty_plan_impl(state, lang_name)


def generate_remediation_plan(
    state: dict, lang_name: str, *, output_path: Path | None = None
) -> str:
    """Back-compat wrapper for remediation plan generation."""
    return _generate_plan_impl(state, lang_name, output_path=output_path)
