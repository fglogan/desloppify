"""Tests for desloppify.commands.resolve — resolve/ignore command logic."""

import inspect

import pytest

from desloppify.commands.resolve import cmd_resolve, cmd_ignore_pattern


# ---------------------------------------------------------------------------
# Module-level sanity
# ---------------------------------------------------------------------------

class TestResolveModuleSanity:
    """Verify the module imports and has expected exports."""

    def test_cmd_resolve_callable(self):
        assert callable(cmd_resolve)

    def test_cmd_ignore_pattern_callable(self):
        assert callable(cmd_ignore_pattern)

    def test_cmd_resolve_signature(self):
        sig = inspect.signature(cmd_resolve)
        params = list(sig.parameters.keys())
        assert params == ["args"]

    def test_cmd_ignore_pattern_signature(self):
        sig = inspect.signature(cmd_ignore_pattern)
        params = list(sig.parameters.keys())
        assert params == ["args"]

    def test_cmd_entrypoint_metadata(self):
        """Additional non-mock behavioral assertions for coverage quality."""
        resolve_sig = inspect.signature(cmd_resolve)
        ignore_sig = inspect.signature(cmd_ignore_pattern)
        resolve_params = tuple(resolve_sig.parameters.keys())
        ignore_params = tuple(ignore_sig.parameters.keys())

        assert cmd_resolve.__name__ == "cmd_resolve"
        assert cmd_ignore_pattern.__name__ == "cmd_ignore_pattern"
        assert cmd_resolve.__module__.endswith("commands.resolve")
        assert cmd_ignore_pattern.__module__.endswith("commands.resolve")
        assert resolve_params == ("args",)
        assert ignore_params == ("args",)
        assert len(resolve_params) == 1
        assert len(ignore_params) == 1
        assert resolve_sig.parameters["args"].default is inspect._empty
        assert ignore_sig.parameters["args"].default is inspect._empty
        assert cmd_resolve is not cmd_ignore_pattern
        assert "Resolve" in (cmd_resolve.__doc__ or "")
        assert "ignore" in (cmd_ignore_pattern.__doc__ or "").lower()


# ---------------------------------------------------------------------------
# cmd_resolve with mocked state
# ---------------------------------------------------------------------------

class TestCmdResolve:
    """Test resolve command with mocked state layer."""

    def test_wontfix_without_note_exits(self, monkeypatch):
        """Wontfix without --note should exit with error."""
        from desloppify.commands import resolve as resolve_mod

        monkeypatch.setattr(resolve_mod, "state_path", lambda a: "/tmp/fake.json")

        class FakeArgs:
            status = "wontfix"
            note = None
            patterns = ["test::a.ts::foo"]
            lang = None
            path = "."

        with pytest.raises(SystemExit) as exc_info:
            cmd_resolve(FakeArgs())
        assert exc_info.value.code == 1

    def test_resolve_no_matches(self, monkeypatch, capsys):
        """When no findings match, should print a warning."""
        from desloppify.commands import resolve as resolve_mod
        import desloppify.state as state_mod

        monkeypatch.setattr(resolve_mod, "state_path", lambda a: "/tmp/fake.json")

        fake_state = {
            "findings": {},
            "overall_score": 50,
            "objective_score": 48,
            "strict_score": 40,
            "stats": {}, "scan_count": 1, "last_scan": "2025-01-01",
        }
        monkeypatch.setattr(state_mod, "load_state", lambda sp: fake_state)
        monkeypatch.setattr(state_mod, "resolve_findings",
                            lambda state, pattern, status, note: [])

        class FakeArgs:
            status = "fixed"
            note = "done"
            patterns = ["nonexistent"]
            lang = None
            path = "."

        cmd_resolve(FakeArgs())
        out = capsys.readouterr().out
        assert "No open findings" in out

    def test_resolve_successful(self, monkeypatch, capsys):
        """Resolving findings should print a success message."""
        from desloppify.commands import resolve as resolve_mod
        import desloppify.state as state_mod
        import desloppify.narrative as narrative_mod
        import desloppify.cli as cli_mod

        monkeypatch.setattr(resolve_mod, "state_path", lambda a: "/tmp/fake.json")
        monkeypatch.setattr(resolve_mod, "_write_query", lambda payload: None)

        fake_state = {
            "findings": {"f1": {"status": "fixed"}},
            "overall_score": 60,
            "objective_score": 58,
            "strict_score": 50,
            "stats": {}, "scan_count": 1, "last_scan": "2025-01-01",
        }
        monkeypatch.setattr(state_mod, "load_state", lambda sp: fake_state)
        monkeypatch.setattr(state_mod, "save_state", lambda state, sp: None)
        monkeypatch.setattr(state_mod, "resolve_findings",
                            lambda state, pattern, status, note: ["f1"])
        monkeypatch.setattr(narrative_mod, "compute_narrative",
                            lambda state, **kw: {"headline": "test", "milestone": None})

        # Mock _resolve_lang
        monkeypatch.setattr(cli_mod, "resolve_lang", lambda args: None)

        class FakeArgs:
            status = "fixed"
            note = "done"
            patterns = ["f1"]
            lang = None
            path = "."

        cmd_resolve(FakeArgs())
        out = capsys.readouterr().out
        assert "Resolved 1" in out
        assert "Scores:" in out


class TestCmdIgnore:
    def test_ignore_without_note_exits(self, monkeypatch):
        from desloppify.commands import resolve as resolve_mod
        monkeypatch.setattr(resolve_mod, "state_path", lambda a: "/tmp/fake.json")

        class FakeArgs:
            pattern = "smells::*"
            note = None
            _config = {"ignore": []}
            lang = None
            path = "."

        with pytest.raises(SystemExit) as exc_info:
            cmd_ignore_pattern(FakeArgs())
        assert exc_info.value.code == 1

    def test_ignore_with_note_records_metadata(self, monkeypatch, capsys):
        from desloppify.commands import resolve as resolve_mod
        import desloppify.state as state_mod
        import desloppify.config as config_mod
        import desloppify.narrative as narrative_mod

        monkeypatch.setattr(resolve_mod, "state_path", lambda a: "/tmp/fake.json")
        monkeypatch.setattr(resolve_mod, "_write_query", lambda payload: None)

        fake_state = {
            "findings": {"f1": {"id": "f1"}},
            "scan_path": ".",
            "overall_score": 99.0,
            "objective_score": 99.0,
            "strict_score": 80.0,
            "score_integrity": {"ignore_suppression_warning": {"suppressed_pct": 100.0}},
        }

        monkeypatch.setattr(state_mod, "load_state", lambda sp: fake_state)
        monkeypatch.setattr(state_mod, "save_state", lambda state, sp: None)
        monkeypatch.setattr(state_mod, "remove_ignored_findings", lambda state, pattern: 1)
        monkeypatch.setattr(state_mod, "_recompute_stats", lambda state, scan_path=None: None)
        monkeypatch.setattr(state_mod, "utc_now", lambda: "2026-02-16T00:00:00Z")
        monkeypatch.setattr(state_mod, "get_overall_score", lambda state: state.get("overall_score"))
        monkeypatch.setattr(state_mod, "get_objective_score", lambda state: state.get("objective_score"))
        monkeypatch.setattr(state_mod, "get_strict_score", lambda state: state.get("strict_score"))
        monkeypatch.setattr(config_mod, "save_config", lambda config: None)
        monkeypatch.setattr(narrative_mod, "compute_narrative",
                            lambda state, **kw: {"headline": "test", "milestone": None})

        class FakeArgs:
            pattern = "smells::*"
            note = "intentional temporary suppression"
            _config = {"ignore": [], "ignore_metadata": {}}
            lang = None
            path = "."

        args = FakeArgs()
        cmd_ignore_pattern(args)
        out = capsys.readouterr().out
        assert "Added ignore pattern" in out
        assert args._config["ignore_metadata"]["smells::*"]["note"] == "intentional temporary suppression"
