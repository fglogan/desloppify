"""AST-based Python code smell detectors.

Public API is intentionally narrow.
"""

from __future__ import annotations

from desloppify.languages.python.detectors.smells_ast._dispatch import _detect_ast_smells
from desloppify.languages.python.detectors.smells_ast._shared import _is_docstring, _is_return_none
from desloppify.languages.python.detectors.smells_ast._source_detectors import _collect_module_constants, _detect_duplicate_constants, _detect_star_import_no_all, _detect_vestigial_parameter

# Public API names (without leading underscores) used by callers outside this package.
detect_ast_smells = _detect_ast_smells
collect_module_constants = _collect_module_constants
detect_duplicate_constants = _detect_duplicate_constants
detect_star_import_no_all = _detect_star_import_no_all
detect_vestigial_parameter = _detect_vestigial_parameter
is_docstring = _is_docstring
is_return_none = _is_return_none

__all__ = [
    "collect_module_constants",
    "detect_ast_smells",
    "detect_duplicate_constants",
    "detect_star_import_no_all",
    "detect_vestigial_parameter",
    "_is_docstring",
    "_is_return_none",
    "is_docstring",
    "is_return_none",
]
