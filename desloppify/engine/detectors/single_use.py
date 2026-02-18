"""Single-use abstraction detection (imported by exactly 1 file = inline candidate)."""

import logging
from pathlib import Path

from desloppify.utils import rel

logger = logging.getLogger(__name__)
_LANG_PLUGIN_ENTRYPOINTS = frozenset(
    {
        "commands.py",
        "extractors.py",
        "phases.py",
        "move.py",
        "review.py",
        "test_coverage.py",
    }
)


def _is_lang_plugin_entrypoint(path: Path) -> bool:
    """Whether *path* is a language plugin contract file loaded by convention."""
    if path.name not in _LANG_PLUGIN_ENTRYPOINTS:
        return False
    parts = path.parts
    for idx, segment in enumerate(parts[:-2]):
        if segment != "lang":
            continue
        plugin_name = parts[idx + 1]
        return bool(plugin_name and not plugin_name.startswith("_"))
    return False


def detect_single_use_abstractions(
    path: Path,
    graph: dict,
    barrel_names: set[str],
) -> tuple[list[dict], int]:
    """Find exported symbols imported by exactly 1 file — candidates for inlining.

    Args:
        barrel_names: set of barrel filenames to skip. Required.

    Returns:
        (entries, total_candidate_files) — candidates are files with exactly 1 importer.
    """
    entries = []
    total_candidates = 0
    for filepath, entry in graph.items():
        if entry["importer_count"] != 1:
            continue
        try:
            p = Path(filepath)
            if not p.exists():
                continue
            basename = p.name
            if basename in barrel_names:
                continue
            if _is_lang_plugin_entrypoint(p):
                continue
            total_candidates += 1
            loc = len(p.read_text().splitlines())
            if loc < 20 or loc > 300:
                continue
            importer = list(entry["importers"])[0]
            entries.append(
                {
                    "file": filepath,
                    "loc": loc,
                    "sole_importer": rel(importer),
                    "reason": f"Only imported by {rel(importer)} — consider inlining",
                    "import_count": entry.get("import_count", 0),
                }
            )
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug(
                "Skipping unreadable file in single-use detector: %s (%s)",
                filepath,
                exc,
            )
            continue
    return sorted(entries, key=lambda e: -e["loc"]), total_candidates
