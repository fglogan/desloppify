"""Scorecard badge image generator — produces a visual health summary PNG."""

from __future__ import annotations

import importlib
import logging
import os
import re
import subprocess
from importlib import metadata as importlib_metadata
from pathlib import Path

from desloppify.core.fallbacks import log_best_effort_failure
from desloppify.utils import PROJECT_ROOT
from desloppify.app.output.scorecard_parts.dimensions import collapse_elegance_dimensions, limit_scorecard_dimensions, prepare_scorecard_dimensions, prepare_scorecard_dimensions_internal, resolve_scorecard_lang
from desloppify.app.output.scorecard_parts.theme import ACCENT, BG, BG_ROW_ALT, BG_SCORE, BG_TABLE, BORDER, DIM, FRAME, SCALE, TEXT, fmt_score, load_font, scale, score_color

logger = logging.getLogger(__name__)

_collapse_elegance_dimensions = collapse_elegance_dimensions
_limit_scorecard_dimensions = limit_scorecard_dimensions
_prepare_scorecard_dimensions = prepare_scorecard_dimensions_internal
_resolve_scorecard_lang = resolve_scorecard_lang
_ACCENT = ACCENT
_BG = BG
_BG_ROW_ALT = BG_ROW_ALT
_BG_SCORE = BG_SCORE
_BG_TABLE = BG_TABLE
_BORDER = BORDER
_DIM = DIM
_FRAME = FRAME
_SCALE = SCALE
_TEXT = TEXT
_fmt_score = fmt_score
_load_font = load_font
_s = scale
_score_color = score_color


def _get_project_name() -> str:
    """Get project name from GitHub API, git remote, or directory name.

    Tries `gh` CLI first for the canonical owner/repo (handles renames and
    transfers). Falls back to parsing the git remote URL, then directory name.
    """
    # Try gh CLI for canonical name (handles username renames, repo transfers)
    try:
        name = subprocess.check_output(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
        if "/" in name:
            return name
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
    ) as exc:
        log_best_effort_failure(logger, "resolve repo name with gh", exc)

    # Fall back to git remote URL parsing
    try:
        url = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
        # SSH: git@github.com:owner/repo.git
        # HTTPS: https://github.com/owner/repo.git
        # HTTPS+token: https://TOKEN@github.com/owner/repo.git
        if url.startswith("git@") and ":" in url:
            path = url.split(":")[-1]
        else:
            path = "/".join(url.split("/")[-2:])
        return path.removesuffix(".git")
    except (
        subprocess.CalledProcessError,
        FileNotFoundError,
        IndexError,
        subprocess.TimeoutExpired,
    ):
        return PROJECT_ROOT.name


def _get_package_version() -> str:
    """Get package version for scorecard display.

    Prefers installed package metadata. Falls back to parsing local
    `pyproject.toml` when running from source without an installed package.
    """
    try:
        return importlib_metadata.version("desloppify")
    except importlib_metadata.PackageNotFoundError as exc:
        log_best_effort_failure(
            logger, "read installed desloppify package metadata", exc
        )

    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    try:
        text = pyproject_path.read_text(encoding="utf-8")
        match = re.search(r'^\s*version\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
        if match:
            return match.group(1)
    except OSError as exc:
        log_best_effort_failure(
            logger,
            f"read {pyproject_path} while resolving package version",
            exc,
        )

    return "unknown"


def generate_scorecard(state: dict, output_path: str | Path) -> Path:
    """Render a landscape scorecard PNG from scan state. Returns the output path."""
    image_mod = importlib.import_module("PIL.Image")
    image_draw_mod = importlib.import_module("PIL.ImageDraw")
    scorecard_draw_mod = importlib.import_module("desloppify.app.output.scorecard_parts.draw")
    state_mod = importlib.import_module("desloppify.state")

    output_path = Path(output_path)

    main_score = state_mod.get_overall_score(state) or 0
    strict_score = state_mod.get_strict_score(state) or 0

    project_name = _get_project_name()
    package_version = _get_package_version()

    # Layout — landscape (wide), File health first
    active_dims = _prepare_scorecard_dimensions(state)
    row_count = len(active_dims)
    row_h = _s(20)
    width = _s(780)
    divider_x = _s(260)
    frame_inset = _s(5)

    cols = 2
    rows_per_col = (row_count + cols - 1) // cols
    table_content_h = _s(14) + _s(4) + _s(6) + rows_per_col * row_h
    content_h = max(table_content_h + _s(28), _s(150))
    height = _s(12) + content_h

    img = image_mod.new("RGB", (width, height), _BG)
    draw = image_draw_mod.Draw(img)

    # Double frame
    draw.rectangle((0, 0, width - 1, height - 1), outline=_FRAME, width=_s(2))
    draw.rectangle(
        (frame_inset, frame_inset, width - frame_inset - 1, height - frame_inset - 1),
        outline=_BORDER,
        width=1,
    )

    content_top = frame_inset + _s(1)
    content_bot = height - frame_inset - _s(1)
    content_mid_y = (content_top + content_bot) // 2

    # Left panel: title + score + project name
    scorecard_draw_mod.draw_left_panel(
        draw,
        main_score,
        strict_score,
        project_name,
        package_version,
        lp_left=frame_inset + _s(11),
        lp_right=divider_x - _s(11),
        lp_top=content_top + _s(4),
        lp_bot=content_bot - _s(4),
    )

    # Vertical divider with ornament
    scorecard_draw_mod._draw_vert_rule_with_ornament(
        draw,
        divider_x,
        content_top + _s(12),
        content_bot - _s(12),
        content_mid_y,
        _BORDER,
        _ACCENT,
    )

    # Right panel: dimension table
    scorecard_draw_mod.draw_right_panel(
        draw,
        active_dims,
        row_h,
        table_x1=divider_x + _s(11),
        table_x2=width - frame_inset - _s(11),
        table_top=content_top + _s(4),
        table_bot=content_bot - _s(4),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG", optimize=True)
    return output_path


def get_badge_config(args, config: dict | None = None) -> tuple[Path | None, bool]:
    """Resolve badge output path and whether badge generation is disabled.

    Returns (output_path, disabled). Checks CLI args, then config, then env vars.
    """
    cfg = config or {}
    disabled = getattr(args, "no_badge", False)
    if not disabled:
        disabled = not cfg.get("generate_scorecard", True)
    if not disabled:
        disabled = os.environ.get("DESLOPPIFY_NO_BADGE", "").lower() in (
            "1",
            "true",
            "yes",
        )
    if disabled:
        return None, True

    path_str = (
        getattr(args, "badge_path", None)
        or cfg.get("badge_path")
        or os.environ.get("DESLOPPIFY_BADGE_PATH", "assets/scorecard.png")
    )
    path = Path(path_str)
    # On Windows, "/tmp/foo.png" is root-anchored but drive-relative.
    # Treat any rooted path as user-intended absolute-like input.
    is_root_anchored = bool(path.root)
    if not path.is_absolute() and not is_root_anchored:
        path = PROJECT_ROOT / path
    return path, False


def _scorecard_ignore_warning(state: dict) -> str | None:
    """Return an ignore-suppression warning line for scorecard context."""
    info = state.get("ignore_integrity", {}) if isinstance(state, dict) else {}
    if not isinstance(info, dict):
        return None
    ignored = int(info.get("ignored", 0) or 0)
    if ignored <= 0:
        return None

    suppressed_pct = float(info.get("suppressed_pct", 0.0) or 0.0)
    rounded = round(suppressed_pct)
    level = "high" if suppressed_pct >= 50 else "moderate"
    return (
        f"Ignore suppression is {rounded}% ({level}) "
        f"across {ignored} findings."
    )


__all__ = [
    "_ACCENT",
    "_BG",
    "_BG_ROW_ALT",
    "_BG_SCORE",
    "_BG_TABLE",
    "_BORDER",
    "_DIM",
    "_FRAME",
    "_SCALE",
    "_TEXT",
    "_collapse_elegance_dimensions",
    "_fmt_score",
    "_get_package_version",
    "_get_project_name",
    "_limit_scorecard_dimensions",
    "_load_font",
    "_prepare_scorecard_dimensions",
    "_resolve_scorecard_lang",
    "_s",
    "_scorecard_ignore_warning",
    "_score_color",
    "generate_scorecard",
    "get_badge_config",
    "prepare_scorecard_dimensions",
]
