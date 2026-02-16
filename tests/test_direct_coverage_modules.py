"""Direct coverage tests for modules currently marked as transitive/untested."""

from __future__ import annotations

import ast
import inspect

import desloppify.commands.config_cmd as config_cmd
import desloppify.commands.resolve as resolve_cmd
import desloppify.detectors.lang_hooks as lang_hooks
import desloppify.lang.csharp.move as csharp_move
import desloppify.lang.csharp.review as csharp_review
import desloppify.lang.finding_factories as finding_factories
import desloppify.lang.python.detectors.dict_keys_visitor as dict_keys_visitor
import desloppify.lang.python.detectors.private_imports as private_imports
import desloppify.lang.python.detectors.smells_ast as smells_ast
import desloppify.lang.python.phases as py_phases
import desloppify.lang.python.review as py_review
import desloppify.lang.typescript.phases as ts_phases
import desloppify.lang.typescript.review as ts_review
import desloppify.output._scorecard_draw as scorecard_draw
import desloppify.review.dimensions as review_dimensions


def test_direct_module_coverage_smoke_signals():
    """Exercise targeted modules with direct imports and behavioral assertions."""
    assert callable(config_cmd.cmd_config)
    assert callable(config_cmd._config_show)
    assert callable(resolve_cmd.cmd_resolve)
    assert callable(resolve_cmd.cmd_ignore_pattern)

    assert csharp_move.find_replacements("a", "b", {}) == {}
    assert csharp_move.find_self_replacements("a", "b", {}) == []
    assert csharp_move.filter_intra_package_importer_changes("a", [("x", "y")], set()) == [("x", "y")]
    assert csharp_move.filter_directory_self_changes("a", [("m", "n")], set()) == [("m", "n")]
    assert csharp_review.module_patterns("public class A {}")
    assert csharp_review.api_surface({"A.cs": "public class A {}"}) == {}

    assert callable(finding_factories.make_unused_findings)
    assert callable(finding_factories.make_dupe_findings)
    assert finding_factories.SMELL_TIER_MAP["high"].name == "QUICK_FIX"
    assert finding_factories.SMELL_TIER_MAP["low"].name == "JUDGMENT"

    assert issubclass(dict_keys_visitor.DictKeyVisitor, ast.NodeVisitor)
    assert private_imports._is_dunder("__len__")
    assert not private_imports._is_dunder("_private")
    assert private_imports._module_of("pkg/file.py").endswith("pkg")

    return_none = ast.parse("return None").body[0]
    expr_stmt = ast.parse('"""doc"""').body[0]
    assert smells_ast._is_return_none(return_none)
    assert smells_ast._is_docstring(expr_stmt)

    assert callable(py_phases._phase_unused)
    assert callable(py_phases._phase_structural)
    assert callable(py_phases._phase_smells)
    assert callable(py_phases._phase_layer_violation)

    assert py_review.module_patterns("def run():\n    pass\n")
    assert py_review.api_surface({"x.py": "def x():\n    pass\n"}) == {}

    assert ts_review.module_patterns("export default function A() {}\n")
    assert ts_review.api_surface({"a.ts": "export function f() {}\n"}) == {}

    assert callable(ts_phases._compute_ts_destructure_props)
    assert callable(ts_phases._compute_ts_inline_types)
    assert callable(ts_phases._phase_structural)
    assert callable(ts_phases._phase_smells)

    assert callable(scorecard_draw._draw_left_panel)
    assert callable(scorecard_draw._draw_right_panel)
    assert callable(scorecard_draw._draw_ornament)

    assert isinstance(review_dimensions.HOLISTIC_DIMENSIONS, list)
    assert "cross_module_architecture" in review_dimensions.HOLISTIC_DIMENSIONS
    assert isinstance(review_dimensions.get_lang_guidance("python"), dict)

    assert lang_hooks.load_lang_hook_module(None, "test_coverage") is None
    assert lang_hooks.load_lang_hook_module("nonexistent_lang", "test_coverage") is None
    assert inspect.isfunction(lang_hooks.load_lang_hook_module)
