"""CLI context loading helpers for `desloppify tree` and `desloppify viz`."""

from __future__ import annotations

import json
from pathlib import Path

from desloppify import state as state_module
from desloppify.app.commands.helpers.lang import resolve_lang
from desloppify.app.commands.helpers.runtime import command_runtime


def load_cmd_context(args: object) -> tuple[Path, object | None, dict | None]:
    """Load language config and state from CLI args."""
    lang = resolve_lang(args)
    runtime = command_runtime(args)
    state = runtime.state
    if not isinstance(state, dict):
        scan_state_path = runtime.state_path
        try:
            state = state_module.load_state(scan_state_path)
        except (OSError, json.JSONDecodeError):
            state = None
    return Path(args.path), lang, state


__all__ = ["load_cmd_context"]
