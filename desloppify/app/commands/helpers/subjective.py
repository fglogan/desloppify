"""Shared subjective follow-up rendering helpers."""

from __future__ import annotations

from desloppify.utils import colorize


def print_subjective_followup(followup, *, leading_newline: bool = False) -> bool:
    """Render common subjective quality/integrity guidance lines.

    Returns True when any line is rendered.
    """
    printed = False
    prefix = "\n" if leading_newline else ""
    if followup.low_assessed:
        print(
            colorize(
                f"{prefix}  Subjective quality (<{followup.threshold_label}%): "
                f"{followup.rendered}",
                "cyan",
            )
        )
        print(
            colorize(
                f"  Next command to improve subjective scores: {followup.command}",
                "dim",
            )
        )
        printed = True

    if followup.integrity_lines:
        if printed:
            print()
        for style, message in followup.integrity_lines:
            print(colorize(f"  {message}", style))
        printed = True
    return printed


__all__ = ["print_subjective_followup"]
