"""State schema migrations."""

from __future__ import annotations


def _migrate_progress_scores(state: dict) -> None:
    """Normalize legacy score keys into canonical score fields."""
    if state.get("objective_score") is None and state.get("score") is not None:
        state["objective_score"] = state["score"]
    if state.get("overall_score") is None:
        if state.get("objective_score") is not None:
            state["overall_score"] = state["objective_score"]
        elif state.get("score") is not None:
            state["overall_score"] = state["score"]
    if state.get("strict_score") is None and state.get("objective_strict") is not None:
        state["strict_score"] = state["objective_strict"]
    if (
        state.get("verified_strict_score") is None
        and state.get("strict_score") is not None
    ):
        state["verified_strict_score"] = state["strict_score"]
    if not isinstance(state.get("subjective_integrity"), dict):
        legacy_status = state.get("subjective_integrity_status")
        if legacy_status is None:
            state["subjective_integrity"] = {}
        else:
            state["subjective_integrity"] = {"status": str(legacy_status)}

    for entry in state.get("scan_history", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("objective_score") is None and entry.get("score") is not None:
            entry["objective_score"] = entry["score"]
        if entry.get("overall_score") is None:
            if entry.get("objective_score") is not None:
                entry["overall_score"] = entry["objective_score"]
            elif entry.get("score") is not None:
                entry["overall_score"] = entry["score"]
        if (
            entry.get("strict_score") is None
            and entry.get("objective_strict") is not None
        ):
            entry["strict_score"] = entry["objective_strict"]
        if (
            entry.get("verified_strict_score") is None
            and entry.get("strict_score") is not None
        ):
            entry["verified_strict_score"] = entry["strict_score"]
        if not isinstance(entry.get("subjective_integrity"), dict):
            legacy_status = entry.get("subjective_integrity_status")
            if legacy_status is not None:
                entry["subjective_integrity"] = {"status": str(legacy_status)}
            elif "subjective_integrity" in entry:
                entry["subjective_integrity"] = None
        entry.pop("score", None)
        entry.pop("objective_strict", None)
        entry.pop("subjective_integrity_status", None)

    state.pop("score", None)
    state.pop("objective_strict", None)
    state.pop("subjective_integrity_status", None)
