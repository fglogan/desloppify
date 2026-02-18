"""Compatibility facade for subjective scan reporting helpers."""

from __future__ import annotations

from desloppify.app.commands.scan.scan_reporting_subjective_common import SubjectiveFollowup, flatten_cli_keys, subjective_rerun_command
from desloppify.app.commands.scan.scan_reporting_subjective_integrity import subjective_entries_for_dimension_keys, subjective_integrity_followup, subjective_integrity_notice_lines
from desloppify.app.commands.scan.scan_reporting_subjective_output import build_subjective_followup, show_subjective_paths

__all__ = [
    "SubjectiveFollowup",
    "build_subjective_followup",
    "flatten_cli_keys",
    "show_subjective_paths",
    "subjective_entries_for_dimension_keys",
    "subjective_integrity_followup",
    "subjective_integrity_notice_lines",
    "subjective_rerun_command",
]
