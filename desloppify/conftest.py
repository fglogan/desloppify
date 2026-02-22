"""Shared pytest fixtures for desloppify test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from desloppify.core.runtime_state import RuntimeContext, runtime_scope
from desloppify.file_discovery import _clear_source_file_cache


@pytest.fixture()
def set_project_root(tmp_path: Path):
    """Set PROJECT_ROOT to tmp_path via RuntimeContext for the duration of a test."""
    ctx = RuntimeContext(project_root=tmp_path)
    with runtime_scope(ctx):
        _clear_source_file_cache()
        yield tmp_path
        _clear_source_file_cache()
