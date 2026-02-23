"""Detector/fixer factory helpers for generic language plugins."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from desloppify.languages._framework.base.types import (
    DetectorPhase,
    FixerConfig,
    FixResult,
)
from desloppify.languages._framework.generic_parts.parsers import PARSERS
from desloppify.languages._framework.generic_parts.tool_runner import (
    SubprocessRun,
    resolve_command_argv,
    run_tool,
)
from desloppify.state import make_finding


def make_tool_phase(
    label: str,
    cmd: str,
    fmt: str,
    smell_id: str,
    tier: int,
) -> DetectorPhase:
    """Create a DetectorPhase that runs an external tool and parses output."""
    parser = PARSERS[fmt]

    def run(path: Path, lang: object) -> tuple[list, dict]:
        del lang
        entries = run_tool(cmd, path, parser)
        if not entries:
            return [], {}
        findings = [
            make_finding(
                smell_id,
                entry["file"],
                f"{smell_id}::{entry['line']}",
                tier=tier,
                confidence="medium",
                summary=entry["message"],
            )
            for entry in entries
        ]
        return findings, {smell_id: len(entries)}

    return DetectorPhase(label, run)


def make_detect_fn(cmd: str, parser: Callable[[str, Path], list[dict]]) -> Callable:
    """Create detect function that runs a tool and returns parsed entries."""
    return make_detect_fn_with_runner(cmd, parser)


def make_detect_fn_with_runner(
    cmd: str,
    parser: Callable[[str, Path], list[dict]],
    *,
    run_subprocess: SubprocessRun | None = None,
) -> Callable:
    """Create detect function that runs a tool with an injected subprocess runner."""
    def detect(path, **kwargs):
        del kwargs
        return run_tool(cmd, path, parser, run_subprocess=run_subprocess)

    return detect


def make_generic_fixer(tool: dict[str, Any]) -> FixerConfig:
    """Create a FixerConfig from a tool spec with fix_cmd."""
    return make_generic_fixer_with_runner(tool)


def make_generic_fixer_with_runner(
    tool: dict[str, Any],
    *,
    run_subprocess: SubprocessRun | None = None,
) -> FixerConfig:
    """Create a FixerConfig from a tool spec with an injected subprocess runner."""
    smell_id = tool["id"]
    fix_cmd = tool["fix_cmd"]
    detect = make_detect_fn_with_runner(
        tool["cmd"],
        PARSERS[tool["fmt"]],
        run_subprocess=run_subprocess,
    )

    def fix(entries, dry_run=False, path=None, **kwargs):
        del kwargs
        if dry_run or not path:
            return FixResult(entries=[{"file": e["file"], "line": e["line"]} for e in entries])
        runner = run_subprocess or subprocess.run
        try:
            runner(
                resolve_command_argv(fix_cmd),
                shell=False,
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return FixResult(entries=[], skip_reasons={"tool_unavailable": len(entries)})
        remaining = detect(path)
        fixed_count = max(0, len(entries) - len(remaining))
        return FixResult(
            entries=[{"file": e["file"], "fixed": True} for e in entries[:fixed_count]]
        )

    return FixerConfig(
        label=f"Fix {tool['label']} issues",
        detect=detect,
        fix=fix,
        detector=smell_id,
        verb="Fixed",
        dry_verb="Would fix",
    )


__all__ = [
    "make_detect_fn",
    "make_detect_fn_with_runner",
    "make_generic_fixer",
    "make_generic_fixer_with_runner",
    "make_tool_phase",
]
