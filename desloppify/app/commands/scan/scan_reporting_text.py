"""Text templates for scan reporting output."""

from __future__ import annotations

from textwrap import dedent


def build_workflow_guide(attest_example: str) -> str:
    """Render the scan workflow guide with current attestation text."""
    return dedent(
        f"""
        ## Workflow Guide

        1. **Review findings first** (if any): `desloppify issues` — high-value subjective findings
        2. **Run auto-fixers** (if available): `desloppify fix <fixer> --dry-run` to preview, then apply
        3. **Manual fixes**: `desloppify next` — highest-priority item. Fix it, then:
           `desloppify resolve fixed "<id>" --note "<what you did>" --attest "{attest_example}"`
           Required attestation keywords: 'I have actually' and 'not gaming'.
        4. **Rescan**: `desloppify scan --path <path>` — verify improvements, catch cascading effects
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

        ### Understanding Dimensions
        - **Mechanical** (File health, Code quality, etc.): Fix code → rescan
        - **Subjective** (Naming Quality, Logic Clarity, etc.): Address review findings → re-review
        - **Health vs Strict**: Health ignores wontfix; Strict penalizes it. Focus on Strict.
        """
    ).strip()


__all__ = ["build_workflow_guide"]
