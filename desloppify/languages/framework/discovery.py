"""Language plugin discovery and import error surfacing."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

from desloppify.languages.framework import registry_state

logger = logging.getLogger(__name__)


def raise_load_errors() -> None:
    if not registry_state._load_errors:
        return
    lines = ["Language plugin import failures:"]
    for module_name, ex in sorted(registry_state._load_errors.items()):
        lines.append(f"  - {module_name}: {type(ex).__name__}: {ex}")
    raise ImportError("\n".join(lines))


def load_all() -> None:
    """Import all language modules to trigger registration."""
    if registry_state._load_attempted:
        raise_load_errors()
        return

    lang_dir = Path(__file__).resolve().parent
    if lang_dir.name == "framework":
        lang_dir = lang_dir.parent
    base_package = __package__.rsplit(".", 1)[0]
    failures: dict[str, BaseException] = {}

    # Discover single-file plugins by naming convention (e.g. plugin_rust.py).
    for f in sorted(lang_dir.glob("plugin_*.py")):
        module_name = f".{f.stem}"
        try:
            importlib.import_module(module_name, base_package)
        except (
            ImportError,
            SyntaxError,
            ValueError,
            TypeError,
            RuntimeError,
            OSError,
        ) as ex:
            logger.debug("Language plugin import failed for %s: %s", module_name, ex)
            failures[module_name] = ex

    # Discover packages (e.g. lang/typescript/)
    for d in sorted(lang_dir.iterdir()):
        if (
            d.is_dir()
            and (d / "__init__.py").exists()
            and not d.name.startswith("_")
            and d.name != "framework"
        ):
            module_name = f".{d.name}"
            try:
                importlib.import_module(module_name, base_package)
            except (
                ImportError,
                SyntaxError,
                ValueError,
                TypeError,
                RuntimeError,
                OSError,
            ) as ex:
                logger.debug(
                    "Language package import failed for %s: %s", module_name, ex
                )
                failures[module_name] = ex

    registry_state._load_attempted = True
    registry_state._load_errors = failures
    raise_load_errors()
