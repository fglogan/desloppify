# AGENTS.md — Guidelines for AI Coding Agents

This file contains build commands, test commands, and code style guidelines
for AI agents (Claude, Copilot, Cursor, etc.) working in this repository.

## Project Overview

**desloppify** is a Python 3.11+ CLI tool that detects and reports "slop"
(AI-generated boilerplate, filler, and low-quality patterns) in codebases.
It supports 28 language plugins and uses a tiered detection/scoring engine.

## Build & Environment

```bash
# Install in development mode (editable, with all optional deps)
pip install -e ".[full,dev]"

# Install minimal (no optional language support)
pip install -e ".[dev]"
```

Build system: **setuptools** via `pyproject.toml`. There is no compiled step;
the project is pure Python.

## Running Tests

```bash
# Run the full test suite
make test
# or directly:
pytest

# Run a single test file
pytest desloppify/tests/scoring/test_scoring.py

# Run a single test by name
pytest -k "test_confidence_enum"

# Run tests with verbose output
pytest -v

# Run only core tests (excludes language plugin tests)
pytest desloppify/tests/

# Run language-specific tests
pytest desloppify/languages/python/tests/
```

Test locations:
- `desloppify/tests/` — core tests (CI, detectors, scoring, state, etc.)
- `desloppify/languages/<lang>/tests/` — per-language plugin tests

## Linting & Type Checking

```bash
# Lint (ruff)
make lint
# or directly:
ruff check .

# Auto-fix lint issues
ruff check --fix .

# Type check (mypy) — only checks files listed in pyproject.toml
make typecheck
# or directly:
mypy

# Architecture contracts (import-linter)
make arch-contracts
# or directly:
lint-imports --config .github/importlinter.ini

# Run all CI gates locally
make ci
```

### Ruff Configuration

Defined in `pyproject.toml`:
- Rules enabled: `E`, `F`, `I` (isort), `B` (bugbear), `UP` (pyupgrade)
- Ignored: `E501` (line length not enforced by linter)
- Line length: 88
- Target: Python 3.11

### Mypy Configuration

Defined in `pyproject.toml`:
- `strict_optional = true`
- `ignore_missing_imports = true`
- Only specific files are checked (see `[[tool.mypy.overrides]]` sections)

### Architecture Contracts

Defined in `.github/importlinter.ini`:
- Runtime code (`desloppify.**`) must NOT import from test modules
- Enforced by `lint-imports` in CI

## Code Style Guidelines

### Imports

- Always include `from __future__ import annotations` as the first import
- Order: stdlib, third-party, local (enforced by ruff's `I` rule)
- Use absolute imports for cross-module references
- Use relative imports only within the same subpackage

### Module Structure

- Define `__all__` at module level to declare public API
- Prefix internal subpackages/modules with `_` (e.g., `engine/_state/`)
- Use facade modules to re-export from internal subpackages:
  ```python
  # state.py — public facade
  from desloppify.engine._state.schema import StateModel, StateStats
  __all__ = ["StateModel", "StateStats"]
  ```

### Types & Data Modeling

- **TypedDict** for state/data transfer objects (`Finding`, `StateModel`, `StateStats`)
- **Frozen dataclasses** (`@dataclass(frozen=True, slots=True)`) for metadata
  records (`DetectorMeta`, `ConfigKey`, `Concern`)
- **StrEnum** for string enumerations (`Confidence`, `Status`)
- **IntEnum** for numeric enumerations (`Tier`)
- Never use plain dicts where a TypedDict exists
- Never use mutable dataclasses where frozen ones are used

### Naming Conventions

| Element       | Convention       | Example                    |
|---------------|------------------|----------------------------|
| Files/modules | snake_case       | `fallbacks.py`             |
| Functions     | snake_case       | `load_state_model()`       |
| Variables     | snake_case       | `finding_count`            |
| Classes       | PascalCase       | `DetectorMeta`             |
| Constants     | UPPER_SNAKE_CASE | `DEFAULT_THRESHOLD`        |
| Internal funcs| `_`-prefixed     | `_merge_findings()`        |
| TypedDict keys| snake_case       | `total_findings`           |

### Error Handling

- Use `logging.getLogger(__name__)` per module — never use the root logger
- Non-fatal errors: call `log_best_effort_failure()` from `desloppify.core.fallbacks`
- User-facing messages: use `print_error()` or `warn_best_effort()`
- Do not raise exceptions for recoverable/best-effort operations
- Let fatal errors propagate naturally; do not catch-and-ignore

### Test Conventions

- Use plain functions and classes (no `unittest.TestCase`)
- Test files: `test_<module>.py`
- Test functions: `test_<behavior>()`
- Use `_make_finding()` factory helpers to build test data
- Use the `set_project_root` fixture for tests needing `RuntimeContext`:
  ```python
  def test_something(set_project_root, tmp_path):
      set_project_root(tmp_path)
      # ... test code using RuntimeContext
  ```
- Shared fixtures live in `desloppify/conftest.py`
- Do not import from test modules in runtime code (architecture contract)

### State Directory

- Project state lives in `.desloppify/` (gitignored)
- Config file: `.desloppify/config.json` (JSON, not TOML)

### Optional Dependencies

Some features require extras. Guard imports accordingly:
- `tree-sitter-language-pack` — extra: `treesitter`
- `bandit` — extra: `python-security`
- `Pillow` — extra: `scorecard`
- All of the above — extra: `full`

## CI Pipeline

The GitHub Actions CI (`.github/workflows/ci.yml`) runs these jobs:
1. `lint` — ruff check
2. `typecheck` — mypy
3. `arch-contracts` — import-linter
4. `ci-contracts` — `pytest desloppify/tests/ci/`
5. `tests-core` — core test suite
6. `tests-full` — full suite with all extras installed
7. `package-smoke` — build and install the package

Run `make ci` locally to approximate the full pipeline before pushing.
