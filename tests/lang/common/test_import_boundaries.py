"""Import boundary and layering regression tests."""

from __future__ import annotations

import ast
from pathlib import Path


def _module_name_from_import(node: ast.AST) -> str:
    if isinstance(node, ast.Import):
        if not node.names:
            return ""
        return node.names[0].name
    if isinstance(node, ast.ImportFrom):
        return node.module or ""
    return ""


def test_detectors_layer_does_not_import_lang_layer():
    detector_dir = Path("desloppify/detectors")
    offenders: list[tuple[str, str]] = []

    for py_file in sorted(detector_dir.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Import | ast.ImportFrom):
                continue
            module_name = _module_name_from_import(node)
            if module_name.startswith("desloppify.languages"):
                offenders.append((str(py_file), module_name))

    assert offenders == [], f"detectors imported lang modules: {offenders}"


def test_review_cmd_uses_split_modules():
    src = Path("desloppify/commands/review/cmd.py").read_text()
    assert "review_batches as review_batches_mod" in src
    assert "review_import as review_import_mod" in src
    assert "review_prepare as review_prepare_mod" in src
    assert "review_runtime as review_runtime_mod" in src


def test_scan_reporting_aggregator_uses_split_modules():
    src = Path("desloppify/commands/scan/scan_reporting_dimensions.py").read_text()
    assert "scan_reporting_progress as progress_mod" in src
    assert "scan_reporting_breakdown as breakdown_mod" in src
    assert "scan_reporting_subjective_paths as subjective_paths_mod" in src


def test_scan_subjective_paths_aggregator_uses_split_modules():
    src = Path("desloppify/commands/scan/scan_reporting_subjective_paths.py").read_text()
    assert "from .scan_reporting_subjective_common import" in src
    assert "from .scan_reporting_subjective_integrity import" in src
    assert "from .scan_reporting_subjective_output import" in src


def test_cli_parser_uses_group_module():
    src = Path("desloppify/cli_parser.py").read_text()
    assert "from .parser_groups import" in src
