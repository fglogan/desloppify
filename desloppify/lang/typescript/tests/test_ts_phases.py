"""Tests for TypeScript phase runners."""

from __future__ import annotations

from pathlib import Path

import desloppify.lang.typescript.phases as phases


class _FakeLang:
    large_threshold = 777
    complexity_threshold = 33
    file_finder = staticmethod(lambda _path: [])
    _complexity_map = {}
    _props_threshold = 0
    _zone_map = None


def test_phase_structural_uses_lang_thresholds(monkeypatch, tmp_path: Path):
    """Structural phase should honor language-configured thresholds."""
    captured: dict[str, int] = {}

    def _fake_detect_large(path, *, file_finder, threshold=500):
        captured["large_threshold"] = threshold
        return [], 0

    def _fake_detect_complexity(path, *, signals, file_finder, threshold=15):
        captured["complexity_threshold"] = threshold
        return [], 0

    monkeypatch.setattr("desloppify.detectors.large.detect_large_files", _fake_detect_large)
    monkeypatch.setattr("desloppify.detectors.complexity.detect_complexity", _fake_detect_complexity)
    monkeypatch.setattr("desloppify.detectors.gods.detect_gods", lambda *a, **k: ([], 0))
    monkeypatch.setattr("desloppify.detectors.flat_dirs.detect_flat_dirs", lambda *a, **k: ([], 0))
    monkeypatch.setattr("desloppify.lang.typescript.extractors.extract_ts_components", lambda _p: [])
    monkeypatch.setattr(
        "desloppify.lang.typescript.extractors.detect_passthrough_components",
        lambda _p: [],
    )
    monkeypatch.setattr("desloppify.lang.typescript.detectors.concerns.detect_mixed_concerns", lambda _p: ([], 0))
    monkeypatch.setattr(
        "desloppify.lang.typescript.detectors.props.detect_prop_interface_bloat",
        lambda _p, threshold=14: ([], 0),
    )

    findings, potentials = phases._phase_structural(tmp_path, _FakeLang())

    assert findings == []
    assert potentials["structural"] == 0
    assert captured["large_threshold"] == 777
    assert captured["complexity_threshold"] == 33


def test_ts_phase_helper_computations():
    """Cover TypeScript helper computations with direct behavioral assertions."""
    rich_content = (
        "const {a, b, c, d, e, f, g, h, i} = props;\n"
        "export type A = string;\n"
        "export type B = number;\n"
        "export interface C {}\n"
        "export type D = boolean;\n"
    )
    lines = rich_content.splitlines()

    destruct = phases._compute_ts_destructure_props(rich_content, lines)
    inline_types = phases._compute_ts_inline_types(rich_content, lines)
    no_destruct = phases._compute_ts_destructure_props("const x = 1;\n", ["const x = 1;"])
    no_inline = phases._compute_ts_inline_types("export type A = string;\n", ["export type A = string;"])

    assert destruct is not None
    assert destruct[0] == 9
    assert "props" in destruct[1]
    assert inline_types is not None
    assert inline_types[0] == 4
    assert "inline types" in inline_types[1]
    assert no_destruct is None
    assert no_inline is None
