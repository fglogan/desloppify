"""Computed narrative context for LLM coaching and terminal headlines.

Pure functions that derive structured observations from state data.
No print statements — returns dicts that flow into _write_query().
"""

from __future__ import annotations

from desloppify.intelligence.narrative._constants import _FEEDBACK_URL, DETECTOR_TOOLS, STRUCTURAL_MERGE
from desloppify.intelligence.narrative.core import compute_narrative

__all__ = [
    "compute_narrative",
    "STRUCTURAL_MERGE",
    "DETECTOR_TOOLS",
    "_FEEDBACK_URL",
]
