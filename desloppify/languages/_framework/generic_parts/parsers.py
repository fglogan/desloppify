"""Output parser catalog for generic language plugins."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_gnu(output: str, scan_path: Path) -> list[dict]:
    """Parse `file:line: message` or `file:line:col: message` format."""
    entries: list[dict] = []
    for line in output.splitlines():
        match = re.match(r"^(.+?):(\d+)(?::\d+)?:\s*(.+)$", line)
        if match:
            entries.append(
                {
                    "file": match.group(1).strip(),
                    "line": int(match.group(2)),
                    "message": match.group(3).strip(),
                }
            )
    return entries


def parse_golangci(output: str, scan_path: Path) -> list[dict]:
    """Parse golangci-lint JSON output: `{"Issues": [...]}`."""
    entries: list[dict] = []
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return entries
    for issue in data.get("Issues") or []:
        pos = issue.get("Pos") or {}
        filename = pos.get("Filename", "")
        line = pos.get("Line", 0)
        text = issue.get("Text", "")
        if filename and text:
            entries.append({"file": filename, "line": line, "message": text})
    return entries


def parse_json(output: str, scan_path: Path) -> list[dict]:
    """Parse flat JSON array with field aliases."""
    entries: list[dict] = []
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return entries
    items = data if isinstance(data, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        filename = item.get("file") or item.get("filename") or item.get("path") or ""
        line = item.get("line") or item.get("line_no") or item.get("row") or 0
        message = item.get("message") or item.get("text") or item.get("reason") or ""
        if filename and message:
            entries.append(
                {
                    "file": str(filename),
                    "line": int(line),
                    "message": str(message),
                }
            )
    return entries


def parse_rubocop(output: str, scan_path: Path) -> list[dict]:
    """Parse RuboCop JSON: `{"files": [{"path": ..., "offenses": [...]}]}`."""
    entries: list[dict] = []
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return entries
    for fobj in data.get("files") or []:
        filepath = fobj.get("path", "")
        for offense in fobj.get("offenses") or []:
            loc = offense.get("location") or {}
            line = loc.get("line", 0)
            message = offense.get("message", "")
            if filepath and message:
                entries.append({"file": filepath, "line": int(line), "message": message})
    return entries


def parse_cargo(output: str, scan_path: Path) -> list[dict]:
    """Parse cargo clippy/check JSON Lines output."""
    entries: list[dict] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.debug("Skipping unparseable cargo output line: %s", exc)
            continue
        if data.get("reason") != "compiler-message":
            continue
        msg = data.get("message") or {}
        spans = msg.get("spans") or []
        rendered = msg.get("rendered") or msg.get("message") or ""
        if not spans or not rendered:
            continue
        span = spans[0]
        filename = span.get("file_name", "")
        line_no = span.get("line_start", 0)
        summary = rendered.split("\n")[0].strip() if rendered else ""
        if filename and summary:
            entries.append({"file": filename, "line": int(line_no), "message": summary})
    return entries


def parse_eslint(output: str, scan_path: Path) -> list[dict]:
    """Parse ESLint JSON: `[{"filePath": ..., "messages": [...]}]`."""
    entries: list[dict] = []
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, ValueError):
        return entries
    for fobj in data if isinstance(data, list) else []:
        if not isinstance(fobj, dict):
            continue
        filepath = fobj.get("filePath", "")
        for msg in fobj.get("messages") or []:
            line = msg.get("line", 0)
            message = msg.get("message", "")
            if filepath and message:
                entries.append({"file": str(filepath), "line": int(line), "message": str(message)})
    return entries


PARSERS: dict[str, Callable[[str, Path], list[dict]]] = {
    "gnu": parse_gnu,
    "golangci": parse_golangci,
    "json": parse_json,
    "rubocop": parse_rubocop,
    "cargo": parse_cargo,
    "eslint": parse_eslint,
}


__all__ = [
    "PARSERS",
    "parse_cargo",
    "parse_eslint",
    "parse_gnu",
    "parse_golangci",
    "parse_json",
    "parse_rubocop",
]
