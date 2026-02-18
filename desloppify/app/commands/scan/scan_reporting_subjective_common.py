"""Common helpers for subjective scan reporting."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubjectiveFollowup:
    threshold: float
    threshold_label: str
    low_assessed: list[dict]
    rendered: str
    command: str
    integrity_notice: dict[str, object] | None
    integrity_lines: list[tuple[str, str]]


def flatten_cli_keys(items: list[dict], *, max_items: int = 3) -> str:
    """Flatten CLI keys across up to max_items subjective entries, preserving order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items[:max_items]:
        for key in item.get("cli_keys", []):
            if key in seen:
                continue
            ordered.append(key)
            seen.add(key)
    return ",".join(ordered)


def render_subjective_scores(entries: list[dict], *, max_items: int = 3) -> str:
    return ", ".join(
        f"{entry.get('name', 'Subjective')} {float(entry.get('strict', entry.get('score', 100.0))):.1f}%"
        for entry in entries[:max_items]
    )


def render_subjective_names(entries: list[dict], *, max_names: int = 3) -> str:
    count = len(entries)
    names = ", ".join(
        str(entry.get("name", "Subjective")) for entry in entries[:max_names]
    )
    if count > max_names:
        names = f"{names}, +{count - max_names} more"
    return names


def coerce_notice_count(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return 0
    return 0


def coerce_str_keys(value: object) -> list[str]:
    if not isinstance(value, list | tuple | set):
        return []
    return [key for key in value if isinstance(key, str) and key]


def subjective_rerun_command(
    items: list[dict],
    *,
    max_items: int = 5,
    refresh: bool = True,
) -> str:
    dim_keys = flatten_cli_keys(items, max_items=max_items)
    if not dim_keys:
        return (
            "`desloppify review --prepare --holistic --refresh && desloppify scan`"
            if refresh
            else "`desloppify review --prepare --holistic && desloppify scan`"
        )

    prepare_parts = ["desloppify", "review", "--prepare"]
    if refresh:
        prepare_parts.append("--refresh")
    prepare_parts.extend(["--dimensions", dim_keys])
    return f"`{' '.join(prepare_parts)} && desloppify scan`"


__all__ = [
    "SubjectiveFollowup",
    "coerce_notice_count",
    "coerce_str_keys",
    "flatten_cli_keys",
    "render_subjective_names",
    "render_subjective_scores",
    "subjective_rerun_command",
]
