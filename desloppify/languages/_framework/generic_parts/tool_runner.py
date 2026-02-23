"""External command execution helpers for generic language plugins."""

from __future__ import annotations

import re
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path

SubprocessRun = Callable[..., subprocess.CompletedProcess[str]]

_SHELL_META_CHARS = re.compile(r"[|&;<>()$`\\n]")


def resolve_command_argv(cmd: str) -> list[str]:
    """Return argv for subprocess.run without relying on shell=True."""
    if _SHELL_META_CHARS.search(cmd):
        return ["/bin/sh", "-lc", cmd]
    try:
        argv = shlex.split(cmd, posix=True)
    except ValueError:
        return ["/bin/sh", "-lc", cmd]
    return argv if argv else ["/bin/sh", "-lc", cmd]


def run_tool(
    cmd: str,
    path: Path,
    parser: Callable[[str, Path], list[dict]],
    *,
    run_subprocess: SubprocessRun | None = None,
) -> list[dict]:
    """Run an external tool and parse its output. Returns [] on failure."""
    runner = run_subprocess or subprocess.run
    try:
        result = runner(
            resolve_command_argv(cmd),
            shell=False,
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    output = (result.stdout or "") + (result.stderr or "")
    if not output.strip():
        return []
    return parser(output, path)


__all__ = ["resolve_command_argv", "run_tool", "SubprocessRun"]
