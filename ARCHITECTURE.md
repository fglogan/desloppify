# Desloppify — Architecture Specification

> Rust rewrite target architecture for the desloppify codebase quality scoring
> system. This document captures the complete design of the Python reference
> implementation and proposes the target Rust crate structure.

---

## Table of Contents

1. [System Context](#1-system-context-diagram)
2. [Module Dependencies](#2-module-dependency-diagram)
3. [Scan Pipeline Data Flow](#3-data-flow-diagram--scan-pipeline)
4. [Finding Lifecycle State Machine](#4-state-machine--finding-lifecycle)
5. [Scoring Pipeline Detail](#5-scoring-pipeline-detail-diagram)
6. [Work Queue Ranking Algorithm](#6-work-queue-ranking-algorithm)
7. [Review Pipeline](#7-review-pipeline-diagram)
8. [Language Plugin Architecture](#8-language-plugin-architecture)
9. [Narrative/Coaching System](#9-narrativecoaching-system)
10. [Rust Module Architecture (Target)](#10-rust-module-architecture-target)

---

## 1. System Context Diagram

```
                            ┌───────────────────────────────┐
                            │           User (CLI)          │
                            │  deslop scan / next / fix ... │
                            └───────────────┬───────────────┘
                                            │
                                    CLI commands
                                    (17 commands)
                                            │
                                            ▼
    ┌──────────────────┐     ┌──────────────────────────────────┐     ┌──────────────────┐
    │  Target Codebase │     │                                  │     │   LLM Review     │
    │                  │────▶│          DESLOPPIFY              │◀───▶│   System         │
    │  Source files,   │     │                                  │     │                  │
    │  project config, │     │  ┌────────────────────────────┐  │     │  ┌────────────┐  │
    │  .gitignore      │     │  │  CLI Layer   (app/)        │  │     │  │ Codex      │  │
    │                  │     │  │  Engine Layer (engine/)     │  │     │  │ Subagent   │  │
    └──────────────────┘     │  │  Intelligence (intelligence)│  │     │  │ (parallel  │  │
                             │  │  Languages   (languages/)  │  │     │  │  batches)  │  │
                             │  │  Core        (core/)       │  │     │  ├────────────┤  │
                             │  └────────────────────────────┘  │     │  │ Claude     │  │
                             │                                  │     │  │ External   │  │
                             └──────────┬───────────┬───────────┘     │  │ (session + │  │
                                        │           │                 │  │  token)    │  │
                           ┌────────────┘           └──────────┐      │  └────────────┘  │
                           ▼                                   ▼      └──────────────────┘
              ┌─────────────────────┐             ┌──────────────────────────┐
              │  External Linters   │             │   .desloppify/           │
              │                     │             │   (State Directory)      │
              │  ┌───────────────┐  │             │                          │
              │  │ tree-sitter   │  │             │  state.json              │
              │  │ (AST parsing) │  │             │  plan.json               │
              │  ├───────────────┤  │             │  config.toml             │
              │  │ ESLint        │  │             │  review_cache/           │
              │  │ ruff          │  │             │  scorecard.png           │
              │  │ cargo clippy  │  │             │                          │
              │  │ golangci-lint │  │             └──────────────────────────┘
              │  │ rubocop       │  │
              │  │ (28+ linters) │  │
              │  └───────────────┘  │
              └─────────────────────┘
```

**Key relationships:**

- **Target Codebase**: Read-only input. Source files are discovered, parsed,
  and analyzed. The codebase is never modified by scan operations.
- **External Linters**: Invoked as subprocesses. Output is parsed through
  format-specific adapters (ESLint JSON, ruff, cargo, golangci, rubocop,
  GNU-style). Graceful degradation when a tool is not installed.
- **tree-sitter**: Used for AST extraction (function/class extraction,
  complexity analysis, import resolution, smell detection). Optional —
  plugins degrade to shallow mode without it.
- **LLM Review System**: Two integration paths. Codex subagent runs parallel
  blind review batches. Claude external uses session-based token/expiry auth.
  Review packets are generated without scores to prevent anchoring bias.
- **State Directory**: `.desloppify/` persists `state.json` (findings,
  scores, assessments, scan history) and `plan.json` (work queue overrides,
  clusters, skip records).

---

## 2. Module Dependency Diagram

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║   ┌─────────────────────────────────────────────────────────────────────┐   ║
║   │                     CLI Layer  (app/)                              │   ║
║   │                                                                     │   ║
║   │  ┌─────────────┐  ┌───────────┐  ┌──────────────────────────────┐  │   ║
║   │  │ cli_support/ │  │ commands/ │  │ output/                      │  │   ║
║   │  │  parser.py   │  │ 17 cmds  │  │  scorecard.py, visualize.py  │  │   ║
║   │  └─────────────┘  └───────────┘  └──────────────────────────────┘  │   ║
║   └──────────┬──────────────┬──────────────────┬───────────────────────┘   ║
║              │              │                  │                            ║
║              ▼              ▼                  ▼                            ║
║   ┌───────────────────────────────┐  ┌─────────────────────────────────┐   ║
║   │     Engine Layer (engine/)    │  │  Intelligence Layer              │   ║
║   │                               │  │  (intelligence/)                │   ║
║   │  ┌──────────┐ ┌────────────┐  │  │                                 │   ║
║   │  │detectors/│ │ _scoring/  │  │  │  ┌─────────┐ ┌───────────────┐  │   ║
║   │  │ 31+      │ │ detection  │  │  │  │ review/ │ │ narrative/    │  │   ║
║   │  │ classes  │ │ policy     │  │  │  │ prepare │ │ phase detect  │  │   ║
║   │  └──────────┘ │ results    │  │  │  │ import  │ │ action engine │  │   ║
║   │  ┌──────────┐ │ subjective │  │  │  │ policy  │ │ headline gen  │  │   ║
║   │  │ _state/  │ └────────────┘  │  │  │ dims    │ │ reminders     │  │   ║
║   │  │ schema   │ ┌────────────┐  │  │  └─────────┘ │ strategy      │  │   ║
║   │  │ merge    │ │ _work_queue│  │  │  ┌─────────┐ └───────────────┘  │   ║
║   │  │ persist  │ │ ranking    │  │  │  │integrity│                    │   ║
║   │  │ resolve  │ └────────────┘  │  │  │ anti-   │                    │   ║
║   │  └──────────┘ ┌────────────┐  │  │  │ gaming  │                    │   ║
║   │  ┌──────────┐ │ _plan/     │  │  │  └─────────┘                    │   ║
║   │  │concerns  │ │ reconcile  │  │  └─────────────────────────────────┘   ║
║   │  │policy/   │ │ cluster    │  │              │                         ║
║   │  └──────────┘ └────────────┘  │              │                         ║
║   └───────────────┬───────────────┘              │                         ║
║                   │                              │                         ║
║                   ▼                              ▼                         ║
║   ┌─────────────────────────────────────────────────────────────────────┐   ║
║   │                  Languages Layer (languages/)                       │   ║
║   │                                                                     │   ║
║   │  ┌──────────────────┐  ┌──────────────────────────────────────────┐ │   ║
║   │  │ _framework/      │  │ Language Plugins (30 directories)       │ │   ║
║   │  │  base/types.py   │  │                                          │ │   ║
║   │  │  generic.py      │  │  Full-depth (6):                         │ │   ║
║   │  │  treesitter/     │  │    python, typescript, javascript,       │ │   ║
║   │  │  discovery.py    │  │    rust, go, java                        │ │   ║
║   │  │  registry.py     │  │                                          │ │   ║
║   │  └──────────────────┘  │  Generic via generic_lang() (22+):       │ │   ║
║   │                        │    ruby, csharp, swift, kotlin, ...      │ │   ║
║   └────────────────────────┴──────────────────────────────────────────┘ │   ║
║                   │                                                     │   ║
║                   ▼                                                     │   ║
║   ┌─────────────────────────────────────────────────────────────────────┐   ║
║   │                    Core Layer (core/)                               │   ║
║   │                   [leaf — no internal deps]                         │   ║
║   │                                                                     │   ║
║   │  config.py   discovery_api.py   paths_api.py   output.py           │   ║
║   │  registry.py runtime_state.py   enums.py       source_discovery.py │   ║
║   │  tooling.py  signal_patterns.py query.py       fallbacks.py        │   ║
║   └─────────────────────────────────────────────────────────────────────┘   ║
║                                                                            ║
║   ┌─────────────────────────────────────────────────────────────────────┐   ║
║   │              Top-level Facades (re-export stable API)               │   ║
║   │        state.py      scoring.py      versioning.py                 │   ║
║   └─────────────────────────────────────────────────────────────────────┘   ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**Dependency rules (strict, enforced in Rust via crate boundaries):**

| Layer          | May depend on                            |
|----------------|------------------------------------------|
| `core/`        | Nothing (leaf crate)                     |
| `languages/`   | `core/`                                  |
| `engine/`      | `core/`, `languages/`                    |
| `intelligence/` | `core/`, `engine/` (via facades)        |
| `app/`         | All layers                               |
| Facades        | `engine/_state`, `engine/_scoring`       |

---

## 3. Data Flow Diagram — Scan Pipeline

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        deslop scan [--lang X] [path]                    │
└──────────────────────────────────────┬───────────────────────────────────┘
                                       │
                                       ▼
                          ┌────────────────────────┐
                          │  1. CLI Argument Parse  │
                          │     + Config Loading    │
                          │  (.desloppify/config)   │
                          └────────────┬───────────┘
                                       │
                                       ▼
                          ┌────────────────────────┐
                          │  2. Language Detection  │
                          │     + File Discovery   │
                          │  find_source_files()   │
                          │  → list[str] per lang  │
                          └────────────┬───────────┘
                                       │
                                       ▼
                          ┌────────────────────────┐
                          │  3. Zone Classification │
                          │                        │
                          │  Each file → Zone:     │
                          │   production, test,    │
                          │   config, generated,   │
                          │   vendor               │
                          │                        │
                          │  Rules applied per-lang│
                          │  (ZoneRule patterns)   │
                          └────────────┬───────────┘
                                       │
                                       ▼
              ┌────────────────────────────────────────────────┐
              │  4. Per-Language Phase Execution (ordered)     │
              │                                                │
              │  For each registered DetectorPhase in order:   │
              │                                                │
              │   ┌──────────────────────────────────────────┐ │
              │   │ Phase: "Structural analysis"             │ │
              │   │  → large files, complexity, god classes  │ │
              │   │  → TODOs, nesting depth, cyclomatic      │ │
              │   ├──────────────────────────────────────────┤ │
              │   │ Phase: "Linter (ESLint/ruff/clippy/...)" │ │
              │   │  → subprocess exec → parse output        │ │
              │   ├──────────────────────────────────────────┤ │
              │   │ Phase: "AST smells"                      │ │
              │   │  → tree-sitter pattern matching          │ │
              │   ├──────────────────────────────────────────┤ │
              │   │ Phase: "Coupling + cycles + orphaned"    │ │
              │   │  → import graph analysis                 │ │
              │   ├──────────────────────────────────────────┤ │
              │   │ Phase: "Security"                        │ │
              │   │  → secret/vuln pattern detection         │ │
              │   ├──────────────────────────────────────────┤ │
              │   │ Phase: "Test coverage"                   │ │
              │   │  → test-file mapping analysis            │ │
              │   ├──────────────────────────────────────────┤ │
              │   │ Phase: "Subjective review"               │ │
              │   │  → coverage tracking for review freshness│ │
              │   ├──────────────────────────────────────────┤ │
              │   │ Phase: "Duplicates" / "Boilerplate"      │ │
              │   │  → function-level duplication detection   │ │
              │   └──────────────────────────────────────────┘ │
              │                                                │
              │  Each phase returns: (findings[], potentials{})│
              └──────────────────────┬─────────────────────────┘
                                     │
                                     ▼
                        ┌──────────────────────────┐
                        │  5. State Merge           │
                        │  merge_scan()             │
                        │                           │
                        │  ┌──────────────────────┐ │
                        │  │ upsert_findings()    │ │
                        │  │  new → open          │ │
                        │  │  existing → update   │ │
                        │  │  last_seen           │ │
                        │  │  reopen if was fixed │ │
                        │  ├──────────────────────┤ │
                        │  │ auto_resolve_        │ │
                        │  │  disappeared()       │ │
                        │  │  open → auto_resolved│ │
                        │  │  if not reproduced   │ │
                        │  ├──────────────────────┤ │
                        │  │ mark_stale_on_       │ │
                        │  │  mechanical_change() │ │
                        │  │  (subjective refresh)│ │
                        │  └──────────────────────┘ │
                        └────────────┬─────────────┘
                                     │
                                     ▼
     ┌───────────────────────────────────────────────────────────────┐
     │  6. Scoring Pipeline  (compute_score_bundle)                 │
     │                                                               │
     │  ┌───────────────────────────────────────────────────────┐    │
     │  │ a. Per-finding weight = confidence_weight × tier_wt   │    │
     │  │    CONFIDENCE_WEIGHTS: high=1.0, medium=0.7, low=0.3  │    │
     │  ├───────────────────────────────────────────────────────┤    │
     │  │ b. Per-detector: group by file → file cap multiplier  │    │
     │  │    FILE_CAP: 1-2 findings=1.0, 3-5=1.5, 6+=2.0       │    │
     │  ├───────────────────────────────────────────────────────┤    │
     │  │ c. Weighted failure sum per detector                  │    │
     │  ├───────────────────────────────────────────────────────┤    │
     │  │ d. Map detectors → dimensions (5 mechanical)          │    │
     │  ├───────────────────────────────────────────────────────┤    │
     │  │ e. dim_score = max(0, (checks - wf) / checks) × 100  │    │
     │  ├───────────────────────────────────────────────────────┤    │
     │  │ f. Pool blend: 40% mechanical + 60% subjective        │    │
     │  ├───────────────────────────────────────────────────────┤    │
     │  │ g. 4-channel output:                                  │    │
     │  │    overall, objective, strict, verified_strict         │    │
     │  └───────────────────────────────────────────────────────┘    │
     └──────────────────────────────┬────────────────────────────────┘
                                    │
                                    ▼
                       ┌──────────────────────────┐
                       │  7. Anti-Gaming Integrity │
                       │                           │
                       │  Subjective integrity:    │
                       │  target_match detection   │
                       │  (tolerance: ±0.05)       │
                       │                           │
                       │  Status: disabled │ pass  │
                       │         │ warn │ penalized│
                       │                           │
                       │  Matched dims → reset to 0│
                       └────────────┬──────────────┘
                                    │
                                    ▼
                       ┌──────────────────────────┐
                       │  8. Plan Reconciliation   │
                       │  reconcile_plan_after_    │
                       │  scan()                   │
                       │                           │
                       │  • Supersede dead findings│
                       │    (90-day TTL prune)     │
                       │  • Resurface stale skips  │
                       │  • Remap candidates       │
                       └────────────┬──────────────┘
                                    │
                                    ▼
                       ┌──────────────────────────┐
                       │  9. State Persistence     │
                       │  save_state()             │
                       │                           │
                       │  → .desloppify/state.json │
                       │  Atomic write (tmp+rename)│
                       └────────────┬──────────────┘
                                    │
                                    ▼
                       ┌──────────────────────────┐
                       │  10. Narrative Computation│
                       │  compute_narrative()      │
                       │                           │
                       │  phase, headline, actions,│
                       │  strategy, tools, debt,   │
                       │  risk flags, reminders    │
                       └────────────┬──────────────┘
                                    │
                                    ▼
                       ┌──────────────────────────┐
                       │  11. Output Rendering     │
                       │                           │
                       │  Scorecard (terminal/PNG) │
                       │  JSON machine output      │
                       │  Tree-text view            │
                       │  Visualization (HTML)     │
                       └───────────────────────────┘
```

---

## 4. State Machine — Finding Lifecycle

```
                              ┌─────────────────────────────────────┐
                              │          New finding detected       │
                              │     (upsert_findings during scan)   │
                              └──────────────────┬──────────────────┘
                                                 │
                                                 ▼
                              ┌─────────────────────────────────────┐
                              │              OPEN                   │
                              │                                     │
                              │  first_seen: timestamp              │
                              │  last_seen:  updated each scan      │
                              │  reopen_count: 0 (initially)        │
                              │  tier: 1-4                          │
                              │  confidence: high/medium/low        │
                              └───┬──────┬──────┬──────────┬────────┘
                                  │      │      │          │
             ┌────────────────────┘      │      │          └────────────────────┐
             │                           │      │                              │
             ▼                           ▼      ▼                              ▼
 ┌───────────────────────┐  ┌────────────────┐  ┌──────────────────┐  ┌────────────────────┐
 │        FIXED          │  │ AUTO_RESOLVED  │  │    WONTFIX       │  │  FALSE_POSITIVE    │
 │                       │  │                │  │                  │  │                    │
 │ Trigger:              │  │ Trigger:       │  │ Trigger:         │  │ Trigger:           │
 │  `deslop resolve      │  │  Finding not   │  │  `deslop resolve │  │  `deslop resolve   │
 │   <pattern> fixed`    │  │  reproduced    │  │   <pattern>      │  │   <pattern>        │
 │                       │  │  on next scan  │  │   wontfix`       │  │   false_positive`  │
 │ resolved_at: ts       │  │                │  │                  │  │                    │
 │ resolution_attestation│  │ resolved_at: ts│  │ REQUIRES:        │  │ REQUIRES:          │
 │   kind: "manual"      │  │ note: auto     │  │  attestation     │  │  attestation       │
 │   text: user note     │  │                │  │  (--note or      │  │  (--note or        │
 │   scan_verified: bool │  │                │  │   --attestation) │  │   --attestation)   │
 │                       │  │                │  │                  │  │                    │
 │ Score mode:           │  │ Score mode:    │  │ Score mode:      │  │ Score mode:        │
 │  lenient: pass        │  │  lenient: pass │  │  lenient: pass   │  │  lenient: pass     │
 │  strict:  FAIL        │  │  strict:  pass │  │  strict:  FAIL ← │  │  strict:  pass     │
 │  verified: FAIL       │  │  verified: pass│  │  verified: FAIL  │  │  verified: FAIL    │
 │  (until scan-verified)│  │                │  │  (counts against │  │  (until scan-      │
 │                       │  │                │  │   strict score!) │  │   verified)        │
 └───────────┬───────────┘  └───────┬────────┘  └────────┬─────────┘  └─────────┬──────────┘
             │                      │                    │                      │
             │                      │                    │                      │
             └──────────────────────┴────────────────────┴──────────────────────┘
                                                 │
                                     ┌───────────▼───────────┐
                                     │     REOPEN → OPEN     │
                                     │                       │
                                     │ Triggers:             │
                                     │  • `deslop resolve    │
                                     │     <pattern> open`   │
                                     │  • Finding reproduced │
                                     │    after fixed/auto   │
                                     │                       │
                                     │ Effects:              │
                                     │  reopen_count += 1    │
                                     │  status → "open"      │
                                     │  resolved_at → null   │
                                     │  resolution_attestation│
                                     │   .kind = "manual_    │
                                     │    reopen"            │
                                     │  wontfix_snapshot     │
                                     │   cleared             │
                                     │                       │
                                     │ CHRONIC REOPENER:     │
                                     │  reopen_count >= 2    │
                                     │  → flagged in diff    │
                                     │  → surfaced in work   │
                                     │    queue --chronic    │
                                     └───────────────────────┘
```

**Score mode failure sets** (which statuses count as failures):

| Score Mode        | Failure Statuses                                 |
|-------------------|--------------------------------------------------|
| `lenient`         | `{open}`                                         |
| `strict`          | `{open, wontfix}`                                |
| `verified_strict` | `{open, wontfix, fixed, false_positive}`         |

**Key invariants:**
- `wontfix` counts against strict score — it represents accepted technical debt
- `verified_strict` only credits scan-verified fixes (not manual attestations)
- `auto_resolved` passes in all modes — the tool confirmed the finding is gone
- Reopening always increments `reopen_count` (never reset to 0)

---

## 5. Scoring Pipeline Detail Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SCORING PIPELINE                                   │
│                                                                             │
│  INPUT: findings{}, potentials{detector → file_count}                      │
│         subjective_assessments{dimension → {score, ...}}                   │
│                                                                             │
│  ═══════════════════════════════════════════════════════════════════════    │
│                                                                             │
│  STEP 1: Per-Finding Weight                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  Standard detectors:  weight = CONFIDENCE_WEIGHTS[finding.confidence]│   │
│  │                       high=1.0  medium=0.7  low=0.3                 │   │
│  │                                                                      │   │
│  │  LOC-weighted (test_coverage): weight = finding.detail.loc_weight    │   │
│  │                                                                      │   │
│  │  Holistic review: weight × HOLISTIC_MULTIPLIER (10.0)               │   │
│  │                   (display/priority only — NOT in score computation) │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  STEP 2: File-Based Detector Grouping + Capping                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  For FILE_BASED_DETECTORS (smells, test_coverage, security, ...):   │   │
│  │                                                                      │   │
│  │    Group findings by file path                                       │   │
│  │    Sum weights per file                                              │   │
│  │                                                                      │   │
│  │    Non-LOC detectors apply tiered cap per file:                      │   │
│  │    ┌───────────────┬──────────────────────┐                          │   │
│  │    │ Findings/File │ Cap Value            │                          │   │
│  │    ├───────────────┼──────────────────────┤                          │   │
│  │    │     1-2       │ _FILE_CAP_LOW  = 1.0 │                          │   │
│  │    │     3-5       │ _FILE_CAP_MID  = 1.5 │                          │   │
│  │    │     6+        │ _FILE_CAP_HIGH = 2.0 │                          │   │
│  │    └───────────────┴──────────────────────┘                          │   │
│  │                                                                      │   │
│  │    LOC-weighted detectors: cap = first finding's loc_weight          │   │
│  │                                                                      │   │
│  │    weighted_failure_file = min(sum_of_weights, cap)                  │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  STEP 3: Weighted Failure Sum Per Detector                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  File-based:   WF = Σ(min(file_weight_sum, file_cap)) + holistic    │   │
│  │  Non-file-based: WF = Σ(finding_weights for failures)               │   │
│  │                                                                      │   │
│  │  Computed for each ScoreMode (lenient, strict, verified_strict)      │   │
│  │  using FAILURE_STATUSES_BY_MODE to filter which findings fail       │   │
│  │                                                                      │   │
│  │  Zone exclusion: security findings in test/config/generated/vendor   │   │
│  │  are excluded from scoring.                                          │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  STEP 4: Map Detectors → Dimensions                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  MECHANICAL DIMENSIONS (derived from DETECTOR_SCORING_POLICIES):     │   │
│  │                                                                      │   │
│  │  ┌─────────────────┬───────────────────────────────────────────────┐ │   │
│  │  │ Dimension       │ Detectors                                     │ │   │
│  │  ├─────────────────┼───────────────────────────────────────────────┤ │   │
│  │  │ File health     │ structural                              T3   │ │   │
│  │  │ Code quality    │ unused, logs, exports, deprecated, props,    │ │   │
│  │  │                 │ smells, react, dict_keys, orphaned,          │ │   │
│  │  │                 │ flat_dirs, naming, facade, patterns,         │ │   │
│  │  │                 │ single_use, coupling, stale_exclude,         │ │   │
│  │  │                 │ responsibility_cohesion, private_imports,     │ │   │
│  │  │                 │ layer_violation, global_mutable_config  T3   │ │   │
│  │  │ Duplication     │ dupes, boilerplate_duplication          T3   │ │   │
│  │  │ Test health     │ test_coverage, subjective_review        T4   │ │   │
│  │  │ Security        │ security, cycles                        T4   │ │   │
│  │  └─────────────────┴───────────────────────────────────────────────┘ │   │
│  │                                                                      │   │
│  │  NON-SCORED DETECTORS:                                               │   │
│  │    review  → scored via subjective assessments only                  │   │
│  │    concerns → scored via subjective assessments only                 │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  STEP 5: Per-Dimension Score                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  For each dimension:                                                 │   │
│  │    total_checks = Σ(potential for each detector in dimension)        │   │
│  │    total_weighted_failures = Σ(WF for each detector)                 │   │
│  │                                                                      │   │
│  │    dim_score = max(0, (total_checks - total_WF) / total_checks)×100 │   │
│  │                                                                      │   │
│  │  For subjective dimensions (from review assessments):                │   │
│  │    dim_score = assessment_score directly (0-100)                     │   │
│  │    checks = SUBJECTIVE_CHECKS (10, synthetic)                       │   │
│  │    pass_rate = score / 100                                           │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  STEP 6: Pool-Weighted Blend                                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │   │
│  │  │ MECHANICAL POOL (40% = MECHANICAL_WEIGHT_FRACTION)              │ │   │
│  │  │                                                                 │ │   │
│  │  │ Per-dimension weights:                                          │ │   │
│  │  │   file health: 2.0,  code quality: 1.0,  duplication: 1.0     │ │   │
│  │  │   test health: 1.0,  security: 1.0                             │ │   │
│  │  │                                                                 │ │   │
│  │  │ Sample dampening: effective_wt = configured_wt ×               │ │   │
│  │  │   min(1.0, checks / MIN_SAMPLE)     [MIN_SAMPLE = 200]        │ │   │
│  │  │                                                                 │ │   │
│  │  │ mech_avg = Σ(score × effective_wt) / Σ(effective_wt)           │ │   │
│  │  └─────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │   │
│  │  │ SUBJECTIVE POOL (60% = SUBJECTIVE_WEIGHT_FRACTION)             │ │   │
│  │  │                                                                 │ │   │
│  │  │ Per-dimension weights (12 dimensions):                          │ │   │
│  │  │   high elegance: 22.0    mid elegance: 22.0                    │ │   │
│  │  │   low elegance:  12.0    contracts:    12.0                    │ │   │
│  │  │   type safety:   12.0    abstraction:   8.0                    │ │   │
│  │  │   logic clarity:  6.0    structure nav:  5.0                   │ │   │
│  │  │   error consist:  3.0    naming quality: 2.0                   │ │   │
│  │  │   AI gen debt:    1.0    design cohere: 10.0                   │ │   │
│  │  │                                                                 │ │   │
│  │  │ subj_avg = Σ(score × weight) / Σ(weight)                      │ │   │
│  │  └─────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                      │   │
│  │  overall = mech_avg × 0.40 + subj_avg × 0.60                       │   │
│  │                                                                      │   │
│  │  Edge cases:                                                         │   │
│  │    No subjective data → overall = mech_avg (fraction = 1.0)         │   │
│  │    No mechanical data → overall = subj_avg (fraction = 1.0)         │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  STEP 7: 4-Channel Output                                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  ┌───────────────────┬──────────────────────────────────────────┐    │   │
│  │  │ Channel           │ Description                              │    │   │
│  │  ├───────────────────┼──────────────────────────────────────────┤    │   │
│  │  │ overall_score     │ lenient mode, mech + subjective pools    │    │   │
│  │  │ objective_score   │ lenient mode, mechanical pool only       │    │   │
│  │  │ strict_score      │ strict mode (open + wontfix fail)        │    │   │
│  │  │ verified_strict   │ verified_strict (only scan-verified)     │    │   │
│  │  └───────────────────┴──────────────────────────────────────────┘    │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Work Queue Ranking Algorithm

The work queue (`deslop next`) presents prioritized findings to the user. Items
are sorted by a composite key that ensures clusters surface first, mechanical
issues outrank subjective ones at the same tier, and higher-confidence findings
rank higher.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    WORK QUEUE ITEM TYPES                                   │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐              │
│  │   cluster    │  │   finding    │  │ subjective_dimension │              │
│  │  (grouped    │  │  (individual │  │  (dimension-level    │              │
│  │   work unit) │  │   issue)     │  │   assessment item)   │              │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘              │
│         │                 │                     │                          │
│         ▼                 ▼                     ▼                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                       SORT KEY COMPUTATION                          │   │
│  │                                                                      │   │
│  │  CLUSTERS:                                                           │   │
│  │    key = (                                                           │   │
│  │      0,                         ← always sort first                 │   │
│  │      action_priority,           ← auto_fix=0, reorganize=1,         │   │
│  │                                    refactor=2, manual_fix=3         │   │
│  │      -member_count,             ← bigger clusters first             │   │
│  │      id                         ← tiebreaker (stable sort)          │   │
│  │    )                                                                 │   │
│  │                                                                      │   │
│  │  MECHANICAL FINDINGS:                                                │   │
│  │    key = (                                                           │   │
│  │      effective_tier,            ← T1=1, T2=2, T3=3, T4=4           │   │
│  │      0,                         ← mechanical before subjective      │   │
│  │      confidence_rank,           ← CONFIDENCE_ORDER:                 │   │
│  │                                    high=0, medium=1, low=2          │   │
│  │      -review_weight,            ← higher review weight first        │   │
│  │      -count,                    ← more occurrences first            │   │
│  │      id                         ← tiebreaker                        │   │
│  │    )                                                                 │   │
│  │                                                                      │   │
│  │  SUBJECTIVE FINDINGS / DIMENSIONS:                                   │   │
│  │    key = (                                                           │   │
│  │      effective_tier,            ← always T4 (forced)                 │   │
│  │      1,                         ← subjective sorts AFTER mechanical │   │
│  │      subjective_score_value,    ← lowest score first                │   │
│  │      id                         ← tiebreaker                        │   │
│  │    )                                                                 │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  EFFECTIVE ORDERING (top to bottom):                                       │
│                                                                             │
│    1. Clusters       (auto_fix → reorganize → refactor → manual_fix)       │
│    2. T1 mechanical  (high conf → medium → low, by -count)                 │
│    3. T2 mechanical                                                        │
│    4. T3 mechanical                                                        │
│    5. T4 mechanical                                                        │
│    6. T4 subjective  (lowest score first)                                  │
│                                                                             │
│  KEY POLICY:                                                               │
│    • Subjective findings are ALWAYS forced to T4 (effective_tier=4)        │
│    • Subjective items never outrank mechanical T1/T2/T3 items              │
│    • Clusters always outrank unclustered items                             │
│    • Chronic reopeners (reopen_count ≥ 2) surfaced via --chronic filter    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Review Pipeline Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          REVIEW PIPELINE                                   │
│                                                                             │
│  ══════════════════════════════                                             │
│  PHASE 1: PREPARE                                                          │
│  ══════════════════════════════                                             │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ prepare_review() / prepare_holistic_review()                         │  │
│  │                                                                       │  │
│  │  ┌───────────────────────┐   ┌──────────────────────────────────┐    │  │
│  │  │ File Selection        │   │ Dimension Resolution              │    │  │
│  │  │                       │   │                                    │    │  │
│  │  │ • file_finder(path)   │   │ • load_dimensions_for_lang()      │    │  │
│  │  │ • zone filtering      │   │ • CLI dims > config dims >        │    │  │
│  │  │ • staleness check     │   │   default dims                    │    │  │
│  │  │ • content_hash diff   │   │ • Invalid dim validation          │    │  │
│  │  └───────────┬───────────┘   └──────────────┬───────────────────┘    │  │
│  │              │                                │                       │  │
│  │              ▼                                ▼                       │  │
│  │  ┌──────────────────────────────────────────────────────────────┐    │  │
│  │  │ Packet Generation (BLIND — no scores visible to reviewer)   │    │  │
│  │  │                                                              │    │  │
│  │  │ Per-file packets:                                            │    │  │
│  │  │   { file, content, zone, loc, neighbors{imports, importers}, │    │  │
│  │  │     existing_findings }                                      │    │  │
│  │  │                                                              │    │  │
│  │  │ Holistic packets (investigation_batches):                    │    │  │
│  │  │   { dimensions, files_to_read, concern_signals,             │    │  │
│  │  │     historical_issue_focus }                                 │    │  │
│  │  │                                                              │    │  │
│  │  │ Context signals:                                             │    │  │
│  │  │   dep_graph, area map, codebase_stats                       │    │  │
│  │  │                                                              │    │  │
│  │  │ ⚠ NO SCORES in packet — prevents anchoring bias             │    │  │
│  │  └──────────────────────────────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                       │                                     │
│                                       ▼                                     │
│  ══════════════════════════════                                             │
│  PHASE 2: EXECUTION                                                        │
│  ══════════════════════════════                                             │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  ┌─────────────────────────┐  ┌──────────────────────────────────┐   │  │
│  │  │ PATH A: Codex Subagent  │  │ PATH B: Claude External          │   │  │
│  │  │                         │  │                                    │   │  │
│  │  │ • Parallel batch exec   │  │ • Session-based auth              │   │  │
│  │  │ • Each batch = one      │  │ • Token + expiry management       │   │  │
│  │  │   investigation scope   │  │ • Single-session review           │   │  │
│  │  │ • Structured JSON out   │  │ • Findings + assessments output   │   │  │
│  │  └────────────┬────────────┘  └──────────────┬───────────────────┘   │  │
│  │               │                               │                      │  │
│  │               └───────────────┬───────────────┘                      │  │
│  │                               ▼                                      │  │
│  │              ┌──────────────────────────────┐                        │  │
│  │              │ Result Normalization          │                        │  │
│  │              │                               │                        │  │
│  │              │ • Schema validation           │                        │  │
│  │              │ • Confidence normalization    │                        │  │
│  │              │   (high/medium/low)           │                        │  │
│  │              │ • Tier derivation from        │                        │  │
│  │              │   confidence + scope          │                        │  │
│  │              │ • Dimension key normalization │                        │  │
│  │              └──────────────────────────────┘                        │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                       │                                     │
│                                       ▼                                     │
│  ══════════════════════════════                                             │
│  PHASE 3: IMPORT + MERGE                                                   │
│  ══════════════════════════════                                             │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                                                                       │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │ Deduplication via Conceptual Similarity                         │  │  │
│  │  │                                                                 │  │  │
│  │  │ Jaccard word-set similarity on finding summaries:               │  │  │
│  │  │   words_a = set(summary_a.lower().split())                     │  │  │
│  │  │   words_b = set(summary_b.lower().split())                     │  │  │
│  │  │   similarity = |words_a ∩ words_b| / |words_a ∪ words_b|      │  │  │
│  │  │                                                                 │  │  │
│  │  │ If similarity > threshold → deduplicate (keep higher-conf)     │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  │                                                                       │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │ 4-Tier Trust Model                                              │  │  │
│  │  │                                                                 │  │  │
│  │  │  ┌─────────────────────┬──────────────────────────────────────┐ │  │  │
│  │  │  │ Trust Level         │ Behavior                             │ │  │  │
│  │  │  ├─────────────────────┼──────────────────────────────────────┤ │  │  │
│  │  │  │ trusted_internal    │ Findings + assessments imported,    │ │  │  │
│  │  │  │                     │ scores applied directly              │ │  │  │
│  │  │  ├─────────────────────┼──────────────────────────────────────┤ │  │  │
│  │  │  │ attested_external   │ Findings + assessments imported,    │ │  │  │
│  │  │  │                     │ human attestation required to apply │ │  │  │
│  │  │  ├─────────────────────┼──────────────────────────────────────┤ │  │  │
│  │  │  │ manual_override     │ Direct score override with          │ │  │  │
│  │  │  │                     │ attestation + audit trail            │ │  │  │
│  │  │  ├─────────────────────┼──────────────────────────────────────┤ │  │  │
│  │  │  │ findings_only       │ Findings imported, no assessment    │ │  │  │
│  │  │  │                     │ scores applied                       │ │  │  │
│  │  │  └─────────────────────┴──────────────────────────────────────┘ │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  │                                                                       │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │ Assessment Storage (store_assessments)                          │  │  │
│  │  │                                                                 │  │  │
│  │  │  • Holistic assessments OVERWRITE per-file for same dimension  │  │  │
│  │  │  • Per-file assessments DO NOT overwrite holistic              │  │  │
│  │  │  • Each assessment: {score, source, assessed_at, components}   │  │  │
│  │  │  • Score clamped to [0, 100]                                   │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  │                                                                       │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │  │
│  │  │ Scoring Integration                                             │  │  │
│  │  │                                                                 │  │  │
│  │  │  Subjective dimensions scored by assessment score directly.     │  │  │
│  │  │  Resolving review findings does NOT change dimension scores —   │  │  │
│  │  │  only a fresh review import updates them.                       │  │  │
│  │  │                                                                 │  │  │
│  │  │  Stale marking: when mechanical findings change, affected       │  │  │
│  │  │  subjective assessments are marked needs_review_refresh=true    │  │  │
│  │  │  (score preserved, not zeroed).                                 │  │  │
│  │  └─────────────────────────────────────────────────────────────────┘  │  │
│  │                                                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Concern Bridge** — mechanical findings feed into subjective review:

```
  Mechanical Findings                    Subjective Review
  ─────────────────                      ─────────────────
  structural ──────────┐
  smells ──────────────┤
  coupling ────────────┤   generate_concerns()     ┌────────────────┐
  responsibility ──────┼──────────────────────────▶│ Concern objects │
  dupes ───────────────┤   (ephemeral, computed    │ type, file,    │
  orphaned ────────────┤    on-demand, never       │ evidence,      │
  naming ──────────────┘    persisted)             │ question       │
                                                    └───────┬────────┘
                                                            │
                              LLM evaluates concern ───────▶│
                                                            │
                         Confirmed → persistent Finding ◀───┘
                         Dismissed → concern_dismissals{}
```

---

## 8. Language Plugin Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     LANGUAGE PLUGIN FRAMEWORK                               │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    LangConfig (base type)                             │  │
│  │                                                                       │  │
│  │  name: str               extensions: [str]      exclusions: [str]    │  │
│  │  default_src: str        entry_patterns: [str]   barrel_names: {str} │  │
│  │  phases: [DetectorPhase] fixers: {name: FixerConfig}                 │  │
│  │  build_dep_graph: fn     extract_functions: fn    file_finder: fn    │  │
│  │  zone_rules: [ZoneRule]  detect_markers: [str]                       │  │
│  │  large_threshold: 500    complexity_threshold: 15                     │  │
│  │  integration_depth: "full" | "standard" | "shallow" | "minimal"     │  │
│  │  test_file_extensions    external_test_dirs: ["tests", "test"]       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    DetectorPhase                                      │  │
│  │                                                                       │  │
│  │  label: str  (e.g. "Structural analysis", "Security")                │  │
│  │  run: fn(path, lang) → (findings[], potentials{})                    │  │
│  │                                                                       │  │
│  │  Phases execute in registration order per language.                   │  │
│  │  Each phase may invoke external tools (subprocess) or internal       │  │
│  │  detectors (tree-sitter, pattern matching).                          │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    TreeSitterSpec                                     │  │
│  │                                                                       │  │
│  │  language: str           function_query: str      class_query: str   │  │
│  │  import_query: str       resolve_import: fn       file_extensions    │  │
│  │                                                                       │  │
│  │  When provided + tree-sitter-language-pack installed:                 │  │
│  │    → function extraction (enables duplicate detection)               │  │
│  │    → class extraction (enables god-class detection)                  │  │
│  │    → import resolution (enables coupling/orphan/cycle detection)     │  │
│  │    → AST complexity (nesting depth, cyclomatic, params, callbacks)   │  │
│  │    → AST smells (pattern-based detection)                            │  │
│  │    → Unused import detection                                         │  │
│  │    → Responsibility cohesion analysis                                │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ═══════════════════════════════════════════════════════════════            │
│                                                                             │
│  FULL-DEPTH PLUGINS (6) — custom phases, detectors, fixers:               │
│                                                                             │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                              │
│  │  Python    │ │ TypeScript │ │ JavaScript │                              │
│  │            │ │            │ │            │                              │
│  │ ruff       │ │ ESLint     │ │ ESLint     │                              │
│  │ tree-sitter│ │ tree-sitter│ │ tree-sitter│                              │
│  │ custom AST │ │ React      │ │ React      │                              │
│  │ phases     │ │ detectors  │ │ detectors  │                              │
│  └────────────┘ └────────────┘ └────────────┘                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                              │
│  │   Rust     │ │    Go      │ │   Java     │                              │
│  │            │ │            │ │            │                              │
│  │ clippy     │ │ golangci   │ │ custom     │                              │
│  │ tree-sitter│ │ tree-sitter│ │ detectors  │                              │
│  │ cargo parse│ │ go vet     │ │ Maven/     │                              │
│  │            │ │            │ │ Gradle     │                              │
│  └────────────┘ └────────────┘ └────────────┘                              │
│                                                                             │
│  GENERIC PLUGINS (22+) — via generic_lang() factory:                       │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      generic_lang() Flow                             │   │
│  │                                                                      │   │
│  │  Input: name, extensions, tools[], treesitter_spec?                  │   │
│  │                                                                      │   │
│  │  1. normalize_tool_specs()                                           │   │
│  │     ├─ Validate: label, cmd, fmt, id, tier, fix_cmd?                │   │
│  │     └─ Supported formats: eslint, ruff, cargo, golangci,            │   │
│  │        rubocop, gnu, json                                            │   │
│  │                                                                      │   │
│  │  2. For each tool:                                                   │   │
│  │     ├─ register_detector() → DetectorMeta in registry               │   │
│  │     ├─ register_scoring_policy() → dimension + tier assignment       │   │
│  │     └─ make_generic_fixer() if fix_cmd present                      │   │
│  │                                                                      │   │
│  │  3. Build phases:                                                    │   │
│  │     ├─ Tool-specific phases (linter execution + output parsing)      │   │
│  │     ├─ Structural analysis (always)                                  │   │
│  │     ├─ AST smells, cohesion, unused imports (if tree-sitter)         │   │
│  │     ├─ Signature analysis (if function extraction available)         │   │
│  │     ├─ Security scan                                                 │   │
│  │     ├─ Coupling + cycles (if dep graph available)                    │   │
│  │     ├─ Test coverage (if dep graph available)                        │   │
│  │     └─ Subjective review + Duplicates (tail phases)                 │   │
│  │                                                                      │   │
│  │  4. Set integration_depth:                                           │   │
│  │     ├─ "full" → custom full-depth plugin                            │   │
│  │     ├─ "standard" → tree-sitter upgraded from shallow               │   │
│  │     ├─ "shallow" → linter-only, no AST                              │   │
│  │     └─ "minimal" → bare minimum                                      │   │
│  │                                                                      │   │
│  │  5. register_generic_lang(name, cfg) → language registry             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Languages: ruby, csharp, swift, kotlin, scala, php, perl, r,             │
│  haskell, ocaml, fsharp, elixir, erlang, clojure, lua, dart,              │
│  zig, nim, gdscript, powershell, bash, cxx                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Phase ordering** (typical generic plugin with tree-sitter):

```
  1. Tool-specific linter phase(s)    [external subprocess]
  2. Structural analysis               [complexity, god classes, file health]
  3. AST smells                        [tree-sitter pattern detection]
  4. Responsibility cohesion           [tree-sitter class analysis]
  5. Unused imports                    [tree-sitter import analysis]
  6. Signature analysis                [function signature patterns]
  7. Security                          [secret/vuln patterns]
  8. Coupling + cycles + orphaned      [import graph analysis]
  9. Test coverage                     [test-file mapping]
  10. Subjective review                [review coverage tracking]
  11. Boilerplate duplication          [function-level dedup]
  12. Duplicates                       [content-level dedup]
```

---

## 9. Narrative/Coaching System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     NARRATIVE/COACHING PIPELINE                             │
│                    compute_narrative(state, context)                        │
│                                                                             │
│  ══════════════════════════════════════════════                             │
│  PHASE DETECTION (7 phases based on scan history)                          │
│  ══════════════════════════════════════════════                             │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  scan_history[] ──▶ _detect_phase() ──▶ phase: str                  │   │
│  │                                                                      │   │
│  │  Decision tree:                                                      │   │
│  │                                                                      │   │
│  │  ┌─────────────────────┐                                            │   │
│  │  │ history empty or    │──yes──▶ "first_scan"                       │   │
│  │  │ len(history) == 1?  │                                            │   │
│  │  └─────────┬───────────┘                                            │   │
│  │            no                                                        │   │
│  │            ▼                                                         │   │
│  │  ┌─────────────────────┐                                            │   │
│  │  │ strict dropped from │──yes──▶ "regression"                       │   │
│  │  │ previous > 0.5pt?   │         (prev_strict - curr_strict > 0.5)  │   │
│  │  └─────────┬───────────┘                                            │   │
│  │            no                                                        │   │
│  │            ▼                                                         │   │
│  │  ┌─────────────────────┐                                            │   │
│  │  │ last 3 scans ±0.5?  │──yes──▶ "stagnation"                      │   │
│  │  │ (spread ≤ 0.5)      │         (requires 3+ scans)               │   │
│  │  └─────────┬───────────┘                                            │   │
│  │            no                                                        │   │
│  │            ▼                                                         │   │
│  │  ┌─────────────────────┐                                            │   │
│  │  │ scans 2-5 and       │──yes──▶ "early_momentum"                  │   │
│  │  │ score rising?       │                                            │   │
│  │  └─────────┬───────────┘                                            │   │
│  │            no                                                        │   │
│  │            ▼                                                         │   │
│  │  ┌─────────────────────┐                                            │   │
│  │  │ strict > 93?        │──yes──▶ "maintenance"                     │   │
│  │  └─────────┬───────────┘                                            │   │
│  │            no                                                        │   │
│  │            ▼                                                         │   │
│  │  ┌─────────────────────┐                                            │   │
│  │  │ strict > 80?        │──yes──▶ "refinement"                      │   │
│  │  └─────────┬───────────┘                                            │   │
│  │            no                                                        │   │
│  │            ▼                                                         │   │
│  │          "middle_grind"                                              │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                       │                                     │
│                                       ▼                                     │
│  ══════════════════════════════════════════════                             │
│  ACTION COMPUTATION (6 action types)                                       │
│  ══════════════════════════════════════════════                             │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  by_detector{} + dimension_scores{} + state + debt                  │   │
│  │                      │                                               │   │
│  │                      ▼                                               │   │
│  │            compute_actions(ActionContext)                             │   │
│  │                      │                                               │   │
│  │                      ▼                                               │   │
│  │  ┌───────────────────────────────────────────────────────────────┐   │   │
│  │  │ ActionType          │ Description                             │   │   │
│  │  ├─────────────────────┼─────────────────────────────────────────┤   │   │
│  │  │ "auto_fix"          │ Findings with available fixers          │   │   │
│  │  │ "manual_fix"        │ Findings requiring manual intervention  │   │   │
│  │  │ "reorganize"        │ File structure / directory improvements │   │   │
│  │  │ "refactor"          │ Code restructuring recommendations     │   │   │
│  │  │ "issue_queue"       │ Pointer to work queue for more items   │   │   │
│  │  │ "debt_review"       │ Wontfix/false_positive debt review     │   │   │
│  │  └─────────────────────┴─────────────────────────────────────────┘   │   │
│  │                                                                      │   │
│  │  Each action includes:                                               │   │
│  │    priority, type, detector, count, description, command,            │   │
│  │    impact (score improvement estimate), dimension, gap, lane         │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                       │                                     │
│                                       ▼                                     │
│  ══════════════════════════════════════════════                             │
│  STRATEGY ENGINE                                                           │
│  ══════════════════════════════════════════════                             │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  compute_strategy(findings, by_detector, actions, phase, lang)      │   │
│  │                                                                      │   │
│  │  Outputs: {hint, focus_area, recommended_approach}                  │   │
│  │                                                                      │   │
│  │  Lane Grouping (union-find for parallelizable workstreams):         │   │
│  │    Actions touching the same files/detectors → same lane            │   │
│  │    Independent actions → parallel lanes                              │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                       │                                     │
│                                       ▼                                     │
│  ══════════════════════════════════════════════                             │
│  DIMENSION ANALYSIS                                                        │
│  ══════════════════════════════════════════════                             │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  _analyze_dimensions(dim_scores, history, state)                    │   │
│  │                                                                      │   │
│  │  Computes:                                                           │   │
│  │    • lowest:      dimension with lowest score                       │   │
│  │    • biggest_gap: dimension farthest below target                   │   │
│  │    • stagnant:    dimension unchanged across recent scans           │   │
│  │    • improving:   dimension showing upward trajectory               │   │
│  │    • declining:   dimension showing downward trajectory             │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                       │                                     │
│                                       ▼                                     │
│  ══════════════════════════════════════════════                             │
│  OUTPUT ASSEMBLY                                                           │
│  ══════════════════════════════════════════════                             │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  NarrativeResult {                                                   │   │
│  │    phase:             "first_scan" | "regression" | ...              │   │
│  │    headline:          context-aware 1-liner                          │   │
│  │    dimensions:        {lowest, biggest_gap, stagnant, ...}          │   │
│  │    actions:           [prioritized ActionItem list]                  │   │
│  │    strategy:          {hint, focus_area, approach}                   │   │
│  │    tools:             {fixers, move, plan, badge}                    │   │
│  │    debt:              {wontfix_count, overall_gap}                   │   │
│  │    milestone:         "Crossed 90%!" | null                         │   │
│  │    primary_action:    {command, description}                         │   │
│  │    why_now:           human-readable urgency explanation             │   │
│  │    verification_step: {command: "desloppify scan", reason: ...}     │   │
│  │    risk_flags:        [{type, severity, message}]                    │   │
│  │    strict_target:     {target, current, gap, state}                 │   │
│  │    reminders:         [contextual reminders with decay]             │   │
│  │  }                                                                   │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ══════════════════════════════════════════════                             │
│  MILESTONES (detected via _detect_milestone)                               │
│  ══════════════════════════════════════════════                             │
│                                                                             │
│    • "Crossed 90% strict!"        (prev < 90, curr ≥ 90)                  │
│    • "Crossed 80% strict!"        (prev < 80, curr ≥ 80)                  │
│    • "All T1 and T2 items cleared!" (0 open T1 + T2, had some before)     │
│    • "All T1 items cleared!"      (0 open T1, had some before)            │
│    • "Zero open findings!"        (0 open, total > 0)                     │
│                                                                             │
│  ══════════════════════════════════════════════                             │
│  REMINDER SYSTEM (with decay)                                              │
│  ══════════════════════════════════════════════                             │
│                                                                             │
│    Reminders are contextual nudges that decay after being shown:           │
│      • auto_fixers_available (when auto-fix actions exist)                 │
│      • high false_positive rates per (detector, zone)                      │
│      • badge/scorecard recommendations                                     │
│      • wontfix debt warnings                                               │
│      • review freshness nudges                                             │
│                                                                             │
│    Decay: _REMINDER_DECAY_THRESHOLD scans before re-showing               │
│    Tracked in reminder_history for persistence                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Rust Module Architecture (Target)

```
genesis-deslop/
├── Cargo.toml                          ← workspace root
├── ARCHITECTURE.md                     ← this document
│
├── crates/
│   ├── genesis-deslop-core/            ← leaf crate, no internal deps
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── config.rs               ← .desloppify/config.toml loading
│   │       ├── discovery.rs            ← source file discovery (find_source_files)
│   │       ├── paths.rs                ← project root, relative path resolution
│   │       ├── output.rs               ← output formatting, log helpers
│   │       ├── registry.rs             ← DetectorMeta, detector registry
│   │       ├── enums.rs                ← Confidence, Status, Tier (StrEnum equiv)
│   │       ├── runtime.rs              ← runtime state (scan_path, etc.)
│   │       ├── zones.rs                ← Zone enum, ZoneRule, zone classification
│   │       └── text_utils.rs           ← is_numeric, normalization helpers
│   │
│   ├── genesis-deslop-lang/            ← language framework + plugins
│   │   ├── Cargo.toml                  ← depends on: genesis-deslop-core
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── framework/
│   │       │   ├── mod.rs
│   │       │   ├── types.rs            ← LangConfig, DetectorPhase, FixerConfig
│   │       │   ├── generic.rs          ← generic_lang() factory
│   │       │   ├── treesitter/         ← tree-sitter integration
│   │       │   │   ├── mod.rs
│   │       │   │   ├── extractors.rs   ← function/class extraction
│   │       │   │   ├── imports.rs      ← dep graph building
│   │       │   │   ├── complexity.rs   ← nesting, cyclomatic, params
│   │       │   │   ├── smells.rs       ← AST smell patterns
│   │       │   │   └── phases.rs       ← phase builders
│   │       │   ├── parsers/            ← linter output parsers
│   │       │   │   ├── mod.rs
│   │       │   │   ├── eslint.rs
│   │       │   │   ├── ruff.rs
│   │       │   │   ├── cargo.rs
│   │       │   │   ├── golangci.rs
│   │       │   │   ├── rubocop.rs
│   │       │   │   └── gnu.rs
│   │       │   ├── discovery.rs        ← language detection heuristics
│   │       │   ├── phase_builders.rs   ← shared phase constructors
│   │       │   └── registry.rs         ← language registry
│   │       ├── plugins/
│   │       │   ├── mod.rs
│   │       │   ├── python.rs           ← full-depth
│   │       │   ├── typescript.rs       ← full-depth
│   │       │   ├── javascript.rs       ← full-depth
│   │       │   ├── rust.rs             ← full-depth
│   │       │   ├── go.rs               ← full-depth
│   │       │   ├── java.rs             ← full-depth
│   │       │   └── generic_all.rs      ← 22+ generic registrations
│   │       └── shared_phases.rs        ← structural, coupling, security
│   │
│   ├── genesis-deslop-engine/          ← detection, scoring, state, planning
│   │   ├── Cargo.toml                  ← depends on: core, lang
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── detectors/
│   │       │   ├── mod.rs
│   │       │   ├── base.rs             ← FunctionInfo, ComplexitySignal, GodRule
│   │       │   ├── complexity.rs
│   │       │   ├── coupling.rs
│   │       │   ├── dupes.rs
│   │       │   ├── gods.rs
│   │       │   ├── large.rs
│   │       │   ├── naming.rs
│   │       │   ├── orphaned.rs
│   │       │   ├── security/
│   │       │   ├── patterns/
│   │       │   ├── single_use.rs
│   │       │   └── ...                 ← 31+ detectors total
│   │       ├── scoring/
│   │       │   ├── mod.rs
│   │       │   ├── detection.rs        ← per-detector stats, file-based scoring
│   │       │   ├── policy.rs           ← DETECTOR_SCORING_POLICIES, Dimension
│   │       │   ├── results.rs          ← ScoreBundle, compute_score_bundle
│   │       │   └── subjective.rs       ← append_subjective_dimensions
│   │       ├── state/
│   │       │   ├── mod.rs
│   │       │   ├── schema.rs           ← Finding, StateModel, StateStats
│   │       │   ├── merge.rs            ← merge_scan, upsert_findings
│   │       │   ├── persistence.rs      ← load_state, save_state (atomic)
│   │       │   ├── resolution.rs       ← resolve_findings, match_findings
│   │       │   ├── filtering.rs        ← ignore patterns, scope filtering
│   │       │   └── noise.rs            ← finding noise budget
│   │       ├── work_queue/
│   │       │   ├── mod.rs
│   │       │   ├── ranking.rs          ← item_sort_key, build_finding_items
│   │       │   └── helpers.rs          ← scope/status matching
│   │       ├── plan/
│   │       │   ├── mod.rs
│   │       │   ├── schema.rs           ← PlanModel, SupersededEntry
│   │       │   ├── reconcile.rs        ← reconcile_plan_after_scan
│   │       │   ├── operations.rs       ← skip, unskip, override, resurface
│   │       │   ├── cluster.rs          ← auto_cluster
│   │       │   └── persistence.rs      ← plan.json load/save
│   │       ├── concerns.rs             ← Concern generator (mechanical→subjective)
│   │       └── policy/
│   │           ├── mod.rs
│   │           └── zones.rs            ← zone policy, excluded zones
│   │
│   ├── genesis-deslop-intel/           ← review, narrative, integrity
│   │   ├── Cargo.toml                  ← depends on: core, engine
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── review/
│   │       │   ├── mod.rs
│   │       │   ├── prepare.rs          ← prepare_review, prepare_holistic_review
│   │       │   ├── importing/
│   │       │   │   ├── mod.rs
│   │       │   │   ├── per_file.rs     ← import_review_findings
│   │       │   │   ├── holistic.rs     ← import_holistic_findings
│   │       │   │   └── shared.rs       ← store_assessments, dedup
│   │       │   ├── dimensions/
│   │       │   │   ├── mod.rs
│   │       │   │   ├── data.rs         ← dimension prompt data
│   │       │   │   ├── selection.rs    ← resolve_dimensions
│   │       │   │   └── metadata.rs     ← display names, weights
│   │       │   ├── context.rs          ← review context building
│   │       │   ├── policy.rs           ← DimensionPolicy, trust model
│   │       │   └── selection.rs        ← file selection for review
│   │       ├── narrative/
│   │       │   ├── mod.rs
│   │       │   ├── core.rs             ← compute_narrative entry point
│   │       │   ├── phase.rs            ← _detect_phase, _detect_milestone
│   │       │   ├── action_engine.rs    ← compute_actions
│   │       │   ├── action_models.rs    ← ActionItem, ActionType, ToolInventory
│   │       │   ├── strategy.rs         ← compute_strategy, lane grouping
│   │       │   ├── dimensions.rs       ← _analyze_dimensions, _analyze_debt
│   │       │   ├── headline.rs         ← _compute_headline
│   │       │   └── reminders.rs        ← _compute_reminders (with decay)
│   │       └── integrity.rs            ← anti-gaming, target-match detection
│   │
│   └── genesis-deslop-cli/             ← user-facing CLI
│       ├── Cargo.toml                  ← depends on: all crates, clap
│       └── src/
│           ├── main.rs
│           ├── commands/
│           │   ├── mod.rs
│           │   ├── scan.rs             ← deslop scan
│           │   ├── next.rs             ← deslop next (work queue)
│           │   ├── fix.rs              ← deslop fix <fixer>
│           │   ├── resolve.rs          ← deslop resolve <pattern> <status>
│           │   ├── review.rs           ← deslop review (prepare/import)
│           │   ├── show.rs             ← deslop show (findings/scores)
│           │   ├── plan.rs             ← deslop plan (skip/override/cluster)
│           │   ├── status.rs           ← deslop status
│           │   ├── config.rs           ← deslop config
│           │   ├── detect.rs           ← deslop detect (single detector)
│           │   ├── exclude.rs          ← deslop exclude
│           │   ├── langs.rs            ← deslop langs
│           │   ├── viz.rs              ← deslop viz (HTML visualization)
│           │   ├── zone.rs             ← deslop zone
│           │   ├── move_cmd.rs         ← deslop move (file reorganization)
│           │   ├── update_skill.rs     ← deslop update-skill
│           │   └── dev.rs              ← deslop dev (scaffolding)
│           └── output/
│               ├── mod.rs
│               ├── scorecard.rs        ← terminal + PNG scorecard rendering
│               ├── tree_text.rs        ← tree-style finding display
│               └── visualize.rs        ← HTML dashboard generation
│
└── tests/                              ← integration tests
    ├── scan_integration.rs
    ├── scoring_property.rs
    └── state_roundtrip.rs
```

**Crate dependency graph:**

```
                    ┌──────────────────────┐
                    │ genesis-deslop-cli   │
                    │ (binary crate)       │
                    └──┬───┬───┬───┬───────┘
                       │   │   │   │
          ┌────────────┘   │   │   └────────────────────┐
          │                │   │                         │
          ▼                │   ▼                         ▼
┌──────────────────┐       │  ┌──────────────────┐  ┌──────────────────┐
│genesis-deslop-   │       │  │genesis-deslop-   │  │genesis-deslop-   │
│  intel           │       │  │  engine           │  │  lang            │
│                  │       │  │                    │  │                  │
│ review/          │       │  │ detectors/         │  │ framework/       │
│ narrative/       │       │  │ scoring/           │  │ plugins/         │
│ integrity        │       │  │ state/             │  │ treesitter/      │
└──────┬───────────┘       │  │ work_queue/        │  └──────┬───────────┘
       │                   │  │ plan/              │         │
       │                   │  │ concerns           │         │
       │                   │  └──────┬─────────────┘         │
       │                   │         │                       │
       └───────────────────┼─────────┘                       │
                           │         │                       │
                           ▼         ▼                       ▼
                    ┌──────────────────────────────────────────┐
                    │          genesis-deslop-core              │
                    │          (leaf library crate)             │
                    │                                          │
                    │  config, discovery, paths, output,       │
                    │  registry, enums, zones, runtime         │
                    └──────────────────────────────────────────┘
```

**Key Rust design decisions:**

| Concern | Approach |
|---------|----------|
| Finding/State types | `serde::{Serialize, Deserialize}` structs, not `TypedDict` |
| Enum dispatch | Rust enums for `Status`, `Confidence`, `Tier`, `Zone` |
| Plugin system | Trait objects (`dyn LangPlugin`) or enum dispatch for 30 languages |
| Scoring policy | Static `phf::Map` or `lazy_static!` for `DETECTOR_SCORING_POLICIES` |
| State persistence | `serde_json` with atomic write (write-tmp + rename) |
| External tool invocation | `tokio::process::Command` for async subprocess execution |
| tree-sitter integration | `tree-sitter` crate with language grammars as features |
| CLI | `clap` derive macros for 17 commands |
| Error handling | `thiserror` for library crates, `anyhow` for CLI |
| Parallelism | `rayon` for per-file detector phases, `tokio` for linter subprocess I/O |
| Testing | Property-based tests (`proptest`) for scoring invariants |

**Migration strategy:**

1. `genesis-deslop-core` first — pure types and utilities, no business logic deps
2. `genesis-deslop-engine/state` + `scoring` — the mathematical core, extensively
   property-tested against Python reference output
3. `genesis-deslop-lang` — start with 1 full-depth plugin (Python), validate
   finding parity
4. `genesis-deslop-engine/detectors` — port detectors one at a time, each with
   golden-file tests from Python output
5. `genesis-deslop-intel` — review and narrative last (most complex, most
   heuristic-heavy)
6. `genesis-deslop-cli` — final integration, can initially shell out to Python
   for unported subsystems

---

## Appendix: Key Constants Reference

| Constant | Value | Location |
|----------|-------|----------|
| `MECHANICAL_WEIGHT_FRACTION` | 0.40 | `scoring/policy` |
| `SUBJECTIVE_WEIGHT_FRACTION` | 0.60 | `scoring/policy` |
| `MIN_SAMPLE` | 200 | `scoring/policy` |
| `HOLISTIC_MULTIPLIER` | 10.0 | `scoring/policy` |
| `HOLISTIC_POTENTIAL` | 10 | `scoring/policy` |
| `SUBJECTIVE_CHECKS` | 10 | `scoring/policy` |
| `SUBJECTIVE_TARGET_MATCH_TOLERANCE` | 0.05 | `scoring/policy` |
| `CONFIDENCE_WEIGHTS` | high=1.0, med=0.7, low=0.3 | `scoring/policy` |
| `TIER_WEIGHTS` | T1=1, T2=2, T3=3, T4=4 | `scoring/policy` |
| `_FILE_CAP_LOW` | 1.0 (1-2 findings/file) | `scoring/detection` |
| `_FILE_CAP_MID` | 1.5 (3-5 findings/file) | `scoring/detection` |
| `_FILE_CAP_HIGH` | 2.0 (6+ findings/file) | `scoring/detection` |
| `SUPERSEDED_TTL_DAYS` | 90 | `plan/reconcile` |
| `_REMINDER_DECAY_THRESHOLD` | (configurable) | `narrative/reminders` |
| `DEFAULT_TARGET_STRICT_SCORE` | 95 | `narrative/core` |
| `_HIGH_IGNORE_SUPPRESSION_THRESHOLD` | 30.0% | `narrative/core` |
| `_WONTFIX_GAP_THRESHOLD` | 1.0 pts | `narrative/core` |
| `CURRENT_VERSION` (state schema) | 1 | `state/schema` |
| `STATE_DIR` | `.desloppify/` | `state/schema` |
| `STATE_FILE` | `.desloppify/state.json` | `state/schema` |
