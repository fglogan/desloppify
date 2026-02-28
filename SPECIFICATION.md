# Genesis Deslop — Master Specification

> **Project:** Rust rewrite of `desloppify` v0.8.0 (Python) as `genesis-deslop`
> **Binary:** `gdeslop`
> **Version:** 1.0.0
> **Date:** 2026-02-28
> **Total specification corpus:** ~385 KB across 5 component documents + this master

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [What desloppify Is](#2-what-desloppify-is)
3. [Document Map](#3-document-map)
4. [Key Architectural Decisions](#4-key-architectural-decisions)
5. [System Overview](#5-system-overview)
6. [Scoring System Summary](#6-scoring-system-summary)
7. [Language Support Matrix](#7-language-support-matrix)
8. [Implementation Roadmap](#8-implementation-roadmap)
9. [Risk Register](#9-risk-register)
10. [Cross-Reference Index](#10-cross-reference-index)
11. [Glossary](#11-glossary)
12. [Acceptance Criteria](#12-acceptance-criteria)

---

## 1. Executive Summary

**desloppify** is a Python-based AI coding agent harness (v0.8.0, MIT license)
that identifies and systematically improves codebase quality. It combines
mechanical detection (14+ detectors covering dead code, duplication, complexity,
security, test coverage, naming, coupling, and more) with subjective LLM review
(11 dimensions including elegance, contracts, type safety, and abstraction fit),
producing a prioritized fix loop with persistent state across scans.

**Genesis Deslop** is the complete Rust rewrite of this system under Genesis
branding. The rewrite is not a port — it is a clean-room reimplementation from
specification. The Python codebase has been fully reverse-engineered: every
algorithm, data structure, state machine, scoring formula, processing pipeline,
and constant has been captured in the component specification documents listed
below.

### Why Rust

| Concern | Python (current) | Rust (target) |
|---------|-------------------|---------------|
| Startup time | ~800ms interpreter + import chain | <50ms native binary |
| Scan speed (1000 files) | Sequential, GIL-bound | Parallel via `rayon`, 4–8x faster |
| Memory safety | Runtime errors possible | Compile-time guarantees |
| Distribution | Requires Python 3.11+ runtime | Single static binary |
| Type safety | Runtime type errors possible | Compile-time type checking |
| Dependency footprint | stdlib-only (core), tree-sitter optional | Minimal: serde, clap, tree-sitter |

### Scope

The Rust implementation must produce **identical scoring results** to the Python
reference (within 0.001 tolerance for floating-point operations). All 17 CLI
commands, 28 language plugins, 14+ detectors, 11 review dimensions, and the
complete state/plan persistence system must be reimplemented.

---

## 2. What desloppify Is

### 2.1 Core Capabilities

1. **Mechanical Detection** — 14+ detectors analyze source code for objective
   quality issues: dead code, duplication (exact + near-duplicate), cyclomatic
   complexity, security vulnerabilities, test coverage gaps, naming convention
   violations, excessive coupling, large files, god objects, circular
   dependencies, import organization, code smells, logging hygiene, and
   responsibility cohesion.

2. **Subjective LLM Review** — 11 quality dimensions assessed via blind review
   packets sent to LLM subagents (Codex or Claude). Dimensions include
   elegance, contracts, type safety, abstraction fit, naming depth, test
   quality, error handling, separation of concerns, documentation, performance
   awareness, and idiomatic style.

3. **4-Channel Scoring** — Four complementary scores computed per scan:
   - `overall`: lenient penalties + subjective review (the headline number)
   - `objective`: lenient penalties, mechanical detectors only
   - `strict`: strict penalties + subjective review
   - `verified_strict`: strict + integrity-verified review scores only

4. **Prioritized Work Queue** — Findings ranked by composite sort key for
   maximum impact-per-fix: cluster grouping → tier (ascending) → pool
   (mechanical first) → confidence rank → review weight → count.

5. **Persistent State** — Finding lifecycle tracked across scans with 5
   statuses (open, fixed, auto_resolved, wontfix, false_positive). Reopen
   detection, attestation, and 90-day superseded TTL.

6. **Narrative Coaching** — 7-phase progression system with lane-based action
   planning, reminder decay, and structural merge grouping.

7. **Anti-Gaming** — Integrity checks detect score manipulation: wontfix counts
   against strict score, placeholder code detection, target-match reset when ≥2
   subjective dimensions suspiciously match targets.

### 2.2 Scale

| Metric | Value |
|--------|-------|
| Supported languages | 28 (6 full-depth, 22 generic) |
| CLI commands | 17 |
| Detectors | 14+ mechanical |
| Review dimensions | 11 subjective |
| Zones | 6 (production, test, config, generated, script, vendor) |
| State schema version | 1 |
| Required dependencies | 0 (stdlib-only core) |
| Optional dependencies | tree-sitter, bandit, Pillow |

---

## 3. Document Map

This master specification is the entry point. It references five component
documents, each of which is self-contained and authoritative for its domain.

```
SPECIFICATION.md  ◄── You are here (master entry point)
    │
    ├── ARCHITECTURE.md ──────── System design, 10 ASCII diagrams, module
    │   (125,450 bytes)          dependencies, data flow, state machines,
    │   1,395 lines              Rust crate architecture
    │
    ├── DATA_DICTIONARY.md ───── Every type, enum, struct, constant, and
    │   (45,320 bytes)           configuration key as Rust-ready definitions.
    │   1,584 lines              12 sections covering all subsystems.
    │
    ├── GENESIS_BRAND.md ─────── Product identity, naming conventions, color
    │   (15,077 bytes)           palette, file formats, migration path,
    │   492 lines                ecosystem integration, quality standards.
    │
    ├── RUST_SPECIFICATION.md ── Complete per-crate implementation spec.
    │   (128,841 bytes)          All types/traits/functions in Rust code blocks.
    │   3,570 lines              Scoring algorithm step-by-step. 3 appendices.
    │
    └── TEST_HARNESS.md ──────── Test strategy, ~755 tests across all crates,
        (70,310 bytes)           golden files, cross-validation, property-based
        1,695 lines              tests, benchmarks, CI pipeline.
```

### 3.1 Reading Order

For a developer starting the Rust implementation:

1. **This document** — understand the project, scope, and roadmap
2. **GENESIS_BRAND.md** — internalize naming, directory layout, and conventions
3. **ARCHITECTURE.md** — study the system diagrams and data flow
4. **DATA_DICTIONARY.md** — reference as you define types
5. **RUST_SPECIFICATION.md** — primary implementation guide (code-level detail)
6. **TEST_HARNESS.md** — set up test infrastructure alongside implementation

### 3.2 Document Relationships

```
┌─────────────────────┐
│  SPECIFICATION.md   │  Executive summary, roadmap, acceptance criteria
│  (this document)    │
└────────┬────────────┘
         │
    ┌────┴────────────────────────────────────────────────┐
    │                                                      │
    ▼                                                      ▼
┌──────────────┐   defines types for   ┌────────────────────────┐
│ ARCHITECTURE │ ─────────────────────▶ │  RUST_SPECIFICATION    │
│  .md         │                        │  .md                   │
│              │ ◀───────────────────── │                        │
│  Diagrams &  │   implements design    │  Per-crate code-level  │
│  data flow   │                        │  specification         │
└──────┬───────┘                        └───────────┬────────────┘
       │                                            │
       │  enumerates                                │  references types from
       ▼                                            ▼
┌──────────────┐                        ┌────────────────────────┐
│ DATA_        │                        │  TEST_HARNESS.md       │
│ DICTIONARY   │ ◀───────── tests ───── │                        │
│ .md          │   validate against     │  ~755 tests, golden    │
│              │                        │  files, cross-validate │
└──────────────┘                        └────────────────────────┘
       │
       │  follows naming from
       ▼
┌──────────────┐
│ GENESIS_     │
│ BRAND.md     │
│              │
│  Names,      │
│  conventions │
└──────────────┘
```

---

## 4. Key Architectural Decisions

### ADR-1: Workspace Crate Split

**Decision:** 6 crates in a Cargo workspace.

**Rationale:** Mirrors the Python package structure while enabling independent
compilation, targeted testing, and clean dependency boundaries.

| Crate | Purpose | Dependencies |
|-------|---------|-------------|
| `genesis-deslop-core` | Types, config, discovery, paths, output, registry | `serde`, `toml` |
| `genesis-deslop-engine` | Detectors, scoring, state, work queue, plan, concerns, policy | `core` |
| `genesis-deslop-lang` | Language framework + 28 plugins | `core`, `engine`, optional `tree-sitter` |
| `genesis-deslop-intel` | Review, narrative, integrity | `core`, `engine` |
| `genesis-deslop-cli` | CLI binary (`gdeslop`), output rendering | all crates, `clap` |
| `genesis-deslop` | Facade lib crate, re-exports public API | all crates |

**See:** ARCHITECTURE.md §10, RUST_SPECIFICATION.md §1, GENESIS_BRAND.md §2.2

### ADR-2: TOML Configuration (Not JSON)

**Decision:** Use `genesis-deslop.toml` instead of Python's inline dict config.

**Rationale:** TOML is the Rust ecosystem standard. Human-readable, supports
comments, first-class `serde` support. The Python version used JSON state files
which remain JSON for backward compatibility during migration.

**See:** RUST_SPECIFICATION.md §2.1, GENESIS_BRAND.md §5

### ADR-3: Scoring Parity as Hard Constraint

**Decision:** The Rust scoring pipeline must produce results within ±0.001 of
the Python reference for identical inputs.

**Rationale:** Users migrating from the Python tool must see consistent scores.
Any deviation would undermine trust. Cross-validation tests run Python and Rust
side-by-side on the same input fixtures.

**See:** TEST_HARNESS.md §4, RUST_SPECIFICATION.md §3.2

### ADR-4: Feature Flags for Optional Subsystems

**Decision:** Heavy optional dependencies gated behind Cargo feature flags.

| Feature Flag | Enables | Default |
|-------------|---------|---------|
| `tree-sitter` | AST-based detection for all languages | off |
| `scorecard` | PNG scorecard generation (image crate) | off |
| `review` | LLM review subsystem (reqwest/tokio) | off |
| `full` | All features | off |

**Rationale:** Core scanning with regex-based detection works with zero optional
dependencies. Users opt in to AST parsing, image generation, and network-based
review as needed.

**See:** RUST_SPECIFICATION.md §7

### ADR-5: Parallel Detection via Rayon

**Decision:** Use `rayon` for per-file parallel detection; `tokio` only for
async subprocess I/O (external linters).

**Rationale:** Detection is CPU-bound and embarrassingly parallel per file.
`rayon`'s work-stealing scheduler is the right tool. `tokio` is reserved for
the small number of operations that involve subprocess I/O (external linter
invocation, LLM API calls).

**See:** ARCHITECTURE.md §10, RUST_SPECIFICATION.md §10

### ADR-6: State File Format Continuity

**Decision:** State file remains JSON (`state.json`, `plan.json`) even though
config moves to TOML.

**Rationale:** JSON round-trips cleanly with `serde_json`, supports the complex
nested structures in state/plan, and allows migration tooling to read Python-era
state files. Config is TOML because it's human-edited; state is JSON because
it's machine-managed.

**See:** RUST_SPECIFICATION.md Appendix A, DATA_DICTIONARY.md §1

### ADR-7: Error Handling Strategy

**Decision:** `thiserror` for library crates (structured error enums),
`anyhow` for the CLI crate (ergonomic error propagation).

**Rationale:** Library crates expose typed errors so consumers can match on
specific failure modes. The CLI crate converts all errors to human-readable
messages — `anyhow` excels at this.

**See:** RUST_SPECIFICATION.md §9

---

## 5. System Overview

### 5.1 High-Level Data Flow

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Discover │    │ Classify │    │  Detect  │    │  Score   │    │ Present  │
│  Files   │───▶│  Zones   │───▶│ Findings │───▶│ & Merge  │───▶│ Results  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     │               │               │               │               │
     │  Walk tree,   │  6 zones,     │  14+ detect-  │  4-channel    │  CLI output,
     │  .gitignore,  │  per-zone     │  ors + LLM    │  scoring,     │  scorecard,
     │  excludes     │  policies     │  review       │  state merge  │  treemap
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
  core::         core::          engine::        engine::        cli::
  discovery      registry        detectors       scoring +       output +
                 + policy        + lang::*       state           app::*
```

### 5.2 CLI Commands

All 17 commands from the Python version are reimplemented. The binary name
changes from `deslop` to `gdeslop`.

| Command | Purpose | Crate(s) Involved |
|---------|---------|-------------------|
| `scan` | Run full detection + scoring + state merge | engine, lang, intel |
| `status` | Display current scores and finding counts | engine, cli |
| `show` | Display details of a specific finding | engine, cli |
| `next` | Show highest-priority work item | engine (work_queue) |
| `ignore` | Mark a finding as wontfix/false_positive | engine (state) |
| `exclude` | Add path to exclude list | core (config) |
| `fix` | Mark finding as fixed (with verification) | engine (state) |
| `plan` | Show/manage the fix plan | engine (plan) |
| `detect` | Run a single detector in isolation | engine (detectors) |
| `tree` | Print LLM-readable directory tree | core (discovery), cli |
| `viz` | Generate treemap visualization | cli (output) |
| `move` | Reorganize files by zone | cli (move/) |
| `zone` | Display/override zone assignments | core (registry) |
| `review` | Trigger LLM subjective review | intel (review) |
| `config` | Show/edit configuration | core (config) |
| `dev` | Developer utilities (debug, dump state) | engine, cli |
| `update-skill` | Update LLM skill/dimension definitions | intel |
| `langs` | List supported languages and their depth | lang |

### 5.3 Finding Lifecycle

Findings transition through 5 statuses across scans:

```
                    ┌─────────────────────────────────────────┐
                    │              Finding Lifecycle           │
                    ├─────────────────────────────────────────┤
                    │                                         │
 New finding ──────▶│  OPEN                                   │
                    │    │                                    │
                    │    ├──── code changed ──────▶ FIXED     │
                    │    │                                    │
                    │    ├──── finding disappears ▶ AUTO_     │
                    │    │     on rescan            RESOLVED  │
                    │    │                                    │
                    │    ├──── user marks ─────────▶ WONTFIX  │
                    │    │     (counts against                │
                    │    │      strict score)                 │
                    │    │                                    │
                    │    └──── user marks ─────────▶ FALSE_   │
                    │                                POSITIVE │
                    │                                         │
                    │  Any non-open status can REOPEN if the  │
                    │  finding reappears on a subsequent scan │
                    └─────────────────────────────────────────┘
```

**Full state machine detail:** ARCHITECTURE.md §4

---

## 6. Scoring System Summary

The scoring system is the mathematical core of desloppify. It produces four
scores from 0–100 (higher = better) via a multi-stage pipeline.

### 6.1 Pipeline Stages

```
 Findings               Per-Detector          Pool Blending         4-Channel
 (raw)                  Aggregation           (40/60 split)         Output
 ─────────────────────  ────────────────────  ──────────────────    ──────────
 For each finding:      For each detector:    Mechanical pool:      overall
   weight = tier_w *      sum weighted        40% of final score    objective
     confidence_w *         failures          Subjective pool:      strict
     file_cap           apply noise budget    60% of final score    verified_
                        score = max(0,                               strict
                          100 - penalty)
```

### 6.2 Key Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| Mechanical weight | 40% | Weight of detector-based scores in blend |
| Subjective weight | 60% | Weight of LLM review scores in blend |
| MIN_SAMPLE | 200 | Minimum files before full scoring applies |
| Confidence high | 1.0 | Weight multiplier for high-confidence findings |
| Confidence medium | 0.7 | Weight multiplier for medium-confidence findings |
| Confidence low | 0.3 | Weight multiplier for low-confidence findings |
| Tier weights | T1=1, T2=2, T3=3, T4=4 | Severity multiplier per tier |
| File cap (1-2 findings) | 1.0 | Cap per-file finding weight |
| File cap (3-5 findings) | 1.5 | Cap per-file finding weight |
| File cap (6+ findings) | 2.0 | Cap per-file finding weight |
| HOLISTIC_MULTIPLIER | 10.0 | Amplifier for holistic detectors |
| Superseded TTL | 90 days | Time before dead findings are pruned |

**Complete scoring algorithm with step-by-step formulas:**
RUST_SPECIFICATION.md §3.2

**All scoring types as Rust structs:** DATA_DICTIONARY.md §3

---

## 7. Language Support Matrix

28 languages are supported across three depth tiers.

### 7.1 Full-Depth Plugins (6)

These languages have dedicated plugin modules with language-specific detectors,
fixers, smell checks, security rules, and dependency graph analysis.

| Language | Detectors | Phases | Smell Checks | Security | Fixers | Special Features |
|----------|-----------|--------|-------------|----------|--------|------------------|
| TypeScript | 15 | 7 | 28 | 10 | 8 | React-specific detection, Knip adapter, barrel files |
| Python | 13+ | 13 | 32 | bandit adapter | ruff adapter (14 rules) | AST analysis, dict key flow, responsibility cohesion |
| C# | 6 | corroboration-gated | – | 4 rules | – | Roslyn dep graph, namespace fallback, min 2 signals |
| Dart | – | – | – | – | – | pubspec integration, barrel re-export resolution |
| GDScript | – | – | – | – | – | Indentation-based parsing, Godot root detection |
| Go | 7 complexity signals | – | – | – | – | Brace tracking, stub dep graph |

### 7.2 Generic Plugins (22)

Single-file plugins using the `generic_lang()` factory. Three depth levels.

| Depth | Languages |
|-------|-----------|
| Standard | Rust |
| Shallow | Bash, C, C++, Elixir, Java, JavaScript, Kotlin, Ruby, Scala, Swift |
| Minimal | CSS, Groovy, Haskell, HTML, Lua, Objective-C, OCaml, Perl, PHP, R, SQL |

5 generic plugins have auto-fix capability: JavaScript, Kotlin, Ruby, Rust,
Swift. Only Rust specifies 2 external tools.

**Complete per-plugin specifications:** RUST_SPECIFICATION.md §4.3–4.4

**Language framework trait definitions:** DATA_DICTIONARY.md §7

---

## 8. Implementation Roadmap

### 8.1 Phase Overview

The implementation proceeds in 6 phases, each producing a shippable increment
with its own test coverage gate.

```
Phase 1        Phase 2         Phase 3        Phase 4         Phase 5        Phase 6
──────────     ──────────      ──────────     ──────────      ──────────     ──────────
core crate     engine:         lang crate     engine:         intel crate    CLI crate
               state +         (1 plugin)     detectors       (review +      (gdeslop
Types,         scoring                        (all 14+)       narrative)     binary)
config,                        Python
discovery,     Mathematical    plugin first   Port one at     LLM review     All 17
paths,         core with       to validate    a time with     pipeline,      commands,
output,        property        finding        golden-file     narrative      output
registry       tests vs        parity         tests           coaching       rendering,
               Python                                                        scorecard
```

### 8.2 Detailed Phase Plan

#### Phase 1: `genesis-deslop-core` (Estimated: 2 weeks)

**Goal:** All shared types, configuration parsing, file discovery, zone
classification, and output formatting.

**Deliverables:**
- All enums: `FindingStatus`, `Confidence`, `Tier`, `Pool`, `Zone`,
  `DetectorKind`, `LanguageDepth`, `ReviewTrust`
- `Config` struct with TOML deserialization (17 keys)
- File discovery with `.gitignore` integration (`ignore` crate)
- Zone classifier with 6 zones + override support
- Detector registry (static registry of all detector metadata)
- Output formatting utilities

**Test gate:** 90% line coverage, all types roundtrip through serde

**Dependencies:** `serde`, `serde_json`, `toml`, `ignore`

#### Phase 2: `genesis-deslop-engine` (state + scoring) (Estimated: 3 weeks)

**Goal:** The mathematical core — state persistence, scoring pipeline, work
queue ranking.

**Deliverables:**
- State load/save with schema version migration
- Finding merge logic (new findings, reopens, auto-resolve)
- Complete 4-channel scoring pipeline
- Work queue composite sort
- Plan reconciliation (supersede, resurface, sync)

**Test gate:** 85% line coverage, cross-validation against Python reference
(±0.001 scoring tolerance), property-based tests for scoring invariants
(monotonicity, boundedness, idempotency)

**Dependencies:** `genesis-deslop-core`

#### Phase 3: `genesis-deslop-lang` (first plugin) (Estimated: 2 weeks)

**Goal:** Language framework trait + one full-depth plugin (Python recommended
as first) to validate the plugin architecture.

**Deliverables:**
- `LanguagePlugin` trait definition
- `generic_lang()` factory function
- Python full-depth plugin with all 13 phases
- Finding output format validation against Python reference

**Test gate:** 75% line coverage, golden file tests for Python plugin output

**Dependencies:** `genesis-deslop-core`, `genesis-deslop-engine`

#### Phase 4: `genesis-deslop-engine` (detectors) + remaining plugins (Estimated: 4 weeks)

**Goal:** All 14+ detectors ported, all 28 language plugins implemented.

**Deliverables:**
- All mechanical detectors: dead_code, duplication (exact + near), complexity,
  security, test_coverage, naming, coupling, large_files, god_objects,
  cycle_detection, imports, smells, logging, concerns
- Remaining 5 full-depth plugins (TypeScript, C#, Dart, GDScript, Go)
- All 22 generic plugins
- Per-zone detector policies (29 policies)

**Test gate:** 85% coverage on detectors, golden file tests for each detector,
at least 3 language plugin integration tests

**Dependencies:** `genesis-deslop-core`, `genesis-deslop-engine` (state/scoring)

#### Phase 5: `genesis-deslop-intel` (Estimated: 3 weeks)

**Goal:** LLM review pipeline, narrative coaching system, integrity checks.

**Deliverables:**
- Blind review packet generation (SHA-256 provenance)
- Codex subagent execution (parallel/serial, stall detection, retry)
- Claude external review (session + token management)
- DimensionMergeScorer (70/30 weighted mean/floor blend)
- 7-phase narrative system with lane-based action planning
- Reminder decay system
- Integrity verification (anti-gaming checks)

**Test gate:** 80% coverage, mock LLM responses for all review tests

**Dependencies:** `genesis-deslop-core`, `genesis-deslop-engine`, `reqwest`,
`tokio` (behind `review` feature flag)

#### Phase 6: `genesis-deslop-cli` (Estimated: 2 weeks)

**Goal:** The `gdeslop` binary with all 17 commands and output rendering.

**Deliverables:**
- `clap` command structure with all 17 subcommands
- Terminal output formatting (colors, tables, progress)
- Scorecard PNG generation (behind `scorecard` feature flag)
- Treemap HTML generation (D3.js template)
- Tree text output (LLM-readable format)
- `genesis-deslop` facade crate re-exporting public API

**Test gate:** 70% coverage, snapshot tests for all command outputs

**Dependencies:** all crates, `clap`, `image` (optional), `indicatif`

### 8.3 Timeline Summary

| Phase | Crate(s) | Duration | Cumulative |
|-------|----------|----------|-----------|
| 1 | core | 2 weeks | 2 weeks |
| 2 | engine (state + scoring) | 3 weeks | 5 weeks |
| 3 | lang (Python plugin) | 2 weeks | 7 weeks |
| 4 | engine (detectors) + lang (all) | 4 weeks | 11 weeks |
| 5 | intel | 3 weeks | 14 weeks |
| 6 | cli + facade | 2 weeks | 16 weeks |

**Total estimated duration: 16 weeks** for a single developer working
full-time. Phases 3 and 4 can partially overlap since the language framework
stabilizes early in Phase 3.

### 8.4 Migration Path (Python → Rust)

During development, the CLI crate can shell out to the Python tool for unported
subsystems. This enables incremental delivery:

1. **Week 5:** `gdeslop scan` works for scoring (shells out for detection)
2. **Week 7:** `gdeslop scan` works end-to-end for Python projects
3. **Week 11:** Full detection for all 28 languages
4. **Week 14:** LLM review and narrative coaching functional
5. **Week 16:** Feature-complete, ready for release

Users can migrate state files from `.desloppify/` to `.genesis-deslop/` using a
`gdeslop migrate` command (one-time conversion).

**See:** GENESIS_BRAND.md §9 (migration path)

---

## 9. Risk Register

| # | Risk | Impact | Likelihood | Mitigation |
|---|------|--------|------------|------------|
| R1 | Scoring drift between Python and Rust | High — users lose trust | Medium | Cross-validation test suite with ±0.001 tolerance; property-based tests for invariants |
| R2 | tree-sitter grammar version mismatch | Medium — AST parsing fails | Medium | Pin grammar versions; feature-flag tree-sitter so regex fallback always works |
| R3 | Near-duplicate detection performance | Medium — O(n²) file comparisons | Low | LOC ratio pruning (1.5x) + quick_ratio gate before full SequenceMatcher |
| R4 | LLM API changes break review pipeline | High — subjective scoring breaks | Medium | Abstract LLM interface behind trait; mock tests; graceful degradation |
| R5 | State migration data loss | High — users lose scan history | Low | Schema versioning; migration tested against 50+ real state files; backup before migration |
| R6 | External linter availability | Low — graceful degradation exists | High | Linter absence produces warning, not error; detection continues with available detectors |
| R7 | Cycle detection performance on large codebases | Medium — scan timeout | Low | Iterative Tarjan's (not recursive); deferred import filtering; file-count circuit breaker |

---

## 10. Cross-Reference Index

This index maps key concepts to their locations across all specification
documents.

### Types and Data Structures

| Concept | DATA_DICTIONARY.md | RUST_SPECIFICATION.md | ARCHITECTURE.md |
|---------|--------------------|-----------------------|-----------------|
| Finding / FindingStatus | §1.1–1.2 | §3.1 | §4 |
| Confidence / Tier | §1.2–1.3 | §2.2 | §5 |
| ScanState | §1.6 | §3.1 | §4 |
| ScoreSet / ScoreResult | §3 | §3.2 | §5 |
| WorkItem | §2.3 | §3.4 | §6 |
| Plan / PlanEntry | §2.4 | §3.5 | — |
| Config | §5 | §2.1 | — |
| Zone | §4 | §2.2 | §8 |
| DetectorMeta | §6 | §3.3 | §8 |
| LanguagePlugin trait | §7 | §4.1–4.2 | §8 |
| ReviewPacket | §10 | §5.1 | §7 |
| NarrativePhase | §9 | §5.2 | §9 |
| Concern | §11 | §3.6 | — |

### Algorithms

| Algorithm | RUST_SPECIFICATION.md | ARCHITECTURE.md | TEST_HARNESS.md |
|-----------|----------------------|-----------------|-----------------|
| 4-channel scoring | §3.2 (step-by-step) | §5 (diagram) | §4 (cross-validation) |
| Work queue ranking | §3.4 | §6 (diagram) | §2 (unit tests) |
| Finding merge | §3.1 | §4 (state machine) | §2, §5 (property tests) |
| Plan reconciliation | §3.5 | — | §2 (unit tests) |
| Near-duplicate detection | §3.3 (duplicate detector) | — | §3 (golden files) |
| Cycle detection (Tarjan's) | §3.3 (cycle detector) | — | §3 (golden files) |
| Auto-clustering | §3.4 | §6 | §5 (property tests) |
| DimensionMergeScorer | §5.1 | §7 | §2 (unit tests) |
| Narrative phase selection | §5.2 | §9 | §2 (unit tests) |
| Integrity verification | §5.3 | — | §2 (unit tests) |

### Branding and Conventions

| Topic | GENESIS_BRAND.md | RUST_SPECIFICATION.md |
|-------|------------------|-----------------------|
| Crate naming | §2.1 | §1 |
| Binary name (`gdeslop`) | §1 | §1 |
| State directory | §2.3 | §3.1 |
| Config format (TOML) | §5 | §2.1, Appendix B |
| Color palette | §4 | §6.2 |
| Error messages | §7 | §9 |
| Version policy | §1 | — |

---

## 11. Glossary

| Term | Definition |
|------|-----------|
| **Attestation** | Cryptographic signature (SHA-256) linking a review result to the blind packet that produced it, preventing score injection |
| **Blind packet** | A review request sent to the LLM with no existing scores, preventing anchoring bias |
| **Confidence** | Finding certainty level: `high` (1.0), `medium` (0.7), `low` (0.3) — used as a weight multiplier in scoring |
| **Corroboration** | C# plugin strategy requiring ≥2 independent signals before reporting a finding |
| **Detector** | A mechanical analysis pass that identifies specific code quality issues (e.g., `complexity`, `duplicate`, `dead_code`) |
| **Dimension** | A subjective quality axis assessed by LLM review (e.g., `elegance`, `contracts`, `type_safety`) |
| **File cap** | Per-file weight limit preventing a single problematic file from dominating the score |
| **Finding** | A single detected quality issue, identified by `{detector}::{path}::{symbol}` |
| **Full-depth plugin** | A language plugin with dedicated detectors, fixers, smell checks, and security rules |
| **Generic plugin** | A language plugin using the `generic_lang()` factory with standard/shallow/minimal depth |
| **Golden file** | A frozen expected-output file used for regression testing |
| **Holistic detector** | A detector that produces a single project-wide finding (e.g., test coverage) rather than per-file findings |
| **Lane** | A parallelizable workstream in the narrative action plan, grouped by file overlap using union-find |
| **Lenient scoring** | Scoring mode that caps per-finding penalties (used in `overall` and `objective` channels) |
| **Noise budget** | Per-detector limit on reported findings to prevent flooding (default: 10 per detector, 0 global) |
| **Pool** | One of two finding categories: `mechanical` (detector-based) or `subjective` (LLM review-based) |
| **Strict scoring** | Scoring mode with uncapped penalties (used in `strict` and `verified_strict` channels) |
| **Superseded** | A finding that disappeared from scan results; pruned after 90-day TTL |
| **Tier** | Finding severity: T1 (informational, weight 1) through T4 (critical, weight 4) |
| **Wontfix** | A finding the user has decided not to fix; counts against strict score as an anti-gaming measure |
| **Zone** | A file classification (production, test, config, generated, script, vendor) that determines which detectors apply |

---

## 12. Acceptance Criteria

The Rust implementation is considered complete when ALL of the following are met:

### 12.1 Functional Parity

- [ ] All 17 CLI commands produce equivalent output to the Python tool
- [ ] All 14+ detectors produce equivalent findings for the same input
- [ ] All 28 language plugins are functional at their specified depth
- [ ] State files can be loaded, modified, and saved without data loss
- [ ] Plan reconciliation handles all edge cases (supersede, resurface, sync)
- [ ] Configuration files (TOML) support all 17 keys

### 12.2 Scoring Parity

- [ ] 4-channel scoring output matches Python reference within ±0.001
- [ ] Cross-validation test suite passes against 50+ golden fixtures
- [ ] Property-based tests verify: monotonicity, boundedness [0,100],
      idempotency, symmetry, empty-input baseline (100.0)
- [ ] Work queue ranking produces identical ordering for identical inputs

### 12.3 Quality Gates

- [ ] >80% overall line coverage (`cargo-llvm-cov`)
- [ ] Per-crate minimums: core 90%, engine 85%, lang 75%, intel 80%, cli 70%
- [ ] Zero `unsafe` blocks outside of FFI boundaries (tree-sitter)
- [ ] `cargo clippy -- -D warnings` passes with zero warnings
- [ ] `cargo fmt --check` passes
- [ ] No `unwrap()` in library crates (use `?` or explicit error handling)
- [ ] All public types implement `Debug`, `Clone`, `Serialize`, `Deserialize`

### 12.4 Performance

- [ ] Cold scan of 1000-file project: <10 seconds (wall clock)
- [ ] State load/save: <100ms for 10,000-finding state file
- [ ] Binary size: <20 MB (release, stripped, without tree-sitter grammars)
- [ ] Startup time: <50ms to first output

### 12.5 Branding

- [ ] Binary name is `gdeslop`
- [ ] State directory is `.genesis-deslop/`
- [ ] Config file is `genesis-deslop.toml`
- [ ] All error messages follow Genesis branding guidelines
- [ ] Scorecard uses Genesis color palette (BG=#F7F0E4, TEXT=#3A3026)
- [ ] No references to "desloppify" in user-facing output

### 12.6 Migration

- [ ] `gdeslop migrate` converts `.desloppify/` → `.genesis-deslop/`
- [ ] State JSON schema is preserved (version 1)
- [ ] Scan history is preserved during migration
- [ ] Finding IDs are stable across migration (no re-hashing)

---

## Appendix: File Manifest

All files produced by this specification effort:

| File | Size | Lines | Content |
|------|------|-------|---------|
| `SPECIFICATION.md` | this file | — | Master entry point, roadmap, acceptance criteria |
| `ARCHITECTURE.md` | 125,450 B | 1,395 | 10 ASCII diagrams, system design, module dependencies |
| `DATA_DICTIONARY.md` | 45,320 B | 1,584 | All types as Rust-ready definitions, 12 sections |
| `GENESIS_BRAND.md` | 15,077 B | 492 | Naming, colors, conventions, migration path |
| `RUST_SPECIFICATION.md` | 128,841 B | 3,570 | Per-crate implementation spec, 3 appendices |
| `TEST_HARNESS.md` | 70,310 B | 1,695 | ~755 tests, golden files, CI pipeline |
| **Total** | **~385 KB** | **~8,736** | **Complete specification corpus** |

---

*This document is the master specification for Genesis Deslop. All
implementation work should begin here and reference the component documents as
needed. The specification corpus is complete and self-contained — a Rust
developer should be able to implement the entire system from these documents
alone, without reference to the Python source.*
