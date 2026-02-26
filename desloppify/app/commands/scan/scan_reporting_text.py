"""Text templates for scan reporting output."""

from __future__ import annotations

from textwrap import dedent


def build_workflow_guide(attest_example: str) -> str:
    """Render the scan workflow guide with current attestation text."""
    return dedent(
        f"""
        ## Workflow Guide

        1. **Run auto-fixers** (if available): `desloppify fix <fixer> --dry-run` to preview, then apply
        2. **Manual fixes**: `desloppify next` — highest-priority item. Fix it, then:
           `desloppify resolve fixed "<id>" --note "<what you did>" --attest "{attest_example}"`
           Required attestation keywords: 'I have actually' and 'not gaming'.
        3. **Rescan**: `desloppify scan --path <path>` — verify improvements, catch cascading effects
        4. **Subjective review**: `desloppify review --prepare` → import → `desloppify show subjective`
        5. **Reset subjective baseline when needed**:
           `desloppify scan --path <path> --reset-subjective` (then run a fresh review/import cycle)
        6. **Check progress**: `desloppify status` — dimension scores dashboard

        ### Decision Guide
        - **Tackle**: T1/T2 (high impact), auto-fixable, security findings
        - **Consider skipping**: T4 low-confidence, test/config zone findings (lower impact)
        - **Wontfix**: Intentional patterns, false positives →
          `desloppify resolve wontfix "<id>" --note "<why>" --attest "{attest_example}"`
        - **Batch wontfix**: Multiple intentional patterns →
          `desloppify resolve wontfix "<detector>::*::<category>" --note "<why>" --attest "{attest_example}"`

        ### Understanding Scores
        - **Overall**: 40% mechanical + 60% subjective. Lenient — wontfix doesn't count against you.
        - **Objective**: Mechanical detectors only (no subjective review component).
        - **Strict**: Same as overall, but wontfix items count as open. THIS IS YOUR NORTH STAR.
        - **Verified**: Like strict, but only credits fixes the scanner has confirmed.
        - Wontfix is not free — every wontfix widens the overall↔strict gap.
        - Re-reviewing subjective dimensions can LOWER scores if the reviewer finds issues.

        ### Understanding Dimensions
        - **Mechanical** (File health, Code quality, etc.): Fix code → rescan
        - **Subjective** (Naming quality, Logic clarity, etc.): Address review findings → re-review
        """
    ).strip()


__all__ = ["build_workflow_guide"]
