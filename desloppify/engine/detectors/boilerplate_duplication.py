"""Detect repeated small boilerplate blocks across files."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_STRING_RE = re.compile(r"""(["'`])(?:\\.|(?!\1).)*\1""")
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")
_IDENT_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")

_KEYWORDS = {
    # Python
    "def",
    "class",
    "return",
    "if",
    "elif",
    "else",
    "for",
    "while",
    "try",
    "except",
    "finally",
    "with",
    "as",
    "pass",
    "raise",
    "import",
    "from",
    "in",
    "and",
    "or",
    "not",
    "lambda",
    "True",
    "False",
    "None",
    # TypeScript / JS
    "function",
    "const",
    "let",
    "var",
    "export",
    "default",
    "new",
    "switch",
    "case",
    "break",
    "continue",
    "throw",
    "catch",
    "async",
    "await",
    "interface",
    "type",
    "extends",
}


def _normalize_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""
    stripped = _STRING_RE.sub('"STR"', stripped)
    stripped = _NUMBER_RE.sub("NUM", stripped)

    def _replace_ident(match: re.Match[str]) -> str:
        token = match.group(0)
        return token if token in _KEYWORDS else "ID"

    stripped = _IDENT_RE.sub(_replace_ident, stripped)
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped


def _window_is_informative(window_lines: list[str]) -> bool:
    if not window_lines:
        return False
    joined = " ".join(window_lines).strip()
    if len(joined) < 40:
        return False
    if joined.count("ID") < 4:
        return False
    if not any(ch in joined for ch in ("(", ")", "=", ".", ":", "{", "}")):
        return False
    return True


def detect_boilerplate_duplication(
    path: Path,
    *,
    file_finder,
    window_size: int = 4,
    min_distinct_files: int = 3,
) -> tuple[list[dict], int]:
    """Detect repeated normalized line windows across files."""
    files = file_finder(path)
    scan_root = path if path.is_absolute() else path.resolve()
    windows: dict[str, list[dict]] = {}

    for filepath in files:
        candidate = Path(filepath)
        if candidate.is_absolute():
            full = candidate
        else:
            rooted = scan_root / candidate
            full = rooted if rooted.exists() else candidate.resolve()
        try:
            lines = full.read_text().splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            # Keep context handy while intentionally skipping unreadable files.
            _ = (full, exc)
            continue

        normalized: list[tuple[int, str]] = []
        for lineno, raw in enumerate(lines, 1):
            norm = _normalize_line(raw)
            if not norm:
                continue
            normalized.append((lineno, norm))
        if len(normalized) < window_size:
            continue

        for idx in range(0, len(normalized) - window_size + 1):
            segment = normalized[idx : idx + window_size]
            seg_lines = [line for _, line in segment]
            if not _window_is_informative(seg_lines):
                continue
            signature = "\n".join(seg_lines)
            key = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:16]
            windows.setdefault(key, []).append(
                {"file": filepath, "line": segment[0][0], "signature": signature}
            )

    entries: list[dict] = []
    for key, occurrences in windows.items():
        by_file: dict[str, int] = {}
        for occurrence in sorted(occurrences, key=lambda item: (item["file"], item["line"])):
            by_file.setdefault(occurrence["file"], occurrence["line"])
        if len(by_file) < min_distinct_files:
            continue
        sample_occurrence = min(occurrences, key=lambda item: (item["file"], item["line"]))
        locations = [
            {"file": file, "line": line}
            for file, line in sorted(by_file.items(), key=lambda item: item[0])
        ]
        entries.append(
            {
                "id": key,
                "distinct_files": len(by_file),
                "window_size": window_size,
                "locations": locations,
                "sample": sample_occurrence["signature"].splitlines(),
            }
        )

    entries.sort(key=lambda item: (-item["distinct_files"], item["id"]))
    return entries, len(files)


__all__ = ["detect_boilerplate_duplication"]
