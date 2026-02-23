"""Prompt template helpers for holistic review batch subagents."""

from __future__ import annotations

from pathlib import Path


def render_batch_prompt(
    *,
    repo_root: Path,
    packet_path: Path,
    batch_index: int,
    batch: dict[str, object],
) -> str:
    """Render one subagent prompt for a holistic investigation batch."""
    name = str(batch.get("name", f"Batch {batch_index + 1}"))
    dims_raw = batch.get("dimensions", [])
    dims = (
        [str(d) for d in dims_raw if isinstance(d, str) and d]
        if isinstance(dims_raw, list | tuple)
        else []
    )
    why = str(batch.get("why", "")).strip()
    files_raw = batch.get("files_to_read", [])
    files = (
        [str(f) for f in files_raw if isinstance(f, str) and f]
        if isinstance(files_raw, list | tuple)
        else []
    )
    file_lines = "\n".join(f"- {f}" for f in files) if files else "- (none)"
    dim_text = ", ".join(dims) if dims else "(none)"
    package_org_focus = ""
    if "package_organization" in set(dims):
        package_org_focus = (
            "9a. For package_organization, ground scoring in objective structure signals from "
            "`holistic_context.structure` (root_files fan_in/fan_out roles, directory_profiles, "
            "coupling_matrix). Prefer thresholded evidence (for example: fan_in < 5 for root "
            "stragglers, import-affinity > 60%, directories > 10 files with mixed concerns).\n"
            "9b. Suggestions must include a staged reorg plan (target folders, move order, "
            "and import-update/validation commands).\n"
        )

    return (
        "You are a focused subagent reviewer for a single holistic investigation batch.\n\n"
        f"Repository root: {repo_root}\n"
        f"Blind packet: {packet_path}\n"
        f"Batch index: {batch_index + 1}\n"
        f"Batch name: {name}\n"
        f"Batch dimensions: {dim_text}\n"
        f"Batch rationale: {why}\n\n"
        "Files assigned:\n"
        f"{file_lines}\n\n"
        "Task requirements:\n"
        "1. Read the blind packet and follow `system_prompt` constraints exactly.\n"
        "2. Evaluate ONLY listed files and ONLY listed dimensions for this batch.\n"
        "3. Return 0-10 high-quality findings for this batch (empty array allowed).\n"
        "4. Score/finding consistency is required: broader or more severe findings MUST lower dimension scores.\n"
        "5. Every finding must include `related_files` with at least 2 files when possible.\n"
        "6. Every finding must include `dimension`, `identifier`, `summary`, `evidence`, `suggestion`, and `confidence`.\n"
        "7. Every finding must include `impact_scope` and `fix_scope`.\n"
        "8. Every scored dimension MUST include dimension_notes with concrete evidence.\n"
        "9. If a dimension score is >85, include `unreported_risk` in dimension_notes.\n"
        "10. Use exactly one decimal place for every assessment and abstraction sub-axis score.\n"
        f"{package_org_focus}"
        "11. Ignore prior chat context and any target-threshold assumptions.\n"
        "12. Do not edit repository files.\n"
        "13. Return ONLY valid JSON, no markdown fences.\n\n"
        "Scope enums:\n"
        '- impact_scope: "local" | "module" | "subsystem" | "codebase"\n'
        '- fix_scope: "single_edit" | "multi_file_refactor" | "architectural_change"\n\n'
        "Output schema:\n"
        "{\n"
        f'  "batch": "{name}",\n'
        f'  "batch_index": {batch_index + 1},\n'
        '  "assessments": {"<dimension>": <0-100 with one decimal place>},\n'
        '  "dimension_notes": {\n'
        '    "<dimension>": {\n'
        '      "evidence": ["specific code observations"],\n'
        '      "impact_scope": "local|module|subsystem|codebase",\n'
        '      "fix_scope": "single_edit|multi_file_refactor|architectural_change",\n'
        '      "confidence": "high|medium|low",\n'
        '      "unreported_risk": "required when score >85",\n'
        '      "sub_axes": {"abstraction_leverage": 0-100 with one decimal place, "indirection_cost": 0-100 with one decimal place, "interface_honesty": 0-100 with one decimal place}  // required for abstraction_fitness when evidence supports it\n'
        "    }\n"
        "  },\n"
        '  "findings": [{\n'
        '    "dimension": "<dimension>",\n'
        '    "identifier": "short_id",\n'
        '    "summary": "one-line defect summary",\n'
        '    "related_files": ["relative/path.py"],\n'
        '    "evidence": ["specific code observation"],\n'
        '    "suggestion": "concrete fix recommendation",\n'
        '    "confidence": "high|medium|low",\n'
        '    "impact_scope": "local|module|subsystem|codebase",\n'
        '    "fix_scope": "single_edit|multi_file_refactor|architectural_change"\n'
        "  }]\n"
        "}\n"
    )


__all__ = ["render_batch_prompt"]
