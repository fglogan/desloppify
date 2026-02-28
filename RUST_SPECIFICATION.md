# Genesis Deslop — Rust Implementation Specification

> **Document version:** 1.0  
> **Target binary:** `gdeslop`  
> **State directory:** `.genesis-deslop/`  
> **Config file:** `genesis-deslop.toml` (TOML format)

This document is the authoritative specification for reimplementing the Python "desloppify" tool as the Rust "genesis-deslop" system. A Rust developer should be able to implement the entire system from this specification alone, without reference to the Python source.

---

## Table of Contents

1. [Workspace Structure](#1-workspace-structure)
2. [genesis-deslop-core](#2-genesis-deslop-core)
   - 2.1 [config module](#21-config-module)
   - 2.2 [enums module](#22-enums-module)
   - 2.3 [registry module](#23-registry-module)
   - 2.4 [discovery module](#24-discovery-module)
   - 2.5 [paths module](#25-paths-module)
   - 2.6 [output module](#26-output-module)
3. [genesis-deslop-engine](#3-genesis-deslop-engine)
   - 3.1 [state module](#31-state-module)
   - 3.2 [scoring module](#32-scoring-module)
   - 3.3 [detectors module](#33-detectors-module)
   - 3.4 [work_queue module](#34-work_queue-module)
   - 3.5 [plan module](#35-plan-module)
   - 3.6 [concerns module](#36-concerns-module)
   - 3.7 [policy module](#37-policy-module)
4. [genesis-deslop-lang](#4-genesis-deslop-lang)
   - 4.1 [framework module](#41-framework-module)
   - 4.2 [Plugin trait](#42-plugin-trait)
   - 4.3 [Full-depth plugins (6)](#43-full-depth-plugins)
   - 4.4 [Generic plugins (22)](#44-generic-plugins)
5. [genesis-deslop-intel](#5-genesis-deslop-intel)
   - 5.1 [review module](#51-review-module)
   - 5.2 [narrative module](#52-narrative-module)
   - 5.3 [integrity module](#53-integrity-module)
6. [genesis-deslop-cli](#6-genesis-deslop-cli)
   - 6.1 [Command structure](#61-command-structure)
   - 6.2 [Output rendering](#62-output-rendering)
7. [Feature Flags](#7-feature-flags)
8. [Dependencies](#8-dependencies)
9. [Error Types](#9-error-types)
10. [Performance Requirements](#10-performance-requirements)

---

## 1. Workspace Structure

```
genesis-deslop/
├── Cargo.toml                    # workspace root
├── crates/
│   ├── genesis-deslop-core/      # config, discovery, paths, output, registry, enums
│   ├── genesis-deslop-engine/    # detectors, scoring, state, work_queue, plan, concerns, policy
│   ├── genesis-deslop-lang/      # language framework + 28 language plugins
│   ├── genesis-deslop-intel/     # review, narrative, integrity
│   └── genesis-deslop-cli/       # clap-based CLI, commands, output rendering
└── genesis-deslop/               # facade lib crate re-exporting public APIs
```

### Crate dependency graph

```
genesis-deslop-cli
  ├── genesis-deslop-engine
  │     ├── genesis-deslop-core
  │     └── genesis-deslop-lang
  │           └── genesis-deslop-core
  ├── genesis-deslop-intel
  │     ├── genesis-deslop-core
  │     └── genesis-deslop-engine
  └── genesis-deslop-core

genesis-deslop (facade)
  ├── genesis-deslop-core (re-export)
  ├── genesis-deslop-engine (re-export)
  ├── genesis-deslop-lang (re-export)
  ├── genesis-deslop-intel (re-export)
  └── genesis-deslop-cli (re-export)
```

### Workspace Cargo.toml

```toml
[workspace]
members = [
    "crates/genesis-deslop-core",
    "crates/genesis-deslop-engine",
    "crates/genesis-deslop-lang",
    "crates/genesis-deslop-intel",
    "crates/genesis-deslop-cli",
    "genesis-deslop",
]
resolver = "2"

[workspace.package]
version = "0.1.0"
edition = "2021"
license = "MIT"

[workspace.dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
toml = "0.8"
thiserror = "2"
anyhow = "1"
clap = { version = "4", features = ["derive"] }
chrono = { version = "0.4", features = ["serde"] }
regex = "1"
sha2 = "0.10"
md-5 = "0.10"
phf = { version = "0.11", features = ["macros"] }
petgraph = "0.6"
similar = "2"
```

### Binary target

The binary is named `gdeslop` and is produced by `genesis-deslop-cli`:

```toml
# crates/genesis-deslop-cli/Cargo.toml
[[bin]]
name = "gdeslop"
path = "src/main.rs"
```

### File conventions

- **State directory:** `.genesis-deslop/` at project root
- **State file:** `.genesis-deslop/state.json`
- **Plan file:** `.genesis-deslop/plan.json`
- **Config file:** `genesis-deslop.toml` at project root
- **All JSON state files use serde_json with pretty-printing (4-space indent)**
- **All timestamps are ISO 8601 format (UTC)**

---

## 2. genesis-deslop-core

This crate contains foundational types, configuration, file discovery, path utilities, output formatting, the detector registry, and shared enumerations. It has no dependencies on other workspace crates.

### 2.1 config module

`crates/genesis-deslop-core/src/config.rs`

The configuration is loaded from `genesis-deslop.toml` (TOML format) and merged with CLI overrides.

```rust
use std::collections::HashMap;
use std::path::Path;
use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct Config {
    /// Score threshold for strict-mode pass (0-100).
    pub target_strict_score: u32,

    /// Maximum age in days before a review is considered stale and must be re-run.
    pub review_max_age_days: u32,

    /// Maximum number of files in a single review batch.
    pub review_batch_max_files: u32,

    /// Maximum age in days before holistic/subjective assessments expire.
    pub holistic_max_age_days: u32,

    /// Whether to generate a scorecard PNG after scan.
    pub generate_scorecard: bool,

    /// Output path for the scorecard PNG image.
    pub badge_path: String,

    /// Glob patterns for files to exclude from scanning entirely.
    pub exclude: Vec<String>,

    /// Finding IDs or glob patterns to suppress (mark as suppressed, not removed).
    pub ignore: Vec<String>,

    /// Metadata attached to ignored findings (arbitrary key-value).
    pub ignore_metadata: HashMap<String, serde_json::Value>,

    /// Manual zone overrides: relative path pattern -> zone name.
    pub zone_overrides: HashMap<String, String>,

    /// Explicit list of review dimension names to include. Empty = all.
    pub review_dimensions: Vec<String>,

    /// Override for large-file LOC threshold. 0 = use language default.
    pub large_files_threshold: u32,

    /// Override for props/params threshold. 0 = use language default.
    pub props_threshold: u32,

    /// Per-detector noise budget: max new findings per detector per scan
    /// before excess are suppressed. Prevents detector floods.
    pub finding_noise_budget: u32,

    /// Global noise budget across all detectors. 0 = unlimited.
    pub finding_noise_global_budget: u32,

    /// Flag set by the system when state indicates a rescan is needed
    /// (e.g., config changed, version upgraded).
    pub needs_rescan: bool,

    /// Per-language configuration overrides. Key = language name (lowercase).
    /// Values are language-specific JSON objects merged into the language plugin config.
    pub languages: HashMap<String, serde_json::Value>,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            target_strict_score: 95,
            review_max_age_days: 30,
            review_batch_max_files: 80,
            holistic_max_age_days: 30,
            generate_scorecard: true,
            badge_path: "scorecard.png".to_string(),
            exclude: Vec::new(),
            ignore: Vec::new(),
            ignore_metadata: HashMap::new(),
            zone_overrides: HashMap::new(),
            review_dimensions: Vec::new(),
            large_files_threshold: 0,
            props_threshold: 0,
            finding_noise_budget: 10,
            finding_noise_global_budget: 0,
            needs_rescan: false,
            languages: HashMap::new(),
        }
    }
}
```

#### Functions

```rust
/// Load configuration from a TOML file. Returns default config if file does not exist.
/// Returns Err only on parse failures (not missing file).
pub fn load_config(path: &Path) -> Result<Config>;

/// Merge a file-loaded config with CLI-provided overrides.
/// CLI values take precedence over file values for scalar fields.
/// Vec fields are concatenated (CLI appends to file).
/// HashMap fields are merged (CLI keys override file keys).
pub fn merge_config(file: Config, cli: Config) -> Config;
```

#### Merge semantics

| Field type | Merge behavior |
|---|---|
| Scalar (`u32`, `bool`, `String`) | CLI value wins if it differs from `Config::default()` |
| `Vec<String>` | Concatenate file + CLI (deduplicated) |
| `HashMap<K, V>` | File map extended by CLI map (CLI keys overwrite) |

---

### 2.2 enums module

`crates/genesis-deslop-core/src/enums.rs`

All shared enumerations used across the entire system. Every enum derives the standard set of traits for serialization, comparison, and use as hash keys.

```rust
use serde::{Serialize, Deserialize};

/// Confidence level of a finding. Affects its weight in scoring.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Confidence {
    High,
    Medium,
    Low,
}

impl Confidence {
    /// Numeric weight used in score calculations.
    pub fn weight(&self) -> f64 {
        match self {
            Confidence::High => 1.0,
            Confidence::Medium => 0.7,
            Confidence::Low => 0.3,
        }
    }

    /// Ordinal rank for sorting (lower = higher priority).
    pub fn rank(&self) -> u32 {
        match self {
            Confidence::High => 0,
            Confidence::Medium => 1,
            Confidence::Low => 2,
        }
    }
}

/// Lifecycle status of a finding.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Status {
    /// Active finding requiring attention.
    Open,
    /// Developer has fixed the underlying issue.
    Fixed,
    /// System determined the finding no longer applies (e.g., file deleted).
    AutoResolved,
    /// Developer explicitly chose not to fix (counts against strict score).
    Wontfix,
    /// Developer asserts this is not a real issue (counts against verified strict score).
    FalsePositive,
}

/// Effort tier for a finding. Determines prioritization and work queue ordering.
/// Repr(u8) so the discriminant can be used directly as a weight.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[repr(u8)]
pub enum Tier {
    /// Can be fixed automatically by a tool (weight 1).
    AutoFix = 1,
    /// Simple manual fix, typically < 5 minutes (weight 2).
    QuickFix = 2,
    /// Requires human judgment to resolve (weight 3).
    Judgment = 3,
    /// Significant refactoring or architectural change (weight 4).
    MajorRefactor = 4,
}

impl Tier {
    /// Numeric weight used in score calculations.
    /// Returns the discriminant value as u32.
    pub fn weight(&self) -> u32 {
        *self as u32
    }
}

/// Classification zone for a file. Determines which detectors apply
/// and how findings are weighted.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Zone {
    /// Application source code (full detection and scoring).
    Production,
    /// Test files (reduced detection, some detectors skipped).
    Test,
    /// Configuration files (minimal detection).
    Config,
    /// Auto-generated code (most detectors skipped).
    Generated,
    /// Build/deploy scripts (reduced detection).
    Script,
    /// Third-party vendored code (excluded from scoring).
    Vendor,
}
```

---

### 2.3 registry module

`crates/genesis-deslop-core/src/registry.rs`

The detector registry is a compile-time map of all known detectors and their metadata. This is the single source of truth for detector properties across the system.

```rust
use phf::phf_map;

/// Metadata for a single detector. All fields are static strings
/// to enable compile-time construction via phf.
#[derive(Debug, Clone)]
pub struct DetectorMeta {
    /// Internal identifier (snake_case, e.g., "duplicate").
    pub name: &'static str,

    /// Human-readable display name (e.g., "Duplicate Code").
    pub display: &'static str,

    /// Scoring dimension this detector contributes to
    /// (e.g., "duplication", "code_quality", "security").
    pub dimension: &'static str,

    /// Action type for work queue prioritization.
    /// One of: "auto_fix", "reorganize", "refactor", "manual_fix", "debt_review".
    pub action_type: &'static str,

    /// Human-readable guidance text for resolving findings from this detector.
    pub guidance: &'static str,

    /// Names of fixer modules that can auto-remediate this detector's findings.
    pub fixers: &'static [&'static str],

    /// External tool name if this detector wraps a third-party tool (e.g., "eslint", "ruff").
    pub tool: Option<&'static str>,

    /// Whether this is a structural detector (affects cross-file analysis).
    pub structural: bool,

    /// Whether findings from this detector require human judgment
    /// (cannot be auto-fixed).
    pub needs_judgment: bool,
}
```

#### DETECTORS map

The `DETECTORS` constant is a `phf::Map<&'static str, DetectorMeta>` containing all 30 detectors. The map is keyed by detector name.

```rust
pub static DETECTORS: phf::Map<&'static str, DetectorMeta> = phf_map! {
    "duplicate"       => DetectorMeta { name: "duplicate",       display: "Duplicate Code",          dimension: "duplication",          action_type: "refactor",     guidance: "Extract shared logic into a common module or utility function.", fixers: &[], tool: None, structural: false, needs_judgment: true },
    "complexity"      => DetectorMeta { name: "complexity",      display: "High Complexity",         dimension: "code_quality",         action_type: "refactor",     guidance: "Break complex functions into smaller, focused units.", fixers: &[], tool: None, structural: false, needs_judgment: true },
    "large"           => DetectorMeta { name: "large",           display: "Large Files",             dimension: "file_health",          action_type: "reorganize",   guidance: "Split large files by responsibility.", fixers: &[], tool: None, structural: true, needs_judgment: true },
    "gods"            => DetectorMeta { name: "gods",            display: "God Classes",             dimension: "file_health",          action_type: "refactor",     guidance: "Decompose into focused, single-responsibility classes.", fixers: &[], tool: None, structural: true, needs_judgment: true },
    "coupling"        => DetectorMeta { name: "coupling",        display: "High Coupling",           dimension: "file_health",          action_type: "reorganize",   guidance: "Reduce dependencies between modules.", fixers: &[], tool: None, structural: true, needs_judgment: true },
    "cycle"           => DetectorMeta { name: "cycle",           display: "Circular Dependencies",   dimension: "file_health",          action_type: "reorganize",   guidance: "Break cycles by introducing interfaces or restructuring.", fixers: &[], tool: None, structural: true, needs_judgment: true },
    "unused"          => DetectorMeta { name: "unused",          display: "Unused Exports",          dimension: "file_health",          action_type: "auto_fix",     guidance: "Remove dead exports to reduce surface area.", fixers: &["remove_unused"], tool: None, structural: false, needs_judgment: false },
    "orphaned"        => DetectorMeta { name: "orphaned",        display: "Orphaned Files",          dimension: "file_health",          action_type: "reorganize",   guidance: "Delete or integrate orphaned files.", fixers: &[], tool: None, structural: true, needs_judgment: true },
    "security"        => DetectorMeta { name: "security",        display: "Security Issues",         dimension: "security",             action_type: "manual_fix",   guidance: "Address security vulnerabilities following OWASP guidelines.", fixers: &[], tool: None, structural: false, needs_judgment: true },
    "naming"          => DetectorMeta { name: "naming",          display: "Naming Conventions",      dimension: "code_quality",         action_type: "auto_fix",     guidance: "Rename to follow project conventions.", fixers: &["rename_symbol"], tool: None, structural: false, needs_judgment: false },
    "smells"          => DetectorMeta { name: "smells",          display: "Code Smells",             dimension: "code_quality",         action_type: "refactor",     guidance: "Refactor to eliminate identified code smells.", fixers: &[], tool: None, structural: false, needs_judgment: true },
    "test_coverage"   => DetectorMeta { name: "test_coverage",   display: "Test Coverage Gaps",      dimension: "test_health",          action_type: "manual_fix",   guidance: "Add tests for uncovered code paths.", fixers: &[], tool: None, structural: false, needs_judgment: true },
    "logs"            => DetectorMeta { name: "logs",            display: "Logging Issues",          dimension: "code_quality",         action_type: "auto_fix",     guidance: "Fix logging patterns (remove console.log, add structured logging).", fixers: &["fix_logs"], tool: None, structural: false, needs_judgment: false },
    "interface"       => DetectorMeta { name: "interface",       display: "Interface Issues",        dimension: "code_quality",         action_type: "refactor",     guidance: "Simplify interfaces: reduce parameters, extract option objects.", fixers: &[], tool: None, structural: false, needs_judgment: true },
    "concerns"        => DetectorMeta { name: "concerns",        display: "Design Concerns",         dimension: "code_quality",         action_type: "debt_review",  guidance: "Review flagged design concerns with the team.", fixers: &[], tool: None, structural: true, needs_judgment: true },
    // Subjective / review-based detectors:
    "high_level_elegance"    => DetectorMeta { name: "high_level_elegance",    display: "High-Level Elegance",     dimension: "high_level_elegance",    action_type: "debt_review", guidance: "Improve architectural cohesion and module boundaries.",    fixers: &[], tool: None, structural: true, needs_judgment: true },
    "mid_level_elegance"     => DetectorMeta { name: "mid_level_elegance",     display: "Mid-Level Elegance",      dimension: "mid_level_elegance",     action_type: "debt_review", guidance: "Improve class/module internal design.",                   fixers: &[], tool: None, structural: true, needs_judgment: true },
    "low_level_elegance"     => DetectorMeta { name: "low_level_elegance",     display: "Low-Level Elegance",      dimension: "low_level_elegance",     action_type: "debt_review", guidance: "Improve function-level implementation quality.",           fixers: &[], tool: None, structural: false, needs_judgment: true },
    "contract_coherence"     => DetectorMeta { name: "contract_coherence",     display: "Contract Coherence",      dimension: "contract_coherence",     action_type: "debt_review", guidance: "Align API contracts with usage patterns.",                fixers: &[], tool: None, structural: true, needs_judgment: true },
    "type_safety"            => DetectorMeta { name: "type_safety",            display: "Type Safety",             dimension: "type_safety",            action_type: "debt_review", guidance: "Strengthen type annotations and reduce `any` usage.",     fixers: &[], tool: None, structural: false, needs_judgment: true },
    "abstraction_fitness"    => DetectorMeta { name: "abstraction_fitness",    display: "Abstraction Fitness",     dimension: "abstraction_fitness",    action_type: "debt_review", guidance: "Right-size abstractions to match actual variation.",      fixers: &[], tool: None, structural: true, needs_judgment: true },
    "logic_clarity"          => DetectorMeta { name: "logic_clarity",          display: "Logic Clarity",           dimension: "logic_clarity",          action_type: "debt_review", guidance: "Simplify conditional logic and control flow.",            fixers: &[], tool: None, structural: false, needs_judgment: true },
    "structure_navigation"   => DetectorMeta { name: "structure_navigation",   display: "Structure Navigation",    dimension: "structure_navigation",   action_type: "debt_review", guidance: "Improve file/folder organization for discoverability.",   fixers: &[], tool: None, structural: true, needs_judgment: true },
    "error_consistency"      => DetectorMeta { name: "error_consistency",      display: "Error Consistency",       dimension: "error_consistency",      action_type: "debt_review", guidance: "Standardize error handling patterns.",                    fixers: &[], tool: None, structural: false, needs_judgment: true },
    "naming_quality"         => DetectorMeta { name: "naming_quality",         display: "Naming Quality",          dimension: "naming_quality",         action_type: "debt_review", guidance: "Improve semantic clarity of names.",                      fixers: &[], tool: None, structural: false, needs_judgment: true },
    "ai_generated_debt"      => DetectorMeta { name: "ai_generated_debt",      display: "AI-Generated Debt",       dimension: "ai_generated_debt",      action_type: "debt_review", guidance: "Review and refine AI-generated code for project fit.",    fixers: &[], tool: None, structural: false, needs_judgment: true },
    "design_coherence"       => DetectorMeta { name: "design_coherence",       display: "Design Coherence",        dimension: "design_coherence",       action_type: "debt_review", guidance: "Align implementation patterns with stated architecture.", fixers: &[], tool: None, structural: true, needs_judgment: true },
    // Tool-based detectors (wrapped external tools):
    "lint"                   => DetectorMeta { name: "lint",                   display: "Lint Errors",             dimension: "code_quality",           action_type: "auto_fix",    guidance: "Fix linter violations.", fixers: &["lint_fix"], tool: Some("eslint"),   structural: false, needs_judgment: false },
    "typecheck"              => DetectorMeta { name: "typecheck",              display: "Type Errors",             dimension: "code_quality",           action_type: "manual_fix",  guidance: "Resolve type errors.",   fixers: &[],           tool: Some("tsc"),      structural: false, needs_judgment: false },
    "format"                 => DetectorMeta { name: "format",                 display: "Format Violations",       dimension: "code_quality",           action_type: "auto_fix",    guidance: "Run the formatter.",     fixers: &["format"],   tool: Some("prettier"), structural: false, needs_judgment: false },
};
```

#### DISPLAY_ORDER

Ordered list of 27 detector names for consistent UI output. Determines the order findings are displayed in status, scorecard, and reports.

```rust
pub static DISPLAY_ORDER: &[&str] = &[
    "security",
    "lint",
    "typecheck",
    "format",
    "naming",
    "logs",
    "unused",
    "orphaned",
    "duplicate",
    "complexity",
    "large",
    "gods",
    "coupling",
    "cycle",
    "interface",
    "smells",
    "test_coverage",
    "concerns",
    "high_level_elegance",
    "mid_level_elegance",
    "low_level_elegance",
    "contract_coherence",
    "type_safety",
    "abstraction_fitness",
    "logic_clarity",
    "structure_navigation",
    "error_consistency",
];
```

#### Helper functions

```rust
/// Look up a detector by name. Returns None if not found.
pub fn get_detector(name: &str) -> Option<&'static DetectorMeta>;

/// Return all detectors in display order, skipping any not in DISPLAY_ORDER.
pub fn detectors_in_display_order() -> Vec<&'static DetectorMeta>;

/// Return all detector names as a sorted Vec.
pub fn all_detector_names() -> Vec<&'static str>;
```

---

### 2.4 discovery module

`crates/genesis-deslop-core/src/discovery.rs`

File discovery walks the project directory tree and produces a filtered list of files for scanning.

```rust
use std::path::{Path, PathBuf};

/// Trait for custom file filtering logic.
pub trait FileFilter: Send + Sync {
    fn should_include(&self, path: &Path) -> bool;
}

/// Walk the directory tree from `root`, applying exclusion rules from `config`
/// and extension matching from `lang_config`.
///
/// Behavior:
/// 1. Respects `.gitignore` if present (via `ignore` crate or manual parsing).
/// 2. Skips hidden directories (starting with `.`) except `.github`.
/// 3. Skips directories matching `config.exclude` patterns.
/// 4. Includes only files whose extensions match `lang_config.extensions`.
/// 5. Applies additional glob patterns from `lang_config.globs`.
/// 6. Skips files matching `lang_config.exclude` patterns.
/// 7. Sorts results by path for deterministic output.
///
/// Returns: Vec of absolute PathBuf entries.
pub fn discover_files(
    root: &Path,
    config: &Config,
    lang_config: &LangConfig,
) -> Vec<PathBuf>;

/// Compute the relative path from `root` to `file`.
/// Always uses forward slashes regardless of platform.
/// Panics if `file` is not under `root`.
pub fn rel_path(root: &Path, file: &Path) -> String;
```

#### Exclusion rules

The following directories are always excluded (hardcoded):

- `node_modules/`
- `.git/`
- `dist/`
- `build/`
- `__pycache__/`
- `.tox/`
- `.mypy_cache/`
- `.pytest_cache/`
- `venv/`, `.venv/`
- `vendor/` (unless zone is Vendor and scanning is explicitly requested)
- `.genesis-deslop/` (own state directory)

---

### 2.5 paths module

`crates/genesis-deslop-core/src/paths.rs`

Path and file I/O utilities.

```rust
use std::path::{Path, PathBuf};

/// Read a code snippet from a file, returning `context` lines above and below
/// the target `line` (1-indexed). Returns the snippet with line numbers.
///
/// Output format per line: "{line_number}: {content}"
/// The target line is marked: "{line_number}> {content}"
///
/// Returns an error if the file cannot be read or line is out of bounds.
pub fn read_code_snippet(file: &Path, line: usize, context: usize) -> Result<String>;

/// Write text content to a file atomically.
///
/// Implementation:
/// 1. Write content to a temporary file in the same directory.
/// 2. Sync the temp file to disk (fsync).
/// 3. Rename the temp file to the target path (atomic on POSIX).
///
/// This ensures no partial writes on crash.
pub fn safe_write_text(path: &Path, content: &str) -> Result<()>;

/// Resolve a relative path against a root directory.
/// Normalizes `.` and `..` components.
pub fn resolve_path(root: &Path, relative: &str) -> PathBuf;
```

---

### 2.6 output module

`crates/genesis-deslop-core/src/output.rs`

Terminal output formatting and logging.

```rust
/// Output format selection.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutputFormat {
    /// No ANSI codes, plain text.
    Plain,
    /// ANSI color-coded terminal output.
    Color,
    /// JSON output (one JSON object per logical unit).
    Json,
    /// Markdown-formatted output (for piping to files/LLMs).
    Markdown,
}

/// ANSI color codes.
#[derive(Debug, Clone, Copy)]
pub enum Color {
    Red,
    Green,
    Yellow,
    Cyan,
    Gray,
    Bold,
    BoldGreen,
    BoldRed,
    BoldYellow,
}

/// Log levels for stderr output.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum LogLevel {
    Debug,
    Info,
    Warn,
    Error,
}

/// Wrap text in ANSI escape codes for the given color.
/// Returns the text unchanged if NO_COLOR env var is set or stdout is not a TTY.
pub fn colorize(text: &str, color: Color) -> String;

/// Print an aligned table to stdout.
///
/// `headers`: column header names.
/// `rows`: row data (each inner Vec must have same length as headers).
///
/// Column widths are computed as max(header_len, max_cell_len) + 2 padding.
/// Headers are separated from data by a line of dashes.
pub fn print_table(headers: &[&str], rows: &[Vec<String>]);

/// Log a message to stderr with the given level.
/// Format: "[LEVEL] message"
/// Respects color settings.
pub fn log(level: LogLevel, msg: &str);
```

#### ANSI code table

| Color | Code | Reset |
|---|---|---|
| Red | `\x1b[31m` | `\x1b[0m` |
| Green | `\x1b[32m` | `\x1b[0m` |
| Yellow | `\x1b[33m` | `\x1b[0m` |
| Cyan | `\x1b[36m` | `\x1b[0m` |
| Gray | `\x1b[90m` | `\x1b[0m` |
| Bold | `\x1b[1m` | `\x1b[0m` |
| BoldGreen | `\x1b[1;32m` | `\x1b[0m` |
| BoldRed | `\x1b[1;31m` | `\x1b[0m` |
| BoldYellow | `\x1b[1;33m` | `\x1b[0m` |

---

## 3. genesis-deslop-engine

This crate contains the detection engine, scoring pipeline, state management, work queue, plan management, design concerns, and zone policy. It depends on `genesis-deslop-core` and `genesis-deslop-lang`.

### 3.1 state module

`crates/genesis-deslop-engine/src/state.rs`

The state model tracks all findings, scores, and scan history. It is persisted as JSON in `.genesis-deslop/state.json`.

#### Core types

```rust
use std::collections::HashMap;
use serde::{Serialize, Deserialize};

/// A single detected issue in the codebase.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Finding {
    /// Unique identifier: "{detector}::{relative_path}::{symbol_or_line}"
    /// Example: "complexity::src/engine.ts::processQueue"
    pub id: String,

    /// Name of the detector that produced this finding.
    pub detector: String,

    /// Relative file path from project root.
    pub file: String,

    /// Effort tier for remediation.
    pub tier: Tier,

    /// How confident the detector is in this finding.
    pub confidence: Confidence,

    /// One-line human-readable summary of the issue.
    pub summary: String,

    /// Flexible detail map for detector-specific data.
    /// Common keys: "loc" (u32), "complexity" (u32), "methods" (u32),
    /// "similarity" (f64), "symbol" (String), "line" (u32),
    /// "files" (Vec<String>), "pattern" (String).
    pub detail: HashMap<String, serde_json::Value>,

    /// Current lifecycle status.
    pub status: Status,

    /// Optional human-added note.
    pub note: Option<String>,

    /// ISO 8601 timestamp of first detection.
    pub first_seen: String,

    /// ISO 8601 timestamp of most recent detection.
    pub last_seen: String,

    /// ISO 8601 timestamp when finding was resolved (status changed from Open).
    pub resolved_at: Option<String>,

    /// Number of times this finding was reopened after being resolved.
    pub reopen_count: u32,

    /// Whether this finding is suppressed via config ignore patterns.
    pub suppressed: Option<bool>,

    /// ISO 8601 timestamp of suppression.
    pub suppressed_at: Option<String>,

    /// The pattern that caused suppression.
    pub suppression_pattern: Option<String>,

    /// Attestation from a developer when resolving as Wontfix or FalsePositive.
    pub resolution_attestation: Option<Attestation>,

    /// Language that produced this finding (for multi-language projects).
    pub lang: Option<String>,

    /// Zone classification of the finding's file.
    pub zone: Option<Zone>,
}

/// A developer's attestation for resolving a finding.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Attestation {
    /// Who attested (name or email).
    pub by: String,
    /// Why the finding was resolved this way.
    pub reason: String,
    /// ISO 8601 timestamp of attestation.
    pub at: String,
}
```

#### State model

```rust
/// The complete persistent state for a project.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StateModel {
    /// Schema version for forward compatibility. Current: 1.
    pub version: u32,

    /// ISO 8601 timestamp of first scan.
    pub created: String,

    /// ISO 8601 timestamp of most recent scan.
    pub last_scan: String,

    /// Total number of scans performed.
    pub scan_count: u32,

    /// Lenient overall score (0-100). Includes all dimensions, only Open counts as failure.
    pub overall_score: f64,

    /// Objective score (0-100). Mechanical dimensions only, lenient mode.
    pub objective_score: f64,

    /// Strict score (0-100). All dimensions, Open + Wontfix count as failure.
    pub strict_score: f64,

    /// Verified strict score (0-100). All dimensions, only AutoResolved counts as pass.
    pub verified_strict_score: f64,

    /// Aggregate statistics.
    pub stats: StateStats,

    /// All findings, keyed by finding ID.
    pub findings: HashMap<String, Finding>,

    /// Per-file scan coverage metadata.
    pub scan_coverage: HashMap<String, serde_json::Value>,

    /// Human-readable confidence qualifier: "high", "medium", "low".
    /// Based on sample size relative to MIN_SAMPLE.
    pub score_confidence: String,

    /// Rolling history of scan results (max 20 entries, FIFO).
    pub scan_history: Vec<ScanHistoryEntry>,

    /// Subjective integrity tracking (anti-gaming).
    pub subjective_integrity: HashMap<String, serde_json::Value>,

    /// Cached subjective assessment results.
    pub subjective_assessments: HashMap<String, serde_json::Value>,

    /// Dismissed concern fingerprints and metadata.
    pub concern_dismissals: HashMap<String, serde_json::Value>,
}

pub const CURRENT_VERSION: u32 = 1;
```

#### Statistics and history

```rust
/// Aggregate statistics for the current state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StateStats {
    /// Total files discovered during scan.
    pub total_files: u32,
    /// Total lines of code across all files.
    pub total_loc: u32,
    /// Total directories containing scanned files.
    pub total_dirs: u32,
    /// Primary language detected.
    pub language: String,
    /// Count of findings with status == Open.
    pub open_findings: u32,
    /// Count of findings with status == Fixed.
    pub fixed_findings: u32,
    /// Count of findings with status == Wontfix.
    pub wontfix_findings: u32,
    /// Count of findings where suppressed == Some(true).
    pub suppressed_findings: u32,
}

/// A single entry in the scan history ring buffer.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScanHistoryEntry {
    pub timestamp: String,
    pub scan_count: u32,
    pub overall_score: f64,
    pub objective_score: f64,
    pub strict_score: f64,
    pub verified_strict_score: f64,
    pub open_count: u32,
    pub fixed_count: u32,
    /// Per-detector count of open findings at this scan.
    pub detector_counts: HashMap<String, u32>,
    pub file_count: u32,
    pub loc_count: u32,
}
```

#### Scan diff

```rust
/// Summary of changes between two scans.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScanDiff {
    /// Finding IDs that are new in this scan.
    pub new_findings: Vec<String>,
    /// Finding IDs that were open but are now resolved.
    pub resolved_findings: Vec<String>,
    /// Finding IDs that were resolved but reappeared.
    pub reopened_findings: Vec<String>,
    /// Change in overall score (positive = improvement).
    pub score_delta: f64,
}
```

#### Functions

```rust
/// Load state from `.genesis-deslop/state.json`.
/// Returns a default empty StateModel if the file doesn't exist.
/// Returns Err(StateCorrupt) if the file exists but cannot be parsed.
pub fn load_state(dir: &Path) -> Result<StateModel>;

/// Save state to `.genesis-deslop/state.json` atomically.
///
/// Implementation:
/// 1. Create `.genesis-deslop/` directory if it doesn't exist.
/// 2. If state.json exists, copy it to state.json.bak (backup).
/// 3. Write new state via safe_write_text.
pub fn save_state(dir: &Path, state: &StateModel) -> Result<()>;

/// Merge scan options controlling the merge behavior.
pub struct MergeScanOptions {
    /// Root path of the scan.
    pub scan_path: PathBuf,
    /// Language that was scanned.
    pub language: String,
    /// Set of detector names that ran in this scan.
    /// Only findings from these detectors are eligible for auto-resolve.
    pub detectors_run: HashSet<String>,
    /// Whether to recompute scores after merge.
    pub update_scores: bool,
}

/// Merge newly detected findings into existing state.
///
/// Algorithm:
/// 1. For each new finding, check if an existing finding has the same ID:
///    a. If match found and existing is Open: update last_seen, merge details.
///    b. If match found and existing is resolved: reopen (set status=Open, increment reopen_count).
///    c. If no match: insert as new finding with first_seen = now.
/// 2. For each existing Open finding whose detector ran but was NOT in new findings:
///    set status = AutoResolved, resolved_at = now.
/// 3. Apply noise budget: if a detector produced > finding_noise_budget new findings,
///    suppress excess (sorted by confidence desc, keep highest confidence).
/// 4. Apply suppression patterns from config.ignore.
/// 5. If update_scores: recompute all scores via scoring module.
/// 6. Append to scan_history (trim to SCAN_HISTORY_MAX).
/// 7. Update stats.
/// 8. Return ScanDiff describing what changed.
pub fn merge_scan(
    state: &mut StateModel,
    new_findings: Vec<Finding>,
    options: &MergeScanOptions,
) -> ScanDiff;

/// Resolve specific findings by ID.
///
/// Sets status to `new_status`, resolved_at to now, attaches attestation if provided.
/// Returns list of IDs that were actually changed.
pub fn resolve_findings(
    state: &mut StateModel,
    ids: &[&str],
    new_status: Status,
    attestation: Option<Attestation>,
) -> Vec<String>;

/// Create a new Finding with defaults filled in.
///
/// Sets: id = "{detector}::{file}::{summary_slug}", first_seen = now,
/// last_seen = now, status = Open, reopen_count = 0.
pub fn make_finding(
    detector: &str,
    file: &str,
    tier: Tier,
    confidence: Confidence,
    summary: &str,
) -> Finding;

/// Match findings in state against a glob/regex pattern.
///
/// Matching rules (applied in order, first match wins):
/// 1. Exact ID match.
/// 2. Glob pattern match against finding ID.
/// 3. Glob pattern match against finding file.
/// 4. Regex match against finding summary.
pub fn match_findings<'a>(state: &'a StateModel, pattern: &str) -> Vec<&'a Finding>;
```

---

### 3.2 scoring module

`crates/genesis-deslop-engine/src/scoring.rs`

**CRITICAL**: The scoring pipeline must produce results identical to the Python implementation within a tolerance of 0.001 on any input. This is the most important correctness requirement in the system.

#### Score modes

```rust
/// Determines which statuses count as "failure" in scoring.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScoreMode {
    /// Only `Open` counts as failure.
    Lenient,
    /// `Open` and `Wontfix` count as failure.
    Strict,
    /// `Open`, `Wontfix`, `Fixed`, and `FalsePositive` count as failure.
    /// Only `AutoResolved` counts as pass.
    VerifiedStrict,
}

impl ScoreMode {
    /// Returns true if the given status counts as a failure in this mode.
    pub fn is_failure(&self, status: Status) -> bool {
        match self {
            ScoreMode::Lenient => matches!(status, Status::Open),
            ScoreMode::Strict => matches!(status, Status::Open | Status::Wontfix),
            ScoreMode::VerifiedStrict => matches!(
                status,
                Status::Open | Status::Wontfix | Status::Fixed | Status::FalsePositive
            ),
        }
    }
}
```

#### Scoring pools and dimensions

```rust
/// Which scoring pool a dimension belongs to.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScoringPool {
    /// Automated/objective detectors (lint, complexity, etc.).
    Mechanical,
    /// Human-review/subjective detectors (elegance, coherence, etc.).
    Subjective,
}

/// A scoring dimension with its pool and weight.
#[derive(Debug, Clone)]
pub struct Dimension {
    pub name: &'static str,
    pub pool: ScoringPool,
    pub weight: f64,
}
```

#### Dimension definitions

**Mechanical dimensions** (total weight: 6.0, 40% of overall score):

| Dimension | Weight |
|---|---|
| `file_health` | 2.0 |
| `code_quality` | 1.0 |
| `duplication` | 1.0 |
| `test_health` | 1.0 |
| `security` | 1.0 |

**Subjective dimensions** (total weight: 115.0, 60% of overall score):

| Dimension | Weight |
|---|---|
| `high_level_elegance` | 22.0 |
| `mid_level_elegance` | 22.0 |
| `low_level_elegance` | 12.0 |
| `contract_coherence` | 12.0 |
| `type_safety` | 12.0 |
| `abstraction_fitness` | 8.0 |
| `logic_clarity` | 6.0 |
| `structure_navigation` | 5.0 |
| `error_consistency` | 3.0 |
| `naming_quality` | 2.0 |
| `ai_generated_debt` | 1.0 |
| `design_coherence` | 10.0 |

```rust
pub static DIMENSIONS: &[Dimension] = &[
    // Mechanical
    Dimension { name: "file_health",          pool: ScoringPool::Mechanical,  weight: 2.0 },
    Dimension { name: "code_quality",         pool: ScoringPool::Mechanical,  weight: 1.0 },
    Dimension { name: "duplication",          pool: ScoringPool::Mechanical,  weight: 1.0 },
    Dimension { name: "test_health",          pool: ScoringPool::Mechanical,  weight: 1.0 },
    Dimension { name: "security",             pool: ScoringPool::Mechanical,  weight: 1.0 },
    // Subjective
    Dimension { name: "high_level_elegance",  pool: ScoringPool::Subjective,  weight: 22.0 },
    Dimension { name: "mid_level_elegance",   pool: ScoringPool::Subjective,  weight: 22.0 },
    Dimension { name: "low_level_elegance",   pool: ScoringPool::Subjective,  weight: 12.0 },
    Dimension { name: "contract_coherence",   pool: ScoringPool::Subjective,  weight: 12.0 },
    Dimension { name: "type_safety",          pool: ScoringPool::Subjective,  weight: 12.0 },
    Dimension { name: "abstraction_fitness",  pool: ScoringPool::Subjective,  weight: 8.0 },
    Dimension { name: "logic_clarity",        pool: ScoringPool::Subjective,  weight: 6.0 },
    Dimension { name: "structure_navigation", pool: ScoringPool::Subjective,  weight: 5.0 },
    Dimension { name: "error_consistency",    pool: ScoringPool::Subjective,  weight: 3.0 },
    Dimension { name: "naming_quality",       pool: ScoringPool::Subjective,  weight: 2.0 },
    Dimension { name: "ai_generated_debt",    pool: ScoringPool::Subjective,  weight: 1.0 },
    Dimension { name: "design_coherence",     pool: ScoringPool::Subjective,  weight: 10.0 },
];
```

#### Detector-to-dimension mapping

```rust
/// Maps a detector to its scoring behavior.
pub struct DetectorScoringPolicy {
    /// Detector name (must exist in DETECTORS registry).
    pub detector: &'static str,
    /// Dimension this detector's findings contribute to.
    pub dimension: &'static str,
    /// Default tier if not set on the finding itself.
    pub default_tier: Tier,
    /// If true, findings are grouped per-file for cap calculation.
    pub file_based: bool,
    /// If true, finding weight is scaled by file LOC / average LOC.
    pub use_loc_weight: bool,
    /// Zones where this detector's findings are excluded from scoring.
    pub excluded_zones: &'static [Zone],
}
```

29 policies mapping detectors to dimensions. Each mechanical detector maps to one of the 5 mechanical dimensions. Each subjective detector maps to its eponymous dimension. Policies specify:

| Detector | Dimension | Default Tier | File-based | LOC weight | Excluded zones |
|---|---|---|---|---|---|
| `duplicate` | `duplication` | Judgment | true | true | [Generated, Vendor] |
| `complexity` | `code_quality` | Judgment | true | false | [Generated, Vendor] |
| `large` | `file_health` | Judgment | true | true | [Generated, Vendor, Config] |
| `gods` | `file_health` | MajorRefactor | true | true | [Generated, Vendor, Test] |
| `coupling` | `file_health` | Judgment | true | false | [Generated, Vendor] |
| `cycle` | `file_health` | MajorRefactor | false | false | [Generated, Vendor] |
| `unused` | `file_health` | AutoFix | true | false | [Generated, Vendor, Test] |
| `orphaned` | `file_health` | QuickFix | true | false | [Generated, Vendor] |
| `security` | `security` | Judgment | true | false | [Generated, Vendor, Test] |
| `naming` | `code_quality` | AutoFix | true | false | [Generated, Vendor] |
| `smells` | `code_quality` | QuickFix | true | false | [Generated, Vendor] |
| `test_coverage` | `test_health` | Judgment | true | false | [Generated, Vendor] |
| `logs` | `code_quality` | AutoFix | true | false | [Generated, Vendor, Test] |
| `interface` | `code_quality` | Judgment | true | false | [Generated, Vendor] |
| `concerns` | `code_quality` | Judgment | false | false | [Generated, Vendor] |
| `lint` | `code_quality` | AutoFix | true | false | [Generated, Vendor] |
| `typecheck` | `code_quality` | QuickFix | true | false | [Generated, Vendor] |
| `format` | `code_quality` | AutoFix | true | false | [Generated, Vendor] |
| `high_level_elegance` | `high_level_elegance` | Judgment | false | false | [Generated, Vendor] |
| `mid_level_elegance` | `mid_level_elegance` | Judgment | false | false | [Generated, Vendor] |
| `low_level_elegance` | `low_level_elegance` | Judgment | false | false | [Generated, Vendor] |
| `contract_coherence` | `contract_coherence` | Judgment | false | false | [Generated, Vendor] |
| `type_safety` | `type_safety` | Judgment | false | false | [Generated, Vendor] |
| `abstraction_fitness` | `abstraction_fitness` | Judgment | false | false | [Generated, Vendor] |
| `logic_clarity` | `logic_clarity` | Judgment | false | false | [Generated, Vendor] |
| `structure_navigation` | `structure_navigation` | Judgment | false | false | [Generated, Vendor] |
| `error_consistency` | `error_consistency` | Judgment | false | false | [Generated, Vendor] |
| `naming_quality` | `naming_quality` | Judgment | false | false | [Generated, Vendor] |
| `design_coherence` | `design_coherence` | Judgment | false | false | [Generated, Vendor] |

#### Constants

```rust
/// Minimum sample size for full-confidence scoring.
/// Below this, scores receive a "low" confidence qualifier.
const MIN_SAMPLE: usize = 200;

/// Multiplier applied to subjective dimension failure weights.
/// Subjective findings have fewer data points, so each one impacts more.
const HOLISTIC_MULTIPLIER: f64 = 10.0;

/// Maximum number of subjective findings per dimension before saturation.
const HOLISTIC_POTENTIAL: usize = 10;

/// Number of subjective checks per dimension.
const SUBJECTIVE_CHECKS: usize = 10;

/// Weight fraction for mechanical pool in overall score.
const MECHANICAL_WEIGHT_FRACTION: f64 = 0.40;

/// Weight fraction for subjective pool in overall score.
const SUBJECTIVE_WEIGHT_FRACTION: f64 = 0.60;

/// Tolerance for detecting target-matching (anti-gaming).
const SUBJECTIVE_TARGET_MATCH_TOLERANCE: f64 = 0.05;

/// Number of consecutive target-matches before subjective scores are reset.
const SUBJECTIVE_TARGET_RESET_THRESHOLD: usize = 2;

/// File-level finding cap: if a file has >= 6 findings from one detector,
/// cap multiplier is 2.0 (diminishing returns).
const FILE_CAP_HIGH_THRESHOLD: usize = 6;

/// File-level finding cap: if a file has >= 3 findings, cap = 1.5.
const FILE_CAP_MID_THRESHOLD: usize = 3;

/// File-level finding cap for files with < 3 findings.
const FILE_CAP_LOW: f64 = 1.0;

/// Maximum entries in scan_history ring buffer.
const SCAN_HISTORY_MAX: usize = 20;

/// Days before superseded findings are purged from plan.
const SUPERSEDED_TTL_DAYS: u64 = 90;
```

#### Score output

```rust
/// Complete scoring result across all modes and dimensions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreBundle {
    /// Per-dimension scores in lenient mode (0-100 each).
    pub dimension_scores: HashMap<String, f64>,
    /// Per-dimension scores in strict mode.
    pub strict_dimension_scores: HashMap<String, f64>,
    /// Per-dimension scores in verified-strict mode.
    pub verified_strict_dimension_scores: HashMap<String, f64>,
    /// Lenient overall: weighted blend of all dimensions.
    pub overall_score: f64,
    /// Objective: weighted blend of mechanical dimensions only, lenient mode.
    pub objective_score: f64,
    /// Strict overall.
    pub strict_score: f64,
    /// Verified strict overall.
    pub verified_strict_score: f64,
}
```

#### Scoring pipeline algorithm

This is the exact algorithm that must be implemented. Each step corresponds to a function or block in the pipeline.

```rust
/// Main entry point. Computes all scores from the current findings.
pub fn compute_health_breakdown(
    findings: &[Finding],
    mode: ScoreMode,
    config: &Config,
) -> ScoreBundle;
```

**Step-by-step algorithm:**

1. **Filter findings**: Remove findings where `suppressed == Some(true)` or where the finding's zone is in the detector's `excluded_zones`.

2. **Group by detector**: Create `HashMap<String, Vec<&Finding>>` mapping detector name to its findings.

3. **For each detector, group by file**: Create `HashMap<String, Vec<&Finding>>` mapping file path to findings in that file.

4. **Compute file cap multiplier**: For each file group:
   - Count = number of findings in this file for this detector.
   - If count >= `FILE_CAP_HIGH_THRESHOLD` (6): cap = 2.0
   - Else if count >= `FILE_CAP_MID_THRESHOLD` (3): cap = 1.5
   - Else: cap = `FILE_CAP_LOW` (1.0)
   - The cap is applied to the SUM of finding weights in that file, not per-finding.

5. **Compute per-finding weight**: For each finding:
   ```
   finding_weight = confidence.weight() * tier.weight() as f64
   ```
   Where `confidence.weight()` is `{High: 1.0, Medium: 0.7, Low: 0.3}` and `tier.weight()` is `{AutoFix: 1, QuickFix: 2, Judgment: 3, MajorRefactor: 4}`.

6. **Compute weighted failures per detector per mode**: For each `ScoreMode`:
   ```
   weighted_failures = 0.0
   for each file_group in detector_files:
       file_sum = sum(finding_weight for f in file_group if mode.is_failure(f.status))
       weighted_failures += file_sum * file_cap_for_this_file
   ```

7. **Map detectors to dimensions**: Using `DetectorScoringPolicy`, accumulate `weighted_failures` per dimension.

8. **Compute dimension scale**:
   - For **subjective** dimensions: `dimension_scale = HOLISTIC_MULTIPLIER` (10.0)
   - For **mechanical** dimensions: `dimension_scale = max(1.0, MIN_SAMPLE as f64 / total_files as f64)`
     where `total_files` is the number of files scanned.

9. **Compute per-dimension score**:
   ```
   score = max(0.0, 100.0 - weighted_failures * dimension_scale)
   ```
   Clamp to [0.0, 100.0].

10. **Compute pool-weighted blends**:
    - Mechanical pool score = weighted average of mechanical dimension scores (weighted by dimension weight).
    - Subjective pool score = weighted average of subjective dimension scores (weighted by dimension weight).
    - Overall score = `MECHANICAL_WEIGHT_FRACTION * mechanical_score + SUBJECTIVE_WEIGHT_FRACTION * subjective_score`.

11. **Compute 4-channel output**:
    - `overall_score`: Lenient mode, all dimensions.
    - `objective_score`: Lenient mode, mechanical dimensions only (weighted average of mechanical pool).
    - `strict_score`: Strict mode, all dimensions (recompute steps 6-10 with Strict mode).
    - `verified_strict_score`: VerifiedStrict mode, all dimensions.

12. **Return `ScoreBundle`** with all dimension scores and overall scores.

#### Helper functions

```rust
/// Compute the score impact of a single finding (used for work queue ranking).
/// Impact = confidence.weight() * tier.weight() * dimension_weight / pool_total_weight
pub fn compute_score_impact(finding: &Finding) -> f64;

/// Compute the pass rate for a detector: fraction of findings that are NOT failures.
/// pass_rate = 1.0 - (failure_count / max(total, 1))
pub fn detector_pass_rate(detector: &str, findings: &[Finding], total: usize) -> f64;
```

---

### 3.3 detectors module

`crates/genesis-deslop-engine/src/detectors/`

This is a directory module with one file per detector implementation plus a shared `mod.rs`.

#### Detector trait

```rust
use std::path::PathBuf;

/// Context provided to every detector during a scan.
pub struct DetectorContext {
    /// List of files to analyze (absolute paths).
    pub files: Vec<PathBuf>,
    /// Zone classification for each file (relative path -> Zone).
    pub zone_map: FileZoneMap,
    /// Dependency graph (import/require relationships).
    pub dep_graph: DepGraph,
    /// Project configuration.
    pub config: Config,
    /// Language-specific configuration.
    pub lang_config: LangConfig,
    /// Root path of the scan.
    pub scan_path: PathBuf,
}

/// Every detector must implement this trait.
pub trait Detector: Send + Sync {
    /// Internal name matching the registry key.
    fn name(&self) -> &str;

    /// Run detection on the given context and return findings.
    /// The detector should NOT filter by zone — the engine handles that.
    fn detect(&self, ctx: &DetectorContext) -> Result<Vec<Finding>>;

    /// Default tier for findings from this detector.
    fn tier(&self) -> Tier;
}
```

#### Dependency graph

```rust
/// Directed graph of file imports.
pub struct DepGraph {
    /// petgraph DiGraph where nodes are file paths and edges are imports.
    pub graph: petgraph::Graph<String, ()>,
    /// Map from file path to node index for quick lookup.
    pub node_map: HashMap<String, petgraph::graph::NodeIndex>,
}

impl DepGraph {
    /// Build a dependency graph from the language plugin's import resolver.
    pub fn build(files: &[PathBuf], lang: &dyn LanguagePlugin) -> Self;

    /// Get all files that `file` imports.
    pub fn imports_of(&self, file: &str) -> Vec<&str>;

    /// Get all files that import `file`.
    pub fn importers_of(&self, file: &str) -> Vec<&str>;

    /// Get the fan-in count (number of importers).
    pub fn fan_in(&self, file: &str) -> usize;

    /// Get the fan-out count (number of imports).
    pub fn fan_out(&self, file: &str) -> usize;
}
```

#### Key detector implementations

Each detector is a struct implementing `Detector`. Below are the critical algorithmic details.

##### DuplicateDetector

`crates/genesis-deslop-engine/src/detectors/duplicate.rs`

```rust
pub struct DuplicateDetector;

impl Detector for DuplicateDetector {
    fn name(&self) -> &str { "duplicate" }
    fn tier(&self) -> Tier { Tier::Judgment }
    fn detect(&self, ctx: &DetectorContext) -> Result<Vec<Finding>> { ... }
}
```

Algorithm:
1. Extract all functions via language plugin extractors.
2. **Exact duplicate detection**: Group functions by `body_hash` (MD5, 12 chars). Groups with 2+ members are exact duplicates.
3. **Near-duplicate detection**: For functions not in exact groups, compute pairwise similarity using `similar::SequenceMatcher` (difflib equivalent). Threshold: 0.9 (90% similar).
4. **Filtering**:
   - Minimum LOC per function: 15 lines.
   - LOC ratio between two near-duplicates must be <= 1.5x.
   - Skip functions in different zones if one is Test.
5. **Clustering**: Use union-find (petgraph's UnionFind) to cluster transitively-connected duplicates.
6. **Output**: One finding per cluster. Finding ID: `"duplicate::{file_of_largest}::{function_name}"`. Detail includes all member functions with file, line, LOC, and similarity score.

##### CycleDetector

`crates/genesis-deslop-engine/src/detectors/cycle.rs`

```rust
pub struct CycleDetector;
```

Algorithm:
1. Build the dependency graph (DepGraph).
2. Run **iterative Tarjan's SCC** algorithm (not recursive, to handle deep graphs without stack overflow). Use `petgraph::algo::tarjan_scc`.
3. Filter SCCs to those with size >= 2.
4. **Deferred import filtering**: For languages that support deferred/lazy imports (Python: imports inside functions; TypeScript: dynamic `import()`), remove edges that are deferred before SCC computation.
5. One finding per SCC. Tier: MajorRefactor. Finding ID: `"cycle::{first_file_alphabetically}::{scc_hash}"`. Detail includes all files in the cycle and the edge list.

##### ComplexityDetector

`crates/genesis-deslop-engine/src/detectors/complexity.rs`

```rust
pub struct ComplexityDetector;
```

Algorithm:
1. Extract functions via language plugin.
2. For each function, compute cyclomatic complexity using language-specific `ComplexitySignal` patterns.
3. Compare against per-language thresholds:

| Language | Default threshold | High threshold |
|---|---|---|
| TypeScript | 15 | 25 |
| Python | 25 | 40 |
| C# | 20 | 35 |
| Dart | 16 | 28 |
| GDScript | 16 | 28 |
| Go | 15 | 25 |
| Generic | 15 | 25 |

4. One finding per function exceeding the threshold. Tier: Judgment (default), QuickFix if complexity is barely over threshold (< 1.5x).

##### LargeFileDetector

`crates/genesis-deslop-engine/src/detectors/large.rs`

```rust
pub struct LargeFileDetector;
```

Per-language LOC thresholds:

| Language | Default threshold |
|---|---|
| TypeScript | 500 |
| Python | 300 |
| C# | 500 |
| Dart | 500 |
| GDScript | 500 |
| Go | 500 |
| Generic | 500 |

Config override: `config.large_files_threshold` (if > 0) overrides language default. One finding per file exceeding threshold. Detail includes LOC count.

##### GodClassDetector

`crates/genesis-deslop-engine/src/detectors/gods.rs`

```rust
pub struct GodClassDetector;
```

Per-language rules:
- **TypeScript**: Checks for React components with too many hooks (>7), classes with too many methods (>15), files with too many exports (>20).
- **Python**: Classes with too many methods (>15), too many attributes (>10), too many base classes (>5).
- **C#**: Classes with too many methods (>20), too many attributes (>15), implementing too many interfaces (>5).
- **Other languages**: Generic method/attribute count thresholds.

Each rule is a `GodRule` struct; the detector evaluates all rules for the language and emits one finding per class/component exceeding any rule.

##### SecurityDetector

`crates/genesis-deslop-engine/src/detectors/security.rs`

```rust
pub struct SecurityDetector;
```

Per-language checks:
- **TypeScript** (10 checks): `dangerouslySetInnerHTML`, `eval()`, hardcoded secrets (regex for API keys/tokens), `innerHTML` assignment, `document.write`, SQL string concatenation, `child_process.exec` with user input, `new Function()`, unvalidated redirect, `crypto.createHash('md5')`.
- **Python**: Wraps `bandit` output if available, plus: `eval()`, `exec()`, `pickle.loads`, `yaml.load` without SafeLoader, `subprocess.call(shell=True)`, hardcoded passwords, SQL string formatting.
- **C#** (4 checks): SQL string concatenation, `Process.Start` with user input, `[AllowAnonymous]` on sensitive endpoints, hardcoded connection strings.

##### SmellDetector

`crates/genesis-deslop-engine/src/detectors/smells.rs`

```rust
pub struct SmellDetector;
```

Language-specific smell checks:
- **TypeScript** (28 checks): boolean prop explosion, excessive useState, nested ternaries, callback hell, any-type usage, magic numbers, long parameter lists, deeply nested JSX, excessive re-renders, missing error boundaries, prop drilling, etc.
- **Python** (32 checks): bare except, mutable default arguments, wildcard imports, nested functions > 2 deep, class with no methods, global state mutation, string concatenation in loops, missing `__init__`, redundant `else` after `return`, `type()` instead of `isinstance()`, etc.

Each smell check is a named pattern (regex or multi-line heuristic) producing findings at specific line numbers.

##### Other detectors

- **UnusedDetector**: Uses language plugin's dead-export detection (e.g., Knip for TypeScript). Finds exports not imported by any other file in the dep graph.
- **OrphanedDetector**: Files with zero importers (fan_in == 0) that are not entry points. Entry points identified by language plugin (e.g., `main.ts`, `index.ts`, `__main__.py`).
- **CouplingDetector**: Files with fan_out > threshold (default 10) or fan_in > threshold (default 15). Adjustable per-language.
- **NamingDetector**: Convention violations per language (camelCase for JS/TS, snake_case for Python/Rust, PascalCase for C#).
- **TestCoverageDetector**: Maps source files to test files via convention (e.g., `foo.ts` -> `foo.test.ts`). Flags source files without corresponding test files.

---

### 3.4 work_queue module

`crates/genesis-deslop-engine/src/work_queue.rs`

Builds a prioritized list of findings for developers to work on.

```rust
/// Options for building a work queue.
pub struct QueueBuildOptions {
    /// Filter to a specific tier. None = all tiers.
    pub tier: Option<Tier>,
    /// Maximum number of items to return.
    pub count: usize,
    /// Root scan path (for relative path computation).
    pub scan_path: PathBuf,
    /// Filter to a specific file or directory scope.
    pub scope: Option<String>,
    /// Filter by finding status. None = Open only.
    pub status: Option<Status>,
    /// Include subjective/review-based findings.
    pub include_subjective: bool,
    /// Minimum subjective score threshold to include.
    pub subjective_threshold: f64,
    /// Include chronic/recurring findings (reopen_count > 0).
    pub chronic: bool,
    /// If tier filter matches nothing, do NOT fall back to next tier.
    pub no_tier_fallback: bool,
    /// Include explanation text for each item.
    pub explain: bool,
    /// If set, integrate plan data (skip/cluster status).
    pub plan: Option<PlanModel>,
    /// Include items marked as skipped in plan.
    pub include_skipped: bool,
    /// Filter to a specific cluster.
    pub cluster: Option<String>,
    /// Collapse cluster members into single cluster items.
    pub collapse_clusters: bool,
}

/// A single item in the work queue.
pub struct RankedItem {
    /// Finding ID or cluster ID.
    pub id: String,
    /// Display label.
    pub label: String,
    /// Tier of this item.
    pub tier: Tier,
    /// Confidence of this item.
    pub confidence: Confidence,
    /// Score impact (how much fixing this would improve the score).
    pub impact: f64,
    /// Detector name.
    pub detector: String,
    /// File path.
    pub file: String,
    /// Action type from registry.
    pub action_type: String,
    /// Whether this item is from a cluster.
    pub clustered: bool,
    /// Number of members if clustered.
    pub member_count: usize,
    /// Explanation text (if explain=true).
    pub explanation: Option<String>,
    /// Whether this item is skipped in the plan.
    pub skipped: bool,
    /// Review weight for subjective items.
    pub review_weight: f64,
}

/// Result of building a work queue.
pub struct WorkQueueResult {
    /// Ordered list of items.
    pub items: Vec<RankedItem>,
    /// Total matching items before count limit.
    pub total: usize,
    /// Count of items per tier.
    pub tier_counts: HashMap<Tier, usize>,
    /// The tier that was requested.
    pub requested_tier: Option<Tier>,
    /// The tier that was actually selected (may differ due to fallback).
    pub selected_tier: Option<Tier>,
    /// Reason for tier fallback (if any).
    pub fallback_reason: Option<String>,
    /// All tiers that have at least one item.
    pub available_tiers: Vec<Tier>,
    /// Whether items are grouped by cluster.
    pub grouped: bool,
}
```

#### Sort key

The sort key determines work queue ordering. Items are sorted by a composite tuple key:

```rust
/// Sort key for work queue items.
/// Lower values sort first. Implement via Ord trait.
///
/// For clusters:
///   (0, action_priority, u32::MAX - member_count, id)
///
/// For regular findings:
///   (effective_tier as u32, 0, confidence.rank(), u32::MAX - review_weight_scaled, u32::MAX - finding_count, id)
///
/// For subjective items:
///   (effective_tier as u32, 1, subjective_score_scaled, id)
```

Action type priority mapping:

| Action type | Priority |
|---|---|
| `auto_fix` | 0 |
| `reorganize` | 1 |
| `refactor` | 2 |
| `manual_fix` | 3 |
| `debt_review` | 4 |

#### Tier fallback

When a specific tier is requested but has no items:
1. If `no_tier_fallback` is true: return empty result.
2. Otherwise: try the next lower tier (AutoFix -> QuickFix -> Judgment -> MajorRefactor).
3. If all lower tiers empty, try higher tiers.
4. Set `fallback_reason` explaining what happened.

#### Functions

```rust
/// Build a work queue from state and options.
pub fn build_work_queue(state: &StateModel, options: &QueueBuildOptions) -> WorkQueueResult;
```

---

### 3.5 plan module

`crates/genesis-deslop-engine/src/plan.rs`

The plan is a persistent work management layer on top of the state. It tracks ordering, skips, clusters, and superseded findings.

```rust
/// Current plan schema version.
pub const PLAN_VERSION: u32 = 2;

/// The complete plan model.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanModel {
    /// Schema version.
    pub version: u32,
    /// ISO 8601 creation timestamp.
    pub created: String,
    /// ISO 8601 last-updated timestamp.
    pub updated: String,
    /// Ordered list of finding IDs representing the work queue order.
    pub queue_order: Vec<String>,
    /// Findings that have been skipped, keyed by finding ID.
    pub skipped: HashMap<String, SkipEntry>,
    /// Currently focused cluster (if any).
    pub active_cluster: Option<String>,
    /// Per-finding overrides (e.g., tier override), keyed by finding ID.
    pub overrides: HashMap<String, ItemOverride>,
    /// Named clusters of related findings, keyed by cluster name.
    pub clusters: HashMap<String, Cluster>,
    /// Findings that have been superseded (ID changed due to refactoring), keyed by old ID.
    pub superseded: HashMap<String, SupersededEntry>,
}
```

#### Skip entries

```rust
/// Why a finding was skipped.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SkipKind {
    /// Skip temporarily, review later.
    Temporary,
    /// Skip permanently, will not fix.
    Permanent,
    /// Skip because this is a false positive.
    FalsePositive,
}

/// Record of a skipped finding.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkipEntry {
    /// The finding ID that was skipped.
    pub finding_id: String,
    /// Why it was skipped.
    pub kind: SkipKind,
    /// Human-readable reason.
    pub reason: String,
    /// Optional additional note.
    pub note: Option<String>,
    /// Attestation if kind is Permanent or FalsePositive.
    pub attestation: Option<Attestation>,
    /// ISO 8601 timestamp of when skip was created.
    pub created_at: String,
    /// Optional: review after this many scans.
    pub review_after: Option<u32>,
    /// Scan count at time of skip (for review_after calculation).
    pub skipped_at_scan: u32,
}
```

#### Clusters

```rust
/// A group of related findings that should be addressed together.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Cluster {
    /// Cluster name (e.g., "auth-refactor" or "auto/duplicate-utils").
    pub name: String,
    /// Human-readable description.
    pub description: String,
    /// Ordered list of finding IDs in this cluster.
    pub finding_ids: Vec<String>,
    /// ISO 8601 creation timestamp.
    pub created_at: String,
    /// ISO 8601 last-updated timestamp.
    pub updated_at: String,
    /// Whether this cluster was auto-generated.
    pub auto: bool,
    /// Key used for auto-clustering (e.g., "duplicate::utils").
    pub cluster_key: Option<String>,
    /// Suggested action type for the cluster.
    pub action: Option<String>,
    /// Whether a user has modified this auto-cluster.
    pub user_modified: bool,
}
```

Auto-clustering constants:

```rust
/// Prefix for auto-generated cluster names.
const AUTO_PREFIX: &str = "auto/";
/// Minimum number of findings to form an auto-cluster.
const MIN_CLUSTER_SIZE: usize = 2;
```

#### Superseded entries

```rust
/// Record of a finding whose ID changed (e.g., file was renamed/moved).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SupersededEntry {
    /// The original finding ID that no longer exists.
    pub original_id: String,
    /// Detector that produced the original finding.
    pub original_detector: String,
    /// File path in the original finding.
    pub original_file: String,
    /// Summary text of the original finding.
    pub original_summary: String,
    /// Status of the original finding at time of supersession.
    pub status: String,
    /// ISO 8601 timestamp of supersession.
    pub superseded_at: String,
    /// New finding ID this was remapped to (if a match was found).
    pub remapped_to: Option<String>,
    /// Candidate new finding IDs (fuzzy matches).
    pub candidates: Vec<String>,
    /// Optional note about the supersession.
    pub note: Option<String>,
}
```

#### Item overrides

```rust
/// Per-finding overrides applied by the user.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ItemOverride {
    /// Override the tier of this finding.
    pub tier: Option<Tier>,
    /// Override the priority rank.
    pub priority: Option<u32>,
    /// Custom note.
    pub note: Option<String>,
}
```

#### Functions

```rust
/// Load plan from `.genesis-deslop/plan.json`.
/// Returns default empty PlanModel if file doesn't exist.
pub fn load_plan(dir: &Path) -> Result<PlanModel>;

/// Save plan atomically.
pub fn save_plan(dir: &Path, plan: &PlanModel) -> Result<()>;

/// Reconcile plan with current state.
///
/// 1. Remove queue_order entries for findings no longer in state.
/// 2. Add new findings from state to end of queue_order.
/// 3. Move resolved findings to superseded (with TTL).
/// 4. Purge superseded entries older than SUPERSEDED_TTL_DAYS.
/// 5. Update cluster membership (remove stale finding IDs).
/// 6. Remove empty clusters (unless user_modified).
pub fn reconcile_plan(plan: &mut PlanModel, state: &StateModel);

/// Auto-cluster findings using union-find.
///
/// Grouping criteria:
/// 1. Same detector + same file → cluster by "{detector}::{file_stem}".
/// 2. Duplicate findings → cluster by duplicate group.
/// 3. Cycle findings → cluster by SCC.
/// 4. Concern findings with overlapping evidence → cluster.
///
/// Only creates clusters with >= MIN_CLUSTER_SIZE members.
/// Cluster names are prefixed with AUTO_PREFIX ("auto/").
/// Does not modify clusters where user_modified == true.
pub fn auto_cluster(plan: &mut PlanModel, state: &StateModel);

/// Skip a finding.
pub fn skip(plan: &mut PlanModel, finding_id: &str, kind: SkipKind, reason: &str, attestation: Option<Attestation>, review_after: Option<u32>, scan_count: u32);

/// Unskip a previously skipped finding.
pub fn unskip(plan: &mut PlanModel, finding_id: &str);

/// Reopen a resolved finding (set back to Open in the plan's context).
pub fn reopen(plan: &mut PlanModel, finding_id: &str);

/// Mark a finding as done (remove from queue_order, move to end).
pub fn done(plan: &mut PlanModel, finding_id: &str);

/// Move a finding to a specific position in queue_order.
/// `position` is 0-indexed. Negative values count from end.
pub fn move_item(plan: &mut PlanModel, finding_id: &str, position: i32);

/// Create a new cluster.
pub fn create_cluster(plan: &mut PlanModel, name: &str, description: &str, finding_ids: &[&str]);

/// Delete a cluster. Findings are returned to the main queue.
pub fn delete_cluster(plan: &mut PlanModel, name: &str);

/// Add findings to an existing cluster.
pub fn add_to_cluster(plan: &mut PlanModel, cluster_name: &str, finding_ids: &[&str]);

/// Remove findings from a cluster.
pub fn remove_from_cluster(plan: &mut PlanModel, cluster_name: &str, finding_ids: &[&str]);

/// Move a finding from one cluster to another.
pub fn move_between_clusters(plan: &mut PlanModel, finding_id: &str, from: &str, to: &str);
```

---

### 3.6 concerns module

`crates/genesis-deslop-engine/src/concerns.rs`

Design concerns are higher-level observations derived from patterns across multiple findings. They prompt design questions rather than prescribing fixes.

```rust
/// Types of design concerns.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ConcernType {
    /// File handles multiple unrelated responsibilities.
    MixedResponsibilities,
    /// Duplication suggests a missing abstraction.
    DuplicationDesign,
    /// Excessive nesting or branching indicates structural problems.
    StructuralComplexity,
    /// High coupling between modules suggests dependency issues.
    CouplingDesign,
    /// Interface with too many parameters suggests design issues.
    InterfaceDesign,
    /// General design concern not fitting other categories.
    DesignConcern,
    /// Pattern repeated across 3+ files suggests systemic issue.
    SystemicPattern,
    /// Same smell appearing in 5+ files.
    SystemicSmell,
}

/// A single design concern.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Concern {
    /// Category of concern.
    pub concern_type: ConcernType,
    /// Primary file associated with this concern.
    pub file: String,
    /// Human-readable summary.
    pub summary: String,
    /// Evidence items (finding IDs, metrics, observations).
    pub evidence: Vec<String>,
    /// Question to prompt design thinking (not a directive).
    pub question: String,
    /// Unique fingerprint: SHA-256 of (concern_type + file + sorted evidence), truncated to 16 hex chars.
    pub fingerprint: String,
    /// Finding IDs that contributed to this concern.
    pub source_findings: Vec<String>,
}
```

#### Thresholds for concern generation

| Condition | Concern type |
|---|---|
| Function with >= 8 parameters | `InterfaceDesign` |
| Nesting depth >= 6 | `StructuralComplexity` |
| File LOC >= 300 | `StructuralComplexity` |
| 3+ files with same detector profile | `SystemicPattern` |
| 5+ files with same smell | `SystemicSmell` |

#### Generators

```rust
/// Generate per-file concerns from findings for a single file.
/// Examines finding combinations within one file.
pub fn generate_per_file_concerns(file: &str, findings: &[&Finding]) -> Vec<Concern>;

/// Generate cross-file concerns by comparing findings across files.
/// Looks for common patterns (same detector in many files, coupling patterns).
pub fn generate_cross_file_concerns(findings: &[Finding]) -> Vec<Concern>;

/// Generate systemic concerns from aggregate statistics.
/// Looks for repeated patterns at the project level.
pub fn generate_systemic_concerns(findings: &[Finding], stats: &StateStats) -> Vec<Concern>;

/// Main entry point: run all three generators and deduplicate by fingerprint.
pub fn generate_all_concerns(findings: &[Finding], stats: &StateStats) -> Vec<Concern>;
```

---

### 3.7 policy module

`crates/genesis-deslop-engine/src/policy.rs`

Zone classification and per-zone detection policies.

```rust
use std::collections::{HashMap, HashSet};

/// A rule mapping file patterns to a zone.
pub struct ZoneRule {
    /// The zone to assign.
    pub zone: Zone,
    /// Patterns that match files in this zone.
    pub patterns: Vec<String>,
}

/// Policy for a zone: which detectors to skip or downgrade.
pub struct ZonePolicy {
    /// Detectors completely skipped in this zone (findings suppressed).
    pub skip_detectors: HashSet<String>,
    /// Detectors whose findings are downgraded one tier in this zone.
    pub downgrade_detectors: HashSet<String>,
    /// If true, findings in this zone are excluded from scoring entirely.
    pub exclude_from_score: bool,
}

/// Map from relative file path to its zone classification.
pub type FileZoneMap = HashMap<String, Zone>;
```

#### Pattern matching rules

Zone patterns use a simple matching syntax (NOT glob, NOT regex):

| Pattern format | Match semantics | Example |
|---|---|---|
| `/dir/` | Path contains this substring | `/test/` matches `src/test/utils.ts` |
| `.ext` | File has this extension | `.test.ts` matches `foo.test.ts` |
| `prefix_` | File basename starts with this | `test_` matches `test_utils.py` |
| `_suffix` | File basename ends with this (before extension) | `_test` matches `utils_test.go` |
| `name.py` | Exact basename match | `conftest.py` matches `tests/conftest.py` |

#### Default zone rules

```rust
/// Default zone rules applied before language-specific and config overrides.
pub fn default_zone_rules() -> Vec<ZoneRule> {
    vec![
        ZoneRule {
            zone: Zone::Test,
            patterns: vec![
                "/test/".into(), "/tests/".into(), "/__tests__/".into(),
                "/spec/".into(), "/specs/".into(),
                ".test.".into(), ".spec.".into(), "_test.".into(), "_spec.".into(),
                "test_".into(), "conftest.py".into(),
            ],
        },
        ZoneRule {
            zone: Zone::Config,
            patterns: vec![
                "tsconfig".into(), "webpack.config".into(), "vite.config".into(),
                "jest.config".into(), "eslint".into(), ".prettierrc".into(),
                "pyproject.toml".into(), "setup.cfg".into(), "setup.py".into(),
                "Cargo.toml".into(), "go.mod".into(),
            ],
        },
        ZoneRule {
            zone: Zone::Generated,
            patterns: vec![
                "/generated/".into(), "/__generated__/".into(),
                ".generated.".into(), ".g.dart".into(), ".g.cs".into(),
                "/migrations/".into(),
            ],
        },
        ZoneRule {
            zone: Zone::Script,
            patterns: vec![
                "/scripts/".into(), "/bin/".into(), "Makefile".into(),
                "Dockerfile".into(), ".sh".into(),
            ],
        },
        ZoneRule {
            zone: Zone::Vendor,
            patterns: vec![
                "/vendor/".into(), "/third_party/".into(), "/external/".into(),
            ],
        },
    ]
}
```

#### Default zone policies

| Zone | Skipped detectors | Downgraded detectors | Exclude from score |
|---|---|---|---|
| Production | (none) | (none) | false |
| Test | gods, unused, coupling, orphaned | complexity, smells | false |
| Config | large, complexity, smells, gods, coupling | (none) | false |
| Generated | (all mechanical detectors) | (none) | true |
| Script | complexity, gods, coupling | smells | false |
| Vendor | (all detectors) | (none) | true |

#### Functions

```rust
/// Classify all discovered files into zones.
///
/// Priority (highest to lowest):
/// 1. config.zone_overrides (user-specified)
/// 2. Language-specific zone rules
/// 3. Default zone rules
/// 4. Default: Zone::Production
pub fn classify_zones(
    files: &[PathBuf],
    root: &Path,
    config: &Config,
    lang_config: &LangConfig,
) -> FileZoneMap;

/// Get the zone policy for a given zone.
pub fn zone_policy(zone: Zone) -> ZonePolicy;

/// Check if a detector should run on a file given its zone.
pub fn should_run_detector(detector: &str, zone: Zone) -> bool;
```

---

## 4. genesis-deslop-lang

This crate provides the language plugin framework and all 28 language implementations. It depends on `genesis-deslop-core`.

### 4.1 framework module

`crates/genesis-deslop-lang/src/framework.rs`

#### Language configuration

```rust
/// Analysis depth level.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Depth {
    /// Only basic file-level metrics (LOC, extensions). Used for unsupported languages.
    Minimal,
    /// File-level + basic function extraction. Used for generic plugins.
    Shallow,
    /// Full analysis including dep graph, tree-sitter, extractors. Used for full-depth plugins.
    Standard,
}

/// Complete configuration for a language plugin.
#[derive(Debug, Clone)]
pub struct LangConfig {
    /// Language name (lowercase, e.g., "typescript", "python").
    pub name: String,
    /// File extensions this language handles (e.g., [".ts", ".tsx"]).
    pub extensions: Vec<String>,
    /// Additional glob patterns for file matching.
    pub globs: Vec<String>,
    /// Analysis depth.
    pub depth: Depth,
    /// External tool integrations.
    pub tools: Vec<ToolConfig>,
    /// Zone classification rules specific to this language.
    pub zone_rules: Vec<ZoneRule>,
    /// Markers that identify this language in a project (e.g., "package.json", "tsconfig.json").
    pub detect_markers: Vec<String>,
    /// Default source directory relative to project root.
    pub default_src: String,
    /// File patterns to exclude (language-specific).
    pub exclude: Vec<String>,
    /// LOC threshold for LargeFileDetector.
    pub large_threshold: u32,
    /// Cyclomatic complexity threshold for ComplexityDetector.
    pub complexity_threshold: u32,
    /// Default scan profile name.
    pub default_scan_profile: String,
    /// External test directory names (e.g., ["tests", "__tests__"]).
    pub external_test_dirs: Vec<String>,
}
```

#### Tool configuration

```rust
/// Configuration for an external tool integration.
#[derive(Debug, Clone)]
pub struct ToolConfig {
    /// Display name (e.g., "ESLint", "Ruff").
    pub name: String,
    /// Tier of findings from this tool.
    pub tier: Tier,
    /// Output format the tool produces.
    pub fmt: ToolOutputFormat,
    /// Internal ID for the detector this tool maps to.
    pub id: String,
    /// Shell command to run the tool.
    pub command: String,
    /// Shell command to auto-fix (if supported).
    pub fix_cmd: Option<String>,
    /// Whether this tool supports auto-fix.
    pub auto_fix: bool,
}

/// Output format parsers for external tools.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ToolOutputFormat {
    /// GNU-style: "file:line:col: message"
    Gnu,
    /// JSON array of objects.
    Json,
    /// ESLint JSON format.
    Eslint,
    /// RuboCop JSON format.
    Rubocop,
    /// Cargo/rustc JSON format.
    Cargo,
}
```

#### Tree-sitter specification

```rust
/// Tree-sitter grammar configuration for a language.
#[derive(Debug, Clone)]
pub struct TreeSitterSpec {
    /// Tree-sitter grammar name (e.g., "typescript", "python").
    pub grammar_name: String,
    /// File extensions this grammar handles.
    pub extensions: Vec<String>,
    /// S-expression query for extracting import statements.
    pub import_query: Option<String>,
    /// S-expression query for extracting class definitions.
    pub class_query: Option<String>,
    // Import resolution is handled by the LanguagePlugin trait method.
}
```

#### Extracted information types

```rust
/// Information about a function/method extracted from source code.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionInfo {
    /// Function name.
    pub name: String,
    /// Relative file path.
    pub file: String,
    /// 1-indexed line number of the function definition.
    pub line: usize,
    /// Lines of code in the function body.
    pub loc: usize,
    /// Parameter names (in order).
    pub params: Vec<String>,
    /// MD5 hash of the function body, truncated to 12 hex characters.
    /// Used for exact duplicate detection.
    pub body_hash: String,
    /// Return type annotation (if present in source).
    pub return_annotation: Option<String>,
}

/// Information about a class extracted from source code.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClassInfo {
    /// Class name.
    pub name: String,
    /// Relative file path.
    pub file: String,
    /// 1-indexed line number of the class definition.
    pub line: usize,
    /// Total lines of code in the class.
    pub loc: usize,
    /// Methods defined in this class.
    pub methods: Vec<FunctionInfo>,
    /// Attribute/field names.
    pub attributes: Vec<String>,
    /// Base class names (for inheritance analysis).
    pub base_classes: Vec<String>,
}
```

#### Complexity and god-class rules

```rust
/// A signal that contributes to cyclomatic complexity.
#[derive(Debug, Clone)]
pub struct ComplexitySignal {
    /// Human-readable label (e.g., "if-else", "for-loop").
    pub label: String,
    /// Regex pattern to match, or "compute" for AST-based computation.
    pub pattern: String,
    /// Weight of each occurrence.
    pub weight: u32,
    /// Threshold above which this signal contributes to complexity.
    pub threshold: u32,
}

/// A rule for detecting god classes/components.
#[derive(Debug, Clone)]
pub struct GodRule {
    /// Internal ID (e.g., "too_many_methods").
    pub id: String,
    /// Human-readable label.
    pub label: String,
    /// Threshold value that triggers the rule.
    pub threshold: u32,
    // The compute function is provided by the language plugin implementation.
}
```

#### Fixer types

```rust
/// Configuration for an auto-fixer.
#[derive(Debug, Clone)]
pub struct FixerConfig {
    /// Fixer name (e.g., "remove_unused", "lint_fix").
    pub name: String,
    /// Detector this fixer addresses.
    pub detector: String,
    /// Human-readable description.
    pub description: String,
}

/// Result of running a fixer.
#[derive(Debug, Clone)]
pub struct FixResult {
    /// Number of findings that were fixed.
    pub fixed_count: usize,
    /// Findings that were skipped (with reasons).
    pub skipped: Vec<SkipInfo>,
    /// Detailed log of what was done.
    pub details: Vec<String>,
}

#[derive(Debug, Clone)]
pub struct SkipInfo {
    pub finding_id: String,
    pub reason: String,
}
```

---

### 4.2 Plugin trait

```rust
/// Phases of a scan pipeline for a language.
pub struct Phase {
    pub name: String,
    pub description: String,
    pub detectors: Vec<String>,
    pub requires: Vec<String>,
}

/// Function/class extractors.
pub struct Extractors {
    pub extract_functions: Box<dyn Fn(&Path, &str) -> Vec<FunctionInfo> + Send + Sync>,
    pub extract_classes: Box<dyn Fn(&Path, &str) -> Vec<ClassInfo> + Send + Sync>,
    pub extract_imports: Box<dyn Fn(&Path, &str) -> Vec<String> + Send + Sync>,
}

/// Hooks for review integration.
pub struct ReviewHooks {
    pub pre_review: Option<Box<dyn Fn(&[PathBuf]) -> Result<()> + Send + Sync>>,
    pub post_review: Option<Box<dyn Fn(&[Finding]) -> Result<()> + Send + Sync>>,
}

/// Module move/rename support.
pub trait MoveModule: Send + Sync {
    /// Move a module from `from` to `to`, updating all imports.
    fn move_module(&self, root: &Path, from: &str, to: &str) -> Result<Vec<String>>;
}

/// Test coverage analysis support.
pub trait TestCoverageModule: Send + Sync {
    /// Map source files to their test files.
    fn source_to_test_map(&self, files: &[PathBuf]) -> HashMap<String, Option<String>>;
}

/// Every language plugin must implement this trait.
pub trait LanguagePlugin: Send + Sync {
    /// Get the language configuration.
    fn config(&self) -> &LangConfig;

    /// Get the scan phases in execution order.
    fn phases(&self) -> &[Phase];

    /// Get detector commands (language-specific detector implementations).
    /// Key = detector name, value = detection function.
    fn detect_commands(&self) -> HashMap<String, Box<dyn DetectCommand>>;

    /// Get function/class/import extractors.
    fn extractors(&self) -> Extractors;

    /// Get available fixers.
    fn fixers(&self) -> Vec<FixerConfig>;

    /// Get review hooks.
    fn review_hooks(&self) -> ReviewHooks;

    /// Get module move support (if any).
    fn move_module(&self) -> Option<Box<dyn MoveModule>>;

    /// Get test coverage module (if any).
    fn test_coverage_module(&self) -> Option<Box<dyn TestCoverageModule>>;
}

/// A language-specific detector command.
pub trait DetectCommand: Send + Sync {
    fn run(&self, ctx: &DetectorContext) -> Result<Vec<Finding>>;
}
```

---

### 4.3 Full-depth plugins

These 6 languages have complete `LanguagePlugin` implementations with full extractors, dep graphs, fixers, and language-specific detectors.

#### TypeScript plugin

`crates/genesis-deslop-lang/src/plugins/typescript.rs`

Configuration:
- Extensions: `[".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]`
- Detect markers: `["package.json", "tsconfig.json"]`
- Default src: `"src"`
- Large threshold: 500
- Complexity threshold: 15
- External test dirs: `["__tests__", "tests", "test"]`

Features:
- **21 detect commands**: lint, typecheck, format, complexity, large, duplicate, gods, coupling, cycle, unused, orphaned, security, naming, smells, test_coverage, interface, concerns, state_sync, context_nesting, hook_return_bloat, boolean_state_explosion
- **7 phases**: lint, typecheck, extract, analyze, detect, review, report
- **15 detector modules**: All standard detectors plus React-specific:
  - `state_sync`: Detects React components where state is derived from props but not synced (stale closures, missing deps in useEffect).
  - `context_nesting`: Detects excessive React context nesting (>3 levels).
  - `hook_return_bloat`: Detects custom hooks returning too many values (>5).
  - `boolean_state_explosion`: Detects components with >4 boolean useState hooks (suggests a state machine).
- **8 fixer modules**: lint_fix, format, remove_unused, rename_symbol, organize_imports, convert_any, extract_component, simplify_boolean_state
- **28 smell checks**: Boolean prop explosion, excessive useState, nested ternaries, callback hell (>3 levels), any-type proliferation, magic numbers, long parameter lists (>5), deeply nested JSX (>5 levels), excessive re-renders, missing error boundaries, prop drilling (>3 levels), unused imports, barrel file bloat, string literal duplication, hardcoded URLs, console.log in production, TODO/FIXME accumulation, empty catch blocks, non-null assertions, type assertions, implicit any, switch without default, large switch statements (>10 cases), dead code after return, unreachable code, assignment in condition, for-in on arrays, prototype pollution patterns.
- **10 security checks**: `dangerouslySetInnerHTML`, `eval()`, hardcoded API keys/tokens (regex: `/(?:api[_-]?key|secret|token|password)\s*[:=]\s*['"][^'"]{8,}/i`), `innerHTML` assignment, `document.write`, SQL string concatenation, `child_process.exec` with template literals, `new Function()`, unvalidated URL redirect, `crypto.createHash('md5')`.
- **Knip adapter**: Wraps the `knip` tool for dead export detection. Parses Knip JSON output into unused findings.
- **Tree-sitter**: Uses `tree-sitter-typescript` grammar for import/export extraction and AST analysis.

#### Python plugin

`crates/genesis-deslop-lang/src/plugins/python.rs`

Configuration:
- Extensions: `[".py", ".pyi"]`
- Detect markers: `["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"]`
- Default src: `"."`
- Large threshold: 300
- Complexity threshold: 25
- External test dirs: `["tests", "test"]`

Features:
- **14 detect commands**: complexity, large, duplicate, gods, coupling, cycle, unused, orphaned, security, naming, smells, test_coverage, interface, concerns
- **13 phases**: extract, analyze_imports, build_dep_graph, detect_duplicates, detect_complexity, detect_large, detect_gods, detect_coupling, detect_cycles, detect_security, detect_smells, detect_test_coverage, generate_concerns
- **32 smell checks**: Bare except (`except:`), mutable default arguments (`def f(x=[])`), wildcard imports (`from foo import *`), nested functions > 2 deep, class with no methods (should be dataclass/namedtuple), global state mutation, string concatenation in loops, missing `__init__` in package, redundant else after return, `type()` instead of `isinstance()`, single-character variable names (outside loops), over-broad exception handling, long comprehensions (>3 clauses), deeply nested dicts (>3 levels), unnecessary lambda, property without setter when mutated, classmethod that doesn't use cls, staticmethod that should be function, unused function arguments, flag arguments (bool params), hardcoded file paths, print statements in production, assert in production, `exec()` usage, `import *` in `__init__`, circular import patterns, dict key access without `.get()`, raw string SQL, f-string with no variables, unused list comprehension, mutable class attributes, `__del__` implementation.
- **Bandit adapter**: Runs `bandit -f json` if available, parses output into security findings.
- **Ruff adapter**: Runs `ruff check --output-format json` with 14 rule categories enabled.
- **Responsibility cohesion**: Graph-based analysis of function call relationships within a file. Low cohesion (disconnected subgraphs) suggests mixed responsibilities.
- **Dict key flow analysis**: Tracks dictionary key access patterns to detect inconsistent key naming and missing key handling.
- **Mutable state detection**: Identifies classes and modules that mutate shared state (global variables, class-level mutables).
- **Tree-sitter**: Uses `tree-sitter-python` grammar.

#### C# plugin

`crates/genesis-deslop-lang/src/plugins/csharp.rs`

Configuration:
- Extensions: `[".cs"]`
- Detect markers: `["*.csproj", "*.sln"]`
- Default src: `"src"`
- Large threshold: 500
- Complexity threshold: 20
- External test dirs: `["Tests", "tests", "*.Tests"]`

Features:
- **6 commands**: complexity, large, gods, coupling, security, smells
- **Corroboration gating**: A finding must have at least 2 independent signals before it is emitted. This reduces false positives in C# where patterns can be ambiguous.
- **Roslyn dependency graph**: Parses `using` directives and maps them to files via namespace-to-file heuristic (namespace `Foo.Bar` → `Foo/Bar.cs` or `Foo/Bar/*.cs`). Falls back to regex matching when namespace resolution fails.
- **4 security rules**: SQL string concatenation (`string.Format` or `$"..."` in SQL context), `Process.Start` with unsanitized input, `[AllowAnonymous]` on controllers handling sensitive data, hardcoded connection strings.
- **Extractors with CSharpExtractorDeps**: The C# extractor requires additional context (solution file, project references) which is provided via a `CSharpExtractorDeps` struct.

#### Dart plugin

`crates/genesis-deslop-lang/src/plugins/dart.rs`

Configuration:
- Extensions: `[".dart"]`
- Detect markers: `["pubspec.yaml"]`
- Default src: `"lib"`
- Large threshold: 500
- Complexity threshold: 16
- External test dirs: `["test"]`

Features:
- **Pubspec integration**: Reads `pubspec.yaml` for dependency information and project name.
- **Barrel file resolution**: Detects `index.dart` barrel files and resolves re-exports to their source files.
- **Import/export/part parsing**: Handles Dart's `import`, `export`, `part`, and `part of` directives, including `show`/`hide` combinators.

#### GDScript plugin

`crates/genesis-deslop-lang/src/plugins/gdscript.rs`

Configuration:
- Extensions: `[".gd"]`
- Detect markers: `["project.godot"]`
- Default src: `"."`
- Large threshold: 500
- Complexity threshold: 16
- External test dirs: `["test"]`

Features:
- **Indentation-based block parsing**: GDScript uses Python-style indentation. The parser tracks indent levels to determine function/class boundaries.
- **Godot project root detection**: Looks for `project.godot` file to establish the project root (may differ from scan root).
- **Resource path patterns**: Matches `preload("res://...")`, `load("res://...")`, and `extends "res://..."` patterns for dependency graph construction. `res://` paths are resolved relative to the Godot project root.

#### Go plugin

`crates/genesis-deslop-lang/src/plugins/go.rs`

Configuration:
- Extensions: `[".go"]`
- Detect markers: `["go.mod", "go.sum"]`
- Default src: `"."`
- Large threshold: 500
- Complexity threshold: 15
- External test dirs: `[]` (Go uses `_test.go` suffix)

Features:
- **7 complexity signals**: `if`, `else if`, `for`, `switch`, `select`, `case`, `&&`/`||` (boolean operators).
- **Sophisticated brace tracking**: Distinguishes between `struct{}` / `interface{}` literals (which are not function bodies) and actual function/method bodies when counting nesting depth. Tracks `struct{` and `interface{` keywords followed by `{` to avoid false positives.
- **Stub dep graph**: Go's module system makes file-level dep graphs less meaningful. Returns an empty dep graph; coupling analysis relies on package-level imports instead.
- **Test file handling**: Files ending in `_test.go` are automatically classified as Zone::Test. When mapping source to test files, `foo.go` maps to `foo_test.go` in the same directory.

---

### 4.4 Generic plugins

22 languages are implemented via a `generic_lang()` factory that produces a `LanguagePlugin` with `Depth::Shallow` analysis.

```rust
/// Create a generic language plugin from minimal configuration.
pub fn generic_lang(
    name: &str,
    extensions: &[&str],
    detect_markers: &[&str],
    tools: Vec<ToolConfig>,
    zone_rules: Vec<ZoneRule>,
) -> Box<dyn LanguagePlugin>;
```

Generic plugins provide:
- File-level LOC counting
- Regex-based function extraction (language-specific regex)
- Basic complexity counting (keyword counting)
- No dep graph (empty graph)
- No tree-sitter (regex fallback)
- External tool integration (if configured)

#### Generic plugins with auto-fix tools

| Language | Tool | Fix command |
|---|---|---|
| JavaScript | ESLint | `eslint --fix` |
| Kotlin | ktlint | `ktlint --format` |
| Ruby | RuboCop | `rubocop --auto-correct` |
| Rust | cargo clippy | `cargo clippy --fix --allow-dirty` |
| Swift | SwiftLint | `swiftlint --fix` |

#### Generic plugins with multiple tools

| Language | Tool 1 | Tool 2 |
|---|---|---|
| Rust | `cargo clippy` (Cargo format, Tier::QuickFix) | `cargo check` (Cargo format, Tier::QuickFix) |

#### Complete list of generic plugins

| # | Language | Extensions | Markers |
|---|---|---|---|
| 1 | Bash | `.sh`, `.bash` | (none) |
| 2 | Clojure | `.clj`, `.cljs`, `.cljc`, `.edn` | `project.clj`, `deps.edn` |
| 3 | C++ | `.cpp`, `.cc`, `.cxx`, `.h`, `.hpp`, `.hxx` | `CMakeLists.txt`, `Makefile` |
| 4 | Elixir | `.ex`, `.exs` | `mix.exs` |
| 5 | Erlang | `.erl`, `.hrl` | `rebar.config` |
| 6 | F# | `.fs`, `.fsi`, `.fsx` | `*.fsproj` |
| 7 | Haskell | `.hs`, `.lhs` | `*.cabal`, `stack.yaml` |
| 8 | Java | `.java` | `pom.xml`, `build.gradle` |
| 9 | JavaScript | `.js`, `.jsx`, `.mjs`, `.cjs` | `package.json` |
| 10 | Kotlin | `.kt`, `.kts` | `build.gradle.kts` |
| 11 | Lua | `.lua` | (none) |
| 12 | Nim | `.nim`, `.nims` | `*.nimble` |
| 13 | OCaml | `.ml`, `.mli` | `dune-project` |
| 14 | Perl | `.pl`, `.pm` | `Makefile.PL`, `cpanfile` |
| 15 | PHP | `.php` | `composer.json` |
| 16 | PowerShell | `.ps1`, `.psm1`, `.psd1` | (none) |
| 17 | R | `.R`, `.r`, `.Rmd` | `DESCRIPTION` |
| 18 | Ruby | `.rb`, `.rake` | `Gemfile` |
| 19 | Rust | `.rs` | `Cargo.toml` |
| 20 | Scala | `.scala`, `.sc` | `build.sbt` |
| 21 | Swift | `.swift` | `Package.swift` |
| 22 | Zig | `.zig` | `build.zig` |

---

## 5. genesis-deslop-intel

This crate provides the intelligence layer: review management, narrative generation, and integrity checking. It depends on `genesis-deslop-core` and `genesis-deslop-engine`.

### 5.1 review module

`crates/genesis-deslop-intel/src/review.rs`

The review module implements a bias-resistant review system where human or AI reviewers assess subjective quality dimensions without seeing existing scores.

#### Blind packet generation

```rust
/// A review packet sent to reviewers. Contains NO score information
/// to prevent anchoring bias.
pub struct BlindReviewPacket {
    /// Unique session ID.
    pub session_id: String,
    /// Findings grouped by dimension, with scores stripped.
    pub dimension_batches: HashMap<String, Vec<NormalizedBatchFinding>>,
    /// File content snippets for context.
    pub code_context: HashMap<String, String>,
    /// Timestamp of packet generation.
    pub generated_at: String,
    /// SHA-256 hash of the packet contents (for provenance verification).
    pub content_hash: String,
}

/// A finding normalized for review, with all score information removed.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NormalizedBatchFinding {
    /// Dimension this finding relates to.
    pub dimension: String,
    /// Unique identifier within the batch.
    pub identifier: String,
    /// Summary description.
    pub summary: String,
    /// Severity level (independent of score impact).
    pub severity: String,
    /// Confidence level.
    pub confidence: String,
    /// Related files for context.
    pub related_files: Vec<String>,
    /// Suggested remediation approach.
    pub remediation: String,
}
```

#### 22 dimension definitions

Loaded from a static `dimensions.json` (embedded at compile time). Each dimension has:
- Name, display name, description
- Category (mechanical or subjective)
- Weight
- Review prompts (questions to ask reviewers)
- Scoring rubric (what constitutes 0, 25, 50, 75, 100)

#### Dimension merge scorer

```rust
/// Merges multiple review scores for a dimension into a single score.
pub struct DimensionMergeScorer;

impl DimensionMergeScorer {
    /// Blend formula: 70% weighted mean + 30% floor (lowest score).
    /// This ensures the worst assessment has significant influence.
    ///
    /// Max penalty cap: 24.0 points. No single review can reduce a
    /// dimension score by more than 24 points.
    pub fn merge_scores(scores: &[f64], weights: &[f64]) -> f64 {
        let weighted_mean = weighted_average(scores, weights);
        let floor = scores.iter().cloned().fold(f64::INFINITY, f64::min);
        let blended = 0.70 * weighted_mean + 0.30 * floor;

        // Apply max penalty cap
        let uncapped = 100.0 - blended;
        let capped_penalty = uncapped.min(24.0);
        100.0 - capped_penalty
    }
}
```

#### Trust model

```rust
/// Trust level for a review source. Determines how much weight the review carries.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum TrustLevel {
    /// Automated findings only, no human review (weight: 0.3).
    FindingsOnly,
    /// Manual override by admin (weight: 0.5).
    ManualOverride,
    /// External reviewer with attestation (weight: 0.8).
    AttestedExternal,
    /// Internal trusted reviewer (weight: 1.0).
    TrustedInternal,
}
```

#### Provenance verification

Every review packet and review result includes a SHA-256 hash of its content. On import, the hash is verified to ensure the review was not tampered with.

```rust
/// Verify that a review result matches its provenance hash.
pub fn verify_provenance(result: &ReviewResult, expected_hash: &str) -> bool;
```

#### External review sessions

```rust
/// An external review session.
pub struct ReviewSession {
    /// Unique session token.
    pub token: String,
    /// The blind packet sent for review.
    pub packet: BlindReviewPacket,
    /// ISO 8601 expiry timestamp.
    pub expires_at: String,
    /// Review results (populated when review is submitted).
    pub results: Option<ReviewResult>,
}
```

#### Conceptual deduplication

When merging findings into review batches, near-duplicate findings are deduplicated using Jaccard word-set similarity:

```rust
/// Compute Jaccard similarity between two text strings based on word sets.
/// Returns a value in [0.0, 1.0].
pub fn jaccard_word_similarity(a: &str, b: &str) -> f64 {
    let set_a: HashSet<&str> = a.split_whitespace().collect();
    let set_b: HashSet<&str> = b.split_whitespace().collect();
    let intersection = set_a.intersection(&set_b).count() as f64;
    let union = set_a.union(&set_b).count() as f64;
    if union == 0.0 { 0.0 } else { intersection / union }
}
```

Threshold for deduplication: 0.7 (70% word overlap → considered duplicate, keep the one with higher confidence).

---

### 5.2 narrative module

`crates/genesis-deslop-intel/src/narrative.rs`

The narrative module generates human-readable progress reports and actionable work plans.

#### Narrative phases

```rust
/// The current project phase, determined by scan history.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NarrativePhase {
    /// First scan ever (scan_count == 1).
    FirstScan,
    /// Score dropped by more than 0.5 since last scan.
    Regression,
    /// Score changed by less than ±0.5 for 3+ consecutive scans.
    Stagnation,
    /// Scans 2-5, score is rising.
    EarlyMomentum,
    /// Score is above 93.
    Maintenance,
    /// Score is above 80 but below 93.
    Refinement,
    /// Default fallback for all other situations.
    MiddleGrind,
}

impl NarrativePhase {
    /// Determine the current phase from scan history.
    pub fn detect(history: &[ScanHistoryEntry], scan_count: u32) -> Self {
        if scan_count == 1 {
            return NarrativePhase::FirstScan;
        }
        if history.len() >= 2 {
            let latest = &history[history.len() - 1];
            let previous = &history[history.len() - 2];
            let delta = latest.overall_score - previous.overall_score;
            if delta < -0.5 {
                return NarrativePhase::Regression;
            }
        }
        if history.len() >= 3 {
            let recent = &history[history.len()-3..];
            let all_stagnant = recent.windows(2).all(|w|
                (w[1].overall_score - w[0].overall_score).abs() <= 0.5
            );
            if all_stagnant {
                return NarrativePhase::Stagnation;
            }
        }
        let latest_score = history.last().map(|h| h.overall_score).unwrap_or(0.0);
        if latest_score > 93.0 {
            return NarrativePhase::Maintenance;
        }
        if latest_score > 80.0 {
            return NarrativePhase::Refinement;
        }
        if scan_count <= 5 {
            if history.len() >= 2 {
                let first = &history[0];
                let latest = &history[history.len() - 1];
                if latest.overall_score > first.overall_score {
                    return NarrativePhase::EarlyMomentum;
                }
            }
        }
        NarrativePhase::MiddleGrind
    }
}
```

#### Action items

```rust
/// Type of action recommended.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[repr(u8)]
pub enum ActionType {
    /// Process issues from the work queue.
    IssueQueue = 0,
    /// Run auto-fix tools.
    AutoFix = 1,
    /// Reorganize file structure.
    Reorganize = 2,
    /// Refactor code.
    Refactor = 3,
    /// Manual fix required.
    ManualFix = 4,
    /// Review technical debt.
    DebtReview = 5,
}

/// A single recommended action.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActionItem {
    /// Type of action.
    pub action_type: ActionType,
    /// Detector that produced the underlying findings.
    pub detector: String,
    /// Estimated score impact if this action is completed.
    pub impact: f64,
    /// Human-readable description.
    pub description: String,
    /// Affected files.
    pub files: Vec<String>,
    /// Fixer module name (if auto-fixable).
    pub fixer: Option<String>,
    /// Cluster name (if part of a cluster).
    pub cluster: Option<String>,
}
```

#### Lane system

Actions are grouped into parallelizable workstreams ("lanes") using union-find:

```rust
/// A workstream of related actions that should be done together.
pub struct Lane {
    /// Lane name.
    pub name: String,
    /// Actions in this lane.
    pub actions: Vec<ActionItem>,
    /// Total estimated impact.
    pub total_impact: f64,
}
```

Lane assignment algorithm:
1. Build a graph where nodes are actions and edges connect actions that share files.
2. Use union-find to compute connected components.
3. Name each component based on its dominant action type:
   - If all actions are AutoFix → "cleanup"
   - If dominant action is Reorganize → "restructure"
   - If dominant action is Refactor → "refactor_N" (numbered)
   - If dominant action is ManualFix with test_coverage → "test_coverage"
   - If dominant action is DebtReview → "debt_review"
   - Otherwise → "mixed_N"

#### Structural merge

When generating action items, related structural detectors are merged:

```rust
/// Detectors whose findings are merged into combined structural actions.
const STRUCTURAL_MERGE: &[&str] = &["large", "complexity", "gods", "concerns"];
```

A file with findings from multiple structural detectors gets a single "restructure" action rather than separate actions for each.

#### Detector cascade

```rust
/// When a detector's findings are resolved, cascade to related detectors.
/// Key = primary detector, Value = detectors that may be auto-resolved.
const DETECTOR_CASCADE: &[(&str, &[&str])] = &[
    ("logs", &["unused"]),
    ("smells", &["unused"]),
];
```

Example: Fixing a smell that was the only reason a function was imported may auto-resolve the "unused" finding for that function.

#### Reminder decay

```rust
/// Suppress repeated reminders after this many occurrences.
const REMINDER_DECAY_THRESHOLD: u32 = 3;

/// Some reminders should never decay (always shown).
pub struct Reminder {
    pub message: String,
    pub occurrence_count: u32,
    pub no_decay: bool,
}
```

---

### 5.3 integrity module

`crates/genesis-deslop-intel/src/integrity.rs`

Anti-gaming checks to ensure scores are honest and meaningful.

```rust
/// Run all integrity checks and return violations.
pub fn check_integrity(state: &StateModel, config: &Config) -> Vec<IntegrityViolation>;

#[derive(Debug, Clone)]
pub struct IntegrityViolation {
    pub check: String,
    pub message: String,
    pub severity: String,   // "warning" or "error"
}
```

#### Target-match detection

```rust
/// Check if subjective scores suspiciously match the target.
///
/// If the overall score is within SUBJECTIVE_TARGET_MATCH_TOLERANCE (0.05)
/// of target_strict_score for SUBJECTIVE_TARGET_RESET_THRESHOLD (2) or more
/// subjective dimensions, flag as suspicious.
pub fn check_target_match(state: &StateModel, config: &Config) -> Option<IntegrityViolation>;
```

#### Placeholder detection

```rust
/// Check for placeholder content in finding summaries and details.
/// Patterns: "TODO", "FIXME", "placeholder", "lorem ipsum", repeated characters.
pub fn check_placeholders(state: &StateModel) -> Vec<IntegrityViolation>;
```

#### Wontfix accountability

```rust
/// Count Wontfix findings and their impact on strict vs lenient score gap.
/// Flag if the gap exceeds a threshold (suggests excessive Wontfix abuse).
pub fn check_wontfix_accountability(state: &StateModel) -> Option<IntegrityViolation>;
```

#### Subjective target reset

```rust
/// When SUBJECTIVE_TARGET_RESET_THRESHOLD (2) subjective dimensions
/// match the target score within tolerance, reset those dimension
/// assessments to force re-review.
pub fn maybe_reset_subjective(state: &mut StateModel, config: &Config) -> bool;
```

---

## 6. genesis-deslop-cli

This crate provides the command-line interface. It depends on all other crates and produces the `gdeslop` binary.

### 6.1 Command structure

`crates/genesis-deslop-cli/src/main.rs`

```rust
use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(
    name = "gdeslop",
    version,
    about = "Genesis Deslop -- Codebase Quality Intelligence"
)]
struct Cli {
    #[command(subcommand)]
    command: Commands,

    /// Disable color output.
    #[arg(long, global = true)]
    no_color: bool,

    /// Output in JSON format.
    #[arg(long, global = true)]
    json: bool,
}

#[derive(Subcommand)]
enum Commands {
    /// Run a full scan of the codebase.
    Scan(ScanArgs),

    /// Show current status and scores.
    Status(StatusArgs),

    /// Show details of a specific finding or detector.
    Show(ShowArgs),

    /// Show the next item to work on.
    Next(NextArgs),

    /// Add findings to the ignore list.
    Ignore(IgnoreArgs),

    /// Add paths to the exclude list.
    Exclude(ExcludeArgs),

    /// Run auto-fixers.
    Fix(FixArgs),

    /// Manage the work plan.
    Plan(PlanArgs),

    /// Run a specific detector.
    Detect(DetectArgs),

    /// Show the dependency tree.
    Tree(TreeArgs),

    /// Generate visualizations.
    Viz(VizArgs),

    /// Move/rename a module.
    #[command(name = "move")]
    Move(MoveArgs),

    /// Show or set zone classifications.
    Zone(ZoneArgs),

    /// Manage reviews.
    Review(ReviewArgs),

    /// Show or modify configuration.
    Config(ConfigArgs),

    /// Developer/debug commands.
    Dev(DevArgs),

    /// Update AI skill prompts.
    UpdateSkill(UpdateSkillArgs),

    /// List supported languages.
    Langs(LangsArgs),
}
```

#### 18 commands detail

##### scan

```rust
#[derive(clap::Args)]
pub struct ScanArgs {
    /// Path to scan (default: current directory).
    #[arg(default_value = ".")]
    path: PathBuf,
    /// Language to use (auto-detect if not specified).
    #[arg(long)]
    lang: Option<String>,
    /// Only run specific detectors (comma-separated).
    #[arg(long)]
    only: Option<String>,
    /// Skip specific detectors (comma-separated).
    #[arg(long)]
    skip: Option<String>,
    /// Force rescan even if recent.
    #[arg(long)]
    force: bool,
    /// Generate scorecard image.
    #[arg(long)]
    scorecard: bool,
}
```

##### status

```rust
#[derive(clap::Args)]
pub struct StatusArgs {
    /// Show detailed dimension breakdown.
    #[arg(long)]
    detail: bool,
    /// Show strict scores.
    #[arg(long)]
    strict: bool,
    /// Show verified strict scores.
    #[arg(long)]
    verified: bool,
    /// Show scan history.
    #[arg(long)]
    history: bool,
}
```

##### show

```rust
#[derive(clap::Args)]
pub struct ShowArgs {
    /// Finding ID, detector name, or file path.
    target: String,
    /// Show full detail (not abbreviated).
    #[arg(long)]
    full: bool,
    /// Show code context around the finding.
    #[arg(long)]
    context: bool,
    /// Number of context lines.
    #[arg(long, default_value = "3")]
    context_lines: usize,
}
```

##### next

```rust
#[derive(clap::Args)]
pub struct NextArgs {
    /// Number of items to show.
    #[arg(short = 'n', long, default_value = "5")]
    count: usize,
    /// Filter by tier.
    #[arg(long)]
    tier: Option<u8>,
    /// Include explanation.
    #[arg(long)]
    explain: bool,
    /// Show clustered items.
    #[arg(long)]
    cluster: bool,
}
```

##### plan

```rust
#[derive(clap::Args)]
pub struct PlanArgs {
    #[command(subcommand)]
    action: PlanAction,
}

#[derive(Subcommand)]
enum PlanAction {
    /// Show the current plan.
    Show(PlanShowArgs),
    /// Build/refresh the work queue.
    Queue(PlanQueueArgs),
    /// Reset the plan to default.
    Reset,
    /// Move an item in the queue.
    Move(PlanMoveArgs),
    /// Set description on an item.
    Describe(PlanDescribeArgs),
    /// Add a note to an item.
    Note(PlanNoteArgs),
    /// Focus on a cluster.
    Focus(PlanFocusArgs),
    /// Skip an item.
    Skip(PlanSkipArgs),
    /// Unskip an item.
    Unskip(PlanUnskipArgs),
    /// Reopen a resolved item.
    Reopen(PlanReopenArgs),
    /// Mark an item as done.
    Done(PlanDoneArgs),
    /// Manage clusters.
    Cluster(PlanClusterArgs),
}

#[derive(clap::Args)]
pub struct PlanClusterArgs {
    #[command(subcommand)]
    action: ClusterAction,
}

#[derive(Subcommand)]
enum ClusterAction {
    /// Create a new cluster.
    Create(ClusterCreateArgs),
    /// Add findings to a cluster.
    Add(ClusterAddArgs),
    /// Remove findings from a cluster.
    Remove(ClusterRemoveArgs),
    /// Delete a cluster.
    Delete(ClusterDeleteArgs),
    /// Move a finding between clusters.
    Move(ClusterMoveArgs),
    /// Show cluster details.
    Show(ClusterShowArgs),
    /// List all clusters.
    List,
}
```

##### Other commands

- **ignore**: `IgnoreArgs { pattern: String, reason: Option<String> }` — Add to config.ignore
- **exclude**: `ExcludeArgs { pattern: String }` — Add to config.exclude
- **fix**: `FixArgs { detector: Option<String>, dry_run: bool, finding: Option<String> }` — Run auto-fixers
- **detect**: `DetectArgs { detector: String, path: Option<PathBuf> }` — Run single detector
- **tree**: `TreeArgs { path: Option<PathBuf>, depth: Option<usize>, format: Option<String> }` — Dependency tree
- **viz**: `VizArgs { kind: VizKind, output: Option<PathBuf> }` where `VizKind` = { Treemap, Scorecard, History }
- **move**: `MoveArgs { from: String, to: String, dry_run: bool }` — Module move
- **zone**: `ZoneArgs { file: Option<String>, set: Option<String> }` — Show/set zones
- **review**: `ReviewArgs { action: ReviewAction }` — Start, submit, import review
- **config**: `ConfigArgs { key: Option<String>, value: Option<String>, list: bool }` — Show/set config
- **dev**: `DevArgs { action: DevAction }` — Debug: dump state, clear cache, benchmark
- **update-skill**: `UpdateSkillArgs { output: Option<PathBuf> }` — Generate AI skill prompt
- **langs**: `LangsArgs { detail: bool }` — List supported languages

---

### 6.2 Output rendering

#### Scorecard PNG

Feature-gated behind `scorecard-png`.

```rust
/// Generate a scorecard PNG image.
///
/// Layout:
/// - Canvas: 800x400px, warm cream background (#FDF6E3).
/// - Left panel (300px wide): Large score number (overall_score), project name,
///   scan date, scan count.
/// - Right panel (500px wide): 2-column table of dimension scores.
///   Max 20 dimensions displayed. Elegance sub-dimensions collapsed into
///   a single "Elegance" row showing average.
///
/// Color coding for scores:
/// - >= 90: Green (#2AA198)
/// - >= 70: Yellow (#B58900)
/// - < 70: Red (#DC322F)
///
/// Font: embedded monospace font (via rusttype).
pub fn render_scorecard(state: &StateModel, output: &Path) -> Result<()>;
```

#### Treemap HTML

```rust
/// Generate an interactive treemap HTML file using D3.js.
///
/// The treemap shows files sized by LOC and colored by finding density.
/// Uses an embedded D3.js template with data injected as a JSON variable.
pub fn render_treemap(state: &StateModel, files: &[PathBuf], output: &Path) -> Result<()>;
```

#### Tree text (LLM-readable)

```rust
/// Generate a text-based dependency tree optimized for LLM consumption.
///
/// Format:
/// ```
/// src/
///   ├── engine.ts (12 findings, score: 65)
///   │   ├── imports: utils.ts, config.ts
///   │   └── imported_by: main.ts, api.ts
///   ├── utils.ts (3 findings, score: 88)
///   ...
/// ```
pub fn render_tree_text(state: &StateModel, dep_graph: &DepGraph) -> String;
```

---

## 7. Feature Flags

Feature flags control optional dependencies and capabilities.

```toml
# Workspace-level feature configuration
# (Applied in crates that need them)

[features]
default = ["tree-sitter", "scorecard-png"]

# Tree-sitter parsing for accurate AST analysis.
# Without this, falls back to regex-based extraction.
tree-sitter = [
    "dep:tree-sitter",
    "dep:tree-sitter-typescript",
    "dep:tree-sitter-python",
    "dep:tree-sitter-c-sharp",
    "dep:tree-sitter-go",
    "dep:tree-sitter-javascript",
]

# Scorecard PNG image generation.
scorecard-png = [
    "dep:image",
    "dep:imageproc",
    "dep:rusttype",
]

# External review batch support (requires async HTTP).
review-batch = [
    "dep:tokio",
    "dep:reqwest",
]

# Enable all 28 language plugins (some may have additional deps).
full-languages = []
```

---

## 8. Dependencies

### Required dependencies

| Crate | Version | Purpose |
|---|---|---|
| `serde` | 1.x | Serialization/deserialization (with `derive` feature) |
| `serde_json` | 1.x | JSON state/plan files |
| `clap` | 4.x | CLI argument parsing (with `derive` feature) |
| `toml` | 0.8.x | Config file parsing |
| `thiserror` | 2.x | Error type derivation |
| `anyhow` | 1.x | Error context and propagation |
| `phf` | 0.11.x | Compile-time hash maps (registry) |
| `regex` | 1.x | Pattern matching in detectors |
| `chrono` | 0.4.x | Timestamp handling (with `serde` feature) |
| `sha2` | 0.10.x | SHA-256 for fingerprints and provenance |
| `md-5` | 0.10.x | MD5 for function body hashing |
| `petgraph` | 0.6.x | Graph algorithms (Tarjan SCC, union-find) |
| `similar` | 2.x | Sequence matching for near-duplicate detection |

### Optional dependencies

| Crate | Feature gate | Purpose |
|---|---|---|
| `tree-sitter` | `tree-sitter` | Incremental parsing framework |
| `tree-sitter-typescript` | `tree-sitter` | TypeScript grammar |
| `tree-sitter-python` | `tree-sitter` | Python grammar |
| `tree-sitter-c-sharp` | `tree-sitter` | C# grammar |
| `tree-sitter-go` | `tree-sitter` | Go grammar |
| `tree-sitter-javascript` | `tree-sitter` | JavaScript grammar |
| `image` | `scorecard-png` | Image manipulation |
| `imageproc` | `scorecard-png` | Image processing operations |
| `rusttype` | `scorecard-png` | Font rendering |
| `tokio` | `review-batch` | Async runtime |
| `reqwest` | `review-batch` | HTTP client |

---

## 9. Error Types

All errors use a structured error code system. Each crate defines its errors using `thiserror`.

### Error code ranges

| Range | Category | Crate |
|---|---|---|
| GD-1xxx | Configuration errors | `genesis-deslop-core` |
| GD-2xxx | State/persistence errors | `genesis-deslop-engine` |
| GD-3xxx | Scoring errors | `genesis-deslop-engine` |
| GD-4xxx | Detection errors | `genesis-deslop-engine` |
| GD-5xxx | Language plugin errors | `genesis-deslop-lang` |
| GD-6xxx | Review/intelligence errors | `genesis-deslop-intel` |
| GD-7xxx | CLI/command errors | `genesis-deslop-cli` |

### Error definitions

```rust
// genesis-deslop-core/src/error.rs

#[derive(Debug, thiserror::Error)]
pub enum CoreError {
    #[error("GD-1001: Config not found: {path}")]
    ConfigNotFound { path: PathBuf },

    #[error("GD-1002: Config parse error: {reason}")]
    ConfigParseError { reason: String },

    #[error("GD-1003: Invalid config value for '{key}': {reason}")]
    ConfigInvalidValue { key: String, reason: String },

    #[error("GD-1004: Config merge conflict for '{key}'")]
    ConfigMergeConflict { key: String },
}

// genesis-deslop-engine/src/error.rs

#[derive(Debug, thiserror::Error)]
pub enum EngineError {
    #[error("GD-2001: State file corrupt: {reason}")]
    StateCorrupt { reason: String },

    #[error("GD-2002: State version mismatch: expected {expected}, found {found}")]
    StateVersionMismatch { expected: u32, found: u32 },

    #[error("GD-2003: State write failed: {reason}")]
    StateWriteFailed { reason: String },

    #[error("GD-2004: Plan file corrupt: {reason}")]
    PlanCorrupt { reason: String },

    #[error("GD-2005: Finding not found: {id}")]
    FindingNotFound { id: String },

    #[error("GD-2006: Cluster not found: {name}")]
    ClusterNotFound { name: String },

    #[error("GD-3001: Scoring computation failed: {reason}")]
    ScoringFailed { reason: String },

    #[error("GD-3002: Unknown dimension: {name}")]
    UnknownDimension { name: String },

    #[error("GD-3003: Invalid score mode")]
    InvalidScoreMode,

    #[error("GD-4001: Detector '{name}' failed: {reason}")]
    DetectorFailed { name: String, reason: String },

    #[error("GD-4002: Unknown detector: {name}")]
    UnknownDetector { name: String },

    #[error("GD-4003: Detector context missing required field: {field}")]
    DetectorContextMissing { field: String },
}

// genesis-deslop-lang/src/error.rs

#[derive(Debug, thiserror::Error)]
pub enum LangError {
    #[error("GD-5001: Language not supported: {name}")]
    UnsupportedLanguage { name: String },

    #[error("GD-5002: Language detection failed for path: {path}")]
    DetectionFailed { path: PathBuf },

    #[error("GD-5003: Extractor failed for {lang}: {reason}")]
    ExtractorFailed { lang: String, reason: String },

    #[error("GD-5004: Tool '{tool}' not found (required for {lang})")]
    ToolNotFound { tool: String, lang: String },

    #[error("GD-5005: Tool '{tool}' execution failed: {reason}")]
    ToolExecutionFailed { tool: String, reason: String },

    #[error("GD-5006: Tree-sitter parse failed for {file}: {reason}")]
    TreeSitterParseFailed { file: String, reason: String },
}

// genesis-deslop-intel/src/error.rs

#[derive(Debug, thiserror::Error)]
pub enum IntelError {
    #[error("GD-6001: Review session expired: {session_id}")]
    ReviewSessionExpired { session_id: String },

    #[error("GD-6002: Review provenance verification failed")]
    ProvenanceVerificationFailed,

    #[error("GD-6003: Review import failed: {reason}")]
    ReviewImportFailed { reason: String },

    #[error("GD-6004: Integrity check failed: {check}")]
    IntegrityCheckFailed { check: String },
}

// genesis-deslop-cli/src/error.rs

#[derive(Debug, thiserror::Error)]
pub enum CliError {
    #[error("GD-7001: Command '{command}' requires a scan first")]
    NoScanData { command: String },

    #[error("GD-7002: Invalid argument: {reason}")]
    InvalidArgument { reason: String },

    #[error("GD-7003: Output rendering failed: {reason}")]
    RenderFailed { reason: String },

    #[error("GD-7004: Operation cancelled by user")]
    Cancelled,
}
```

### Error propagation

- Within a crate: Use the crate-specific error type.
- Across crate boundaries: Convert to `anyhow::Error` at the boundary.
- At the CLI level: All errors are caught and displayed with their error code and a human-readable message.
- Errors include context via `anyhow::Context::context()` for debugging.

---

## 10. Performance Requirements

These are hard requirements that must be validated with benchmarks.

| Operation | Target | Measurement |
|---|---|---|
| Full scan of 10,000 files | < 30 seconds | Wall clock, warm filesystem cache |
| State load (50,000 findings) | < 100ms | Wall clock |
| State save (50,000 findings) | < 100ms | Wall clock |
| Score computation (50,000 findings) | < 10ms | Wall clock |
| Work queue build (50,000 findings) | < 50ms | Wall clock |
| Memory usage (50,000 findings) | < 500MB | RSS peak |
| Single detector (1,000 files) | < 5 seconds | Wall clock |
| File discovery (100,000 entries) | < 2 seconds | Wall clock |
| Plan reconciliation (10,000 items) | < 200ms | Wall clock |

### Performance design guidelines

1. **Avoid unnecessary allocations**: Use `&str` over `String` where possible. Use `Cow<str>` for strings that may or may not need allocation.
2. **Streaming file reads**: Don't load entire files into memory for line counting. Use `BufReader`.
3. **Parallel detection**: Detectors that are independent should run in parallel using `rayon` or similar. The detection phase should use available CPU cores.
4. **Lazy loading**: Don't parse all files upfront. Parse on demand during detection.
5. **Incremental state**: Only re-serialize changed portions of state where possible.
6. **File hashing**: Use memory-mapped I/O or streaming hash for large files.

---

## Appendix A: State file format example

```json
{
  "version": 1,
  "created": "2025-01-15T10:30:00Z",
  "last_scan": "2025-02-28T14:22:00Z",
  "scan_count": 12,
  "overall_score": 78.5,
  "objective_score": 82.1,
  "strict_score": 71.3,
  "verified_strict_score": 65.8,
  "stats": {
    "total_files": 342,
    "total_loc": 45210,
    "total_dirs": 28,
    "language": "typescript",
    "open_findings": 47,
    "fixed_findings": 123,
    "wontfix_findings": 5,
    "suppressed_findings": 3
  },
  "findings": {
    "complexity::src/engine.ts::processQueue": {
      "id": "complexity::src/engine.ts::processQueue",
      "detector": "complexity",
      "file": "src/engine.ts",
      "tier": "Judgment",
      "confidence": "High",
      "summary": "Function processQueue has cyclomatic complexity 28 (threshold: 15)",
      "detail": { "complexity": 28, "threshold": 15, "line": 142, "loc": 85 },
      "status": "Open",
      "note": null,
      "first_seen": "2025-01-15T10:30:00Z",
      "last_seen": "2025-02-28T14:22:00Z",
      "resolved_at": null,
      "reopen_count": 0,
      "suppressed": null,
      "suppressed_at": null,
      "suppression_pattern": null,
      "resolution_attestation": null,
      "lang": "typescript",
      "zone": "Production"
    }
  },
  "scan_coverage": {},
  "score_confidence": "high",
  "scan_history": [],
  "subjective_integrity": {},
  "subjective_assessments": {},
  "concern_dismissals": {}
}
```

## Appendix B: Config file format example

```toml
target_strict_score = 90
review_max_age_days = 14
generate_scorecard = true
badge_path = "docs/scorecard.png"

exclude = [
    "legacy/",
    "*.generated.ts",
]

ignore = [
    "naming::src/legacy/*",
]

[zone_overrides]
"scripts/" = "Script"
"src/generated/" = "Generated"

[languages.typescript]
large_files_threshold = 400
complexity_threshold = 20
```

## Appendix C: Finding ID format

Finding IDs follow the pattern: `{detector}::{relative_path}::{symbol}`

- `detector`: The detector name from the registry (e.g., "complexity", "duplicate").
- `relative_path`: File path relative to project root, using forward slashes (e.g., "src/engine.ts").
- `symbol`: A disambiguator, typically:
  - Function/class name for function-level findings (e.g., "processQueue").
  - Line number for line-level findings (e.g., "L42").
  - Hash for multi-file findings (e.g., SHA fragment for duplicate groups).
  - Empty string for file-level findings (trailing `::` is kept).

Examples:
- `complexity::src/engine.ts::processQueue`
- `large::src/utils.ts::`
- `duplicate::src/helpers.ts::formatDate`
- `cycle::src/auth/index.ts::scc_a1b2c3`
- `security::src/api.ts::L157`
