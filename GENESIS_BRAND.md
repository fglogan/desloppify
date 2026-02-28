# Genesis Deslop -- Brand Specification

> Canonical reference for rebranding `desloppify` (Python) as `genesis-deslop` (Rust).
> All naming, color, file format, and quality decisions flow from this document.

---

## 1. Product Identity

| Field | Value |
|-------|-------|
| Genesis Product Name | `genesis-deslop` |
| Binary Name | `gdeslop` |
| Full Name | Genesis Deslop -- Codebase Quality Intelligence |
| Tagline | Mechanical precision. Subjective depth. Zero slop. |
| Initial Version | 1.0.0 |
| Origin | Clean Rust rewrite of `desloppify` v0.8.0 (Python) |

Version 1.0.0 is a fresh start. The Rust implementation is not a continuation of
the Python version's semver history. The version number reflects the maturity of
the new codebase, not the feature parity with the old one.

---

## 2. Naming Conventions

### 2.1 Crate and Module Mapping

Every Python module maps to a specific Rust crate or module path. Crate names
use hyphens (`genesis-deslop-core`). Module paths use underscores
(`genesis_deslop_core`). This follows standard Rust convention.

| Python Module | Rust Crate | Rust Module Path |
|---|---|---|
| `desloppify.core` | `genesis-deslop-core` | `genesis_deslop_core` |
| `desloppify.engine` | `genesis-deslop-engine` | `genesis_deslop_engine` |
| `desloppify.engine.detectors` | `genesis-deslop-engine` | `engine::detectors` |
| `desloppify.engine._scoring` | `genesis-deslop-engine` | `engine::scoring` |
| `desloppify.engine._state` | `genesis-deslop-engine` | `engine::state` |
| `desloppify.engine._work_queue` | `genesis-deslop-engine` | `engine::work_queue` |
| `desloppify.engine._plan` | `genesis-deslop-engine` | `engine::plan` |
| `desloppify.intelligence` | `genesis-deslop-intel` | `genesis_deslop_intel` |
| `desloppify.languages` | `genesis-deslop-lang` | `genesis_deslop_lang` |
| `desloppify.app` | `genesis-deslop-cli` | `genesis_deslop_cli` |

### 2.2 Workspace Layout

```
genesis-deslop/
  Cargo.toml              # workspace root
  crates/
    genesis-deslop/       # facade crate (lib, re-exports public API)
    genesis-deslop-core/
    genesis-deslop-engine/
    genesis-deslop-intel/
    genesis-deslop-lang/
    genesis-deslop-cli/   # binary crate, produces `gdeslop`
```

### 2.3 General Rules

- Crate names: `genesis-deslop-{component}` (hyphenated).
- Module names: `genesis_deslop_{component}` (underscored, automatic from crate name).
- Public types: PascalCase. No `Deslop` prefix on types within `genesis-deslop-*` crates
  (the crate name already namespaces them).
- Constants: `SCREAMING_SNAKE_CASE`, centralized in a `constants` module per crate.
- Feature flags: lowercase kebab-case (`tree-sitter`, `scorecard-png`).

---

## 3. CLI Identity

### 3.1 Invocation

```
gdeslop <subcommand> [options] [path]
```

Replaces the Python-era `deslop` command.

### 3.2 Subcommands

All subcommands from the Python version are preserved with identical names and
semantics:

```
scan            Run full codebase analysis
status          Show current analysis state
show            Display detailed file/module scores
next            Suggest the next file to improve
ignore          Mark files as ignored
exclude         Exclude paths from analysis
fix             Apply automated fixes
plan            Generate or display improvement plan
detect          Run mechanical detectors only
tree            Output file tree with scores
viz             Generate visual scorecard / treemap
move            Reclassify files between zones
zone            Manage quality zones
review          Run subjective LLM review
config          Manage configuration
dev             Developer/debug utilities
update-skill    Update LLM skill definitions
langs           List supported languages and their detectors
```

Flag names and short forms are 1:1 compatible with the Python CLI unless a
conflict with Rust-standard conventions is documented below.

### 3.3 Help Text Style

- Clean, professional, minimal.
- No emoji anywhere in help output, error messages, or log lines.
- Monochrome by default. Color output enabled via `--color=auto|always|never`
  (default: `auto`, which enables color only when stdout is a TTY).
- Built with `clap` derive macros. Help text comes from doc comments on
  command structs.

### 3.4 Error Messages

Structured errors with unique codes:

```
error[GD-1001]: file not found
  --> src/lib.rs
  = note: the path was resolved relative to the workspace root
```

Error code ranges:

| Range | Category |
|-------|----------|
| GD-1xxx | I/O and filesystem |
| GD-2xxx | Configuration and parsing |
| GD-3xxx | Detector execution |
| GD-4xxx | LLM / intelligence layer |
| GD-5xxx | Scoring and aggregation |
| GD-6xxx | State management |
| GD-7xxx | CLI argument validation |

### 3.5 State and Config Paths

| Purpose | Path | Format |
|---------|------|--------|
| State directory | `.genesis-deslop/` | -- |
| State file | `.genesis-deslop/state.json` | JSON |
| Plan file | `.genesis-deslop/plan.json` | JSON |
| Query output | `.genesis-deslop/query.json` | JSON |
| Config file | `genesis-deslop.toml` | TOML |

The state directory replaces `.desloppify/`. The config file replaces
`desloppify.toml` and upgrades from the implicit JSON-style format to TOML.

---

## 4. Color Palette

### 4.1 Terminal Colors (ANSI 256)

All terminal output uses standard ANSI color codes. No 24-bit / truecolor
sequences -- maximum compatibility with minimal terminals.

| Role | ANSI Code | Appearance |
|------|-----------|------------|
| Primary text | Default FG | Terminal default |
| Success / Good | 2 | Green |
| Warning / Moderate | 3 | Yellow |
| Error / Critical | 1 | Red |
| Info / Accent | 6 | Cyan |
| Muted / Secondary | 8 | Gray |

Score-dependent coloring in terminal output:

| Score Range | Color | ANSI |
|-------------|-------|------|
| >= 90 (excellent) | Bold Green | `\e[1;32m` |
| 70--89 (good) | Green | `\e[32m` |
| 50--69 (warning) | Yellow | `\e[33m` |
| < 50 (poor) | Red | `\e[31m` |

### 4.2 Scorecard and Export Colors (RGB)

Used in PNG scorecards, HTML treemaps, and any rendered visual output. Derived
from the existing warm cream/brown scorecard theme, elevated for Genesis branding.

| Role | Hex | RGB | Usage |
|------|-----|-----|-------|
| Background | `#F7F0E4` | (247, 240, 228) | Scorecard / treemap background |
| Primary text | `#3A3026` | (58, 48, 38) | Headings, labels, body text |
| Score excellent | `#5A7A5A` | (90, 122, 90) | Scores >= 90 |
| Score good | `#6B8B4A` | (107, 139, 74) | Scores 70--89 |
| Score warning | `#B8A040` | (184, 160, 64) | Scores 50--69 |
| Score poor | `#A05050` | (160, 80, 80) | Scores < 50 |
| Accent | `#8B7355` | (139, 115, 85) | Borders, dividers, ornaments |
| Diamond ornaments | -- | -- | Score-dependent coloring (match score tier) |

These values are defined as constants in `genesis-deslop-core::constants` and
must not be hardcoded elsewhere.

---

## 5. File Format Specifications

### 5.1 Output Files

| File | Path | Format | Notes |
|------|------|--------|-------|
| State | `.genesis-deslop/state.json` | JSON | Cross-tool compatibility |
| Plan | `.genesis-deslop/plan.json` | JSON | Improvement plan |
| Query | `.genesis-deslop/query.json` | JSON | Agent consumption |
| Scorecard | `genesis-deslop-scorecard.png` | PNG | Visual quality report |
| Treemap | `genesis-deslop-treemap.html` | HTML | Interactive file map |
| Tree text | `genesis-deslop-tree.txt` | Plain text | ASCII tree with scores |

### 5.2 Configuration

The project-level config file is `genesis-deslop.toml` at the workspace root.

```toml
[scan]
exclude = ["target/", "vendor/", ".git/"]
parallelism = 0  # 0 = auto-detect CPU count

[scoring]
mechanical_weight = 0.6
subjective_weight = 0.4

[review]
model = "default"
batch_size = 10

[output]
color = "auto"        # auto | always | never
scorecard_path = "genesis-deslop-scorecard.png"
```

### 5.3 JSON Schema Versioning

All JSON state/plan files include a top-level `"version"` field:

```json
{
  "version": "1.0.0",
  "tool": "genesis-deslop",
  ...
}
```

---

## 6. Genesis Ecosystem Integration

### 6.1 Crate Structure

| Crate | Type | Purpose |
|-------|------|---------|
| `genesis-deslop` | lib | Facade. Re-exports public API for embedding. |
| `genesis-deslop-core` | lib | Shared types, constants, scoring primitives. |
| `genesis-deslop-engine` | lib | Detectors, scoring pipeline, state, work queue, plan. |
| `genesis-deslop-intel` | lib | LLM integration, subjective review, prompt management. |
| `genesis-deslop-lang` | lib | Language definitions, file classification, tree-sitter bindings. |
| `genesis-deslop-cli` | bin | CLI binary (`gdeslop`). Argument parsing, output formatting. |

### 6.2 Feature Flags

| Flag | Default | Description |
|------|---------|-------------|
| `tree-sitter` | on | Syntax-aware detection via tree-sitter grammars |
| `scorecard-png` | on | PNG scorecard rendering (pulls in image deps) |
| `review-batch` | on | Batch LLM review support |
| `full-languages` | off | All 30+ language grammars (large compile-time cost) |

### 6.3 Rust Toolchain Requirements

| Requirement | Value |
|-------------|-------|
| Edition | 2021 |
| MSRV | 1.75.0 |
| Rationale | Async fn in traits stabilized in 1.75 |

### 6.4 Key Dependencies (Expected)

| Purpose | Crate |
|---------|-------|
| CLI parsing | `clap` (derive) |
| Serialization | `serde`, `serde_json`, `toml` |
| Async runtime | `tokio` |
| HTTP (LLM calls) | `reqwest` |
| Error handling (lib) | `thiserror` |
| Error handling (bin) | `anyhow` |
| Tree-sitter | `tree-sitter`, language-specific grammar crates |
| Image rendering | `resvg` or `tiny-skia` (for scorecard PNGs) |
| Terminal color | `termcolor` or `owo-colors` |

---

## 7. Documentation Style

### 7.1 README

Follow Genesis standard format:

```
# genesis-deslop

Codebase Quality Intelligence -- mechanical precision, subjective depth.

## Install
## Quick Start
## Commands
## Configuration
## Scoring Model
## License
```

### 7.2 Code Documentation

- Public API: `///` doc comments on every public item. Include examples for
  non-trivial functions.
- Implementation: `//` comments for why, not what. No commented-out code.
- Module-level: `//!` at the top of each module file explaining purpose and
  key types.

### 7.3 Tone

- No emoji in code, docs, output, or error messages.
- Professional, concise, technical.
- Prefer active voice and imperative mood in doc comments
  ("Returns the score" not "This function returns the score").

### 7.4 Error Types

- Library crates: `thiserror`-derived error enums with structured variants.
- CLI crate: `anyhow::Result` for top-level, wrapping library errors.
- Every error variant includes an error code (`GD-xxxx`).

---

## 8. Logo

### 8.1 Terminal Banner

Displayed on `gdeslop --version` and at the top of scorecard text output:

```
+=======================================+
|   GENESIS DESLOP                      |
|   Codebase Quality Intelligence       |
|   * v1.0.0                            |
+=======================================+
```

Uses box-drawing characters (`U+2550`, `U+2551`, `U+2554`, `U+2557`, `U+255A`,
`U+255D`) and the diamond ornament (`U+25C6`). Falls back to ASCII (`=`, `|`,
`+`, `*`) when the terminal does not support Unicode.

### 8.2 Compact Form

For log output and short headers:

```
genesis-deslop v1.0.0
```

No banner, no box. One line.

---

## 9. Migration Path

### 9.1 Automatic Detection

When `gdeslop` is invoked in a directory containing `.desloppify/`, it prints:

```
note[GD-6001]: legacy state directory detected
  --> .desloppify/
  = help: run `gdeslop migrate` to import existing state
```

Analysis does not proceed until migration is performed or explicitly skipped
with `--ignore-legacy`.

### 9.2 Migration Command

```
gdeslop migrate [--dry-run] [--force]
```

Behavior:

1. Read `.desloppify/state.json` and `.desloppify/plan.json`.
2. Convert to `genesis-deslop` v1.0.0 schema.
3. Write to `.genesis-deslop/`.
4. Convert `desloppify.toml` (or JSON config) to `genesis-deslop.toml`.
5. Print summary of migrated files and any data that could not be converted.
6. Do **not** delete `.desloppify/`. The user removes it manually.

### 9.3 Scoring Compatibility

The mechanical scoring algorithms must produce identical results to Python
`desloppify` v0.8.0 for the same input. This is verified by cross-validation
tests that run both implementations on a shared fixture set and assert score
equality within a tolerance of 0.001.

### 9.4 CLI Compatibility

All subcommand names and flag names are preserved. Users can alias
`deslop` -> `gdeslop` and existing scripts will work without modification,
subject to the config file rename.

---

## 10. Quality Standards

### 10.1 Documentation

- All public types, traits, functions, and modules have Rustdoc comments.
- Every crate has a top-level `//!` module doc with purpose statement.

### 10.2 Type Requirements

All domain types must implement:

- `Debug`
- `Clone`
- `serde::Serialize`
- `serde::Deserialize`

Where semantically meaningful, also implement `PartialEq`, `Eq`, `Hash`.

### 10.3 Error Handling

- All fallible operations return `Result<T, Error>`.
- No `.unwrap()` or `.expect()` in library code. Permitted in tests and in
  CLI `main()` only where the error is immediately reported.
- No `panic!` in library code.

### 10.4 Linting

Every crate's `lib.rs` or `main.rs` includes:

```rust
#![deny(clippy::all, clippy::pedantic)]
#![allow(clippy::module_name_repetitions)]
```

Additional targeted `#[allow(...)]` is permitted with a `// Reason:` comment.

### 10.5 Testing

- Target: >80% line coverage across all crates.
- Unit tests in `#[cfg(test)]` modules within each source file.
- Integration tests in `tests/` directories per crate.
- Cross-validation tests against Python `desloppify` v0.8.0 scoring output
  in a dedicated `tests/cross-validation/` directory.

### 10.6 Safety

- No `unsafe` code unless explicitly justified in a `// SAFETY:` comment
  and approved via code review.
- All `unsafe` blocks are isolated in dedicated modules, never inline in
  business logic.

### 10.7 Constants

- All magic numbers, strings, default values, and configuration keys are
  defined as constants in a `constants` module within the relevant crate.
- No string literals for config keys, error codes, or file paths scattered
  through implementation code.

---

## Appendix A: String Replacement Reference

Quick reference for search-and-replace during migration of docs, scripts, and
CI configuration:

| Old | New |
|-----|-----|
| `desloppify` | `genesis-deslop` |
| `deslop` (CLI command) | `gdeslop` |
| `.desloppify/` | `.genesis-deslop/` |
| `desloppify.toml` | `genesis-deslop.toml` |
| `desloppify-scorecard.png` | `genesis-deslop-scorecard.png` |
| `desloppify-treemap.html` | `genesis-deslop-treemap.html` |
| `desloppify-tree.txt` | `genesis-deslop-tree.txt` |

---

*This document is the single source of truth for Genesis Deslop branding
decisions. All implementation must conform to these specifications.*
