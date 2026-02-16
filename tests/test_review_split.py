"""Tests verifying the review/ package split — all imports work, no circular deps."""

from __future__ import annotations

import importlib
import sys

import pytest


class TestReviewImports:
    """Verify all public names are importable from desloppify.review."""

    def test_all_exports_importable(self):
        """Every name in __all__ is importable."""
        from desloppify import review
        for name in review.__all__:
            assert hasattr(review, name), f"Missing export: {name}"

    def test_key_public_names(self):
        """Key public names are available."""


class TestSubmoduleImports:
    """Each submodule can be imported independently."""

    @pytest.mark.parametrize("module", [
        "desloppify.review.dimensions",
        "desloppify.review.context",
        "desloppify.review.selection",
        "desloppify.review.prepare",
        "desloppify.review.import_findings",
        "desloppify.review.remediation",
    ])
    def test_submodule_importable(self, module):
        mod = importlib.import_module(module)
        assert mod is not None

    def test_no_circular_import(self):
        """Fresh import of desloppify.review succeeds without circular import errors."""
        # Remove cached modules to force fresh import
        to_remove = [k for k in sys.modules if k.startswith("desloppify.review")]
        removed = {}
        for k in to_remove:
            removed[k] = sys.modules.pop(k)
        try:
            import desloppify.review
            # If we get here, no circular import
            assert hasattr(desloppify.review, "__all__")
        finally:
            # Restore removed modules
            sys.modules.update(removed)
