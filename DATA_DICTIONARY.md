# Data Dictionary — desloppify (Rust Edition)

> Canonical reference for every type, constant, enum, struct, scoring parameter,
> detector policy, zone rule, and configuration key in the desloppify codebase
> quality tool. All definitions are expressed as Rust-ready types.
>
> **Source lineage:** Python desloppify codebase, fully reverse-engineered for
> the Rust rewrite.

---

## Table of Contents

1. [Core State Types](#1-core-state-types)
2. [Plan & Queue Types](#2-plan--queue-types)
3. [Scoring Engine](#3-scoring-engine)
4. [Zone System](#4-zone-system)
5. [Configuration Schema](#5-configuration-schema)
6. [Detector Registry](#6-detector-registry)
7. [Language Framework](#7-language-framework)
8. [Detector-Specific Constants & Thresholds](#8-detector-specific-constants--thresholds)
9. [Narrative & Action Planning](#9-narrative--action-planning)
10. [Review & Intelligence Layer](#10-review--intelligence-layer)
11. [Concern Synthesis](#11-concern-synthesis)
12. [Output & Visualization](#12-output--visualization)

---

## 1. Core State Types

### 1.1 FindingStatus

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FindingStatus {
    Open,
    Fixed,
    AutoResolved,
    Wontfix,
    FalsePositive,
}
```

### 1.2 Confidence

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Confidence {
    High,
    Medium,
    Low,
}
```

### 1.3 FindingDetail

Optional metadata attached to a finding. All fields are optional; the struct
is serialized as a flat JSON object.

```rust
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct FindingDetail {
    pub subtype:        Option<String>,
    pub review_weight:  Option<f64>,
    pub line:           Option<u32>,
    pub symbol:         Option<String>,
    pub description:    Option<String>,
    pub noise_tag:      Option<String>,
    pub cluster_id:     Option<String>,
    pub wontfix_reason: Option<String>,
    /// Catch-all for detector-specific extra keys.
    #[serde(flatten)]
    pub extra: HashMap<String, serde_json::Value>,
}
```

### 1.4 ResolutionAttestation

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResolutionAttestation {
    pub by:     String,
    pub reason: String,
    pub at:     String, // ISO-8601 timestamp
}
```

### 1.5 Finding

The central unit of analysis. Every finding is uniquely keyed by `id`.

```rust
/// ID format: "{detector}::{relative_path}::{symbol}"
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Finding {
    /// Unique key: "{detector}::{relpath}::{symbol}"
    pub id:                     String,
    pub detector:               String,
    /// Relative path from scan root.
    pub file:                   String,
    /// Severity tier 1..=4 (see `Tier` enum).
    pub tier:                   u8,
    pub confidence:             Confidence,
    pub summary:                String,
    pub detail:                 FindingDetail,
    pub status:                 FindingStatus,
    pub note:                   Option<String>,
    /// ISO-8601 timestamp of first observation.
    pub first_seen:             String,
    /// ISO-8601 timestamp of most recent observation.
    pub last_seen:              String,
    pub resolved_at:            Option<String>,
    #[serde(default)]
    pub reopen_count:           u32,
    pub suppressed:             Option<bool>,
    pub suppressed_at:          Option<String>,
    pub suppression_pattern:    Option<String>,
    pub resolution_attestation: Option<ResolutionAttestation>,
    pub lang:                   Option<String>,
    pub zone:                   Option<String>,
}
```

### 1.6 StateStats

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StateStats {
    pub total_files:         u32,
    pub total_loc:           u64,
    pub total_dirs:          u32,
    pub language:            String,
    pub open_findings:       u32,
    pub fixed_findings:      u32,
    pub wontfix_findings:    u32,
    pub suppressed_findings: u32,
}
```

### 1.7 ScanHistoryEntry

Retained in a ring buffer of **max 20 entries**.

```rust
pub const MAX_SCAN_HISTORY: usize = 20;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScanHistoryEntry {
    pub timestamp:            String, // ISO-8601
    pub scan_count:           u32,
    pub overall_score:        f64,
    pub objective_score:      f64,
    pub strict_score:         f64,
    pub verified_strict_score: f64,
    pub open_count:           u32,
    pub fixed_count:          u32,
    pub detector_counts:      HashMap<String, u32>,
    pub file_count:           u32,
    pub loc_count:            u64,
}
```

### 1.8 ScoreSnapshot

```rust
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct ScoreSnapshot {
    pub overall:         f64,
    pub objective:       f64,
    pub strict:          f64,
    pub verified_strict: f64,
}
```

### 1.9 ScanDiff

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScanDiff {
    pub new_findings:      Vec<Finding>,
    pub resolved_findings: Vec<Finding>,
    pub reopened_findings: Vec<Finding>,
    pub score_delta:       f64,
}
```

### 1.10 StateModel

Top-level persisted state. Version-stamped for forward compatibility.

```rust
pub const STATE_VERSION: u32 = 1;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StateModel {
    pub version:               u32, // STATE_VERSION
    pub created:               String,
    pub last_scan:             String,
    pub scan_count:            u32,
    /// 0.0..=100.0
    pub overall_score:         f64,
    pub objective_score:       f64,
    pub strict_score:          f64,
    pub verified_strict_score: f64,
    pub stats:                 StateStats,
    /// Keyed by Finding::id.
    pub findings:              HashMap<String, Finding>,
    pub scan_coverage:         HashMap<String, serde_json::Value>,
    pub score_confidence:      String,
    pub scan_history:          Vec<ScanHistoryEntry>, // max MAX_SCAN_HISTORY
    pub subjective_integrity:  HashMap<String, serde_json::Value>,
    pub subjective_assessments: HashMap<String, serde_json::Value>,
    pub concern_dismissals:    HashMap<String, serde_json::Value>,
}
```

---

## 2. Plan & Queue Types

### 2.1 Plan Model

```rust
pub const PLAN_VERSION: u32 = 2;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanModel {
    pub version:        u32, // PLAN_VERSION
    pub created:        String,
    pub updated:        String,
    /// Ordered list of finding IDs representing the work queue.
    pub queue_order:    Vec<String>,
    /// Legacy field, always empty.
    pub deferred:       Vec<serde_json::Value>,
    /// Keyed by finding ID.
    pub skipped:        HashMap<String, SkipEntry>,
    pub active_cluster: Option<String>,
    /// Keyed by finding ID.
    pub overrides:      HashMap<String, ItemOverride>,
    /// Keyed by cluster name.
    pub clusters:       HashMap<String, Cluster>,
    /// Keyed by original finding ID.
    pub superseded:     HashMap<String, SupersededEntry>,
}
```

### 2.2 SkipEntry

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SkipKind {
    Temporary,
    Permanent,
    FalsePositive,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkipEntry {
    pub finding_id:      String,
    pub kind:            SkipKind,
    pub reason:          String,
    pub note:            Option<String>,
    pub attestation:     Option<HashMap<String, String>>,
    pub created_at:      String,
    /// If set, the skip expires after this many total scans.
    pub review_after:    Option<u32>,
    pub skipped_at_scan: u32,
}
```

### 2.3 ItemOverride

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ItemOverride {
    pub priority: Option<i32>,
    pub notes:    Option<String>,
    #[serde(default)]
    pub tags:     Vec<String>,
}
```

### 2.4 Cluster

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Cluster {
    pub name:          String,
    pub description:   String,
    pub finding_ids:   Vec<String>,
    pub created_at:    String,
    pub updated_at:    String,
    pub auto:          bool,
    pub cluster_key:   Option<String>,
    pub action:        Option<String>,
    pub user_modified: bool,
}
```

#### Auto-Clustering Constants

```rust
/// Prefix for automatically generated cluster names.
pub const AUTO_PREFIX: &str = "auto/";

/// Minimum number of findings to form a scored auto-cluster.
pub const MIN_CLUSTER_SIZE: usize = 2;

/// Minimum number of findings to form an un-scored auto-cluster.
pub const MIN_UNSCORED_CLUSTER_SIZE: usize = 1;
```

### 2.5 SupersededEntry

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SupersededEntry {
    pub original_id:       String,
    pub original_detector: String,
    pub original_file:     String,
    pub original_summary:  String,
    pub status:            FindingStatus,
    pub superseded_at:     String,
    pub remapped_to:       Option<String>,
    pub candidates:        Vec<serde_json::Value>,
    pub note:              Option<String>,
}
```

### 2.6 Work Queue

#### QueueBuildOptions

```rust
#[derive(Debug, Clone)]
pub struct QueueBuildOptions {
    pub tier:                 Option<u8>,
    pub count:                usize,
    pub scan_path:            PathBuf,
    pub scope:                Option<String>,
    pub status:               Option<String>,
    pub include_subjective:   bool,
    /// Default: 100.0
    pub subjective_threshold: f64,
    pub chronic:              bool,
    pub no_tier_fallback:     bool,
    pub explain:              bool,
    pub plan:                 Option<PlanModel>,
    pub include_skipped:      bool,
    pub cluster:              Option<String>,
    pub collapse_clusters:    bool,
}

impl Default for QueueBuildOptions {
    fn default() -> Self {
        Self {
            tier: None,
            count: 10,
            scan_path: PathBuf::new(),
            scope: None,
            status: None,
            include_subjective: false,
            subjective_threshold: 100.0,
            chronic: false,
            no_tier_fallback: false,
            explain: false,
            plan: None,
            include_skipped: false,
            cluster: None,
            collapse_clusters: false,
        }
    }
}
```

#### WorkQueueResult

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkQueueResult {
    pub items:           Vec<HashMap<String, serde_json::Value>>,
    pub total:           usize,
    pub tier_counts:     HashMap<u8, u32>,
    pub requested_tier:  Option<u8>,
    pub selected_tier:   Option<u8>,
    pub fallback_reason: Option<String>,
    pub available_tiers: Vec<u8>,
    pub grouped:         bool,
}
```

#### Sort Key Semantics

Items in the work queue are sorted by composite keys:

| Category | Sort Tuple (ascending) |
|---|---|
| Regular findings | `(effective_tier, 0, confidence_rank, -review_weight, -count, id)` |
| Clusters | `(0, action_priority, -member_count, id)` |
| Subjective items | `(effective_tier, 1, subjective_score, id)` |

#### Action Type Priority (queue ordering)

```rust
pub const ACTION_TYPE_PRIORITY: &[(&str, u8)] = &[
    ("auto_fix",   0),
    ("reorganize", 1),
    ("refactor",   2),
    ("manual_fix", 3),
];
```

---

## 3. Scoring Engine

### 3.1 Score Mode

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ScoreMode {
    Lenient,
    Strict,
    VerifiedStrict,
}
```

#### Failure Statuses by Mode

Findings with these statuses count as **failures** (deductions) in each mode:

| Mode | Failure Statuses |
|---|---|
| `Lenient` | `{Open}` |
| `Strict` | `{Open, Wontfix}` |
| `VerifiedStrict` | `{Open, Wontfix, Fixed, FalsePositive}` |

```rust
pub fn failure_statuses(mode: ScoreMode) -> HashSet<FindingStatus> {
    use FindingStatus::*;
    match mode {
        ScoreMode::Lenient        => [Open].into(),
        ScoreMode::Strict         => [Open, Wontfix].into(),
        ScoreMode::VerifiedStrict => [Open, Wontfix, Fixed, FalsePositive].into(),
    }
}
```

### 3.2 Tier

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
#[repr(u8)]
pub enum Tier {
    AutoFix       = 1,
    QuickFix      = 2,
    Judgment       = 3,
    MajorRefactor = 4,
}
```

### 3.3 Scoring Constants

```rust
/// Weight applied per tier level when computing deductions.
pub const TIER_WEIGHTS: [(u8, f64); 4] = [
    (1, 1.0),
    (2, 2.0),
    (3, 3.0),
    (4, 4.0),
];

/// Weight multiplier per confidence level.
pub const CONFIDENCE_WEIGHTS: [(Confidence, f64); 3] = [
    (Confidence::High,   1.0),
    (Confidence::Medium, 0.7),
    (Confidence::Low,    0.3),
];

/// Minimum LOC sample size. Projects below this get scaled deductions.
pub const MIN_SAMPLE: u64 = 200;

/// Multiplier for holistic (subjective) potential points.
pub const HOLISTIC_MULTIPLIER: f64 = 10.0;

/// Maximum potential points from holistic assessment.
pub const HOLISTIC_POTENTIAL: u32 = 10;

/// Number of subjective review checks.
pub const SUBJECTIVE_CHECKS: u32 = 10;

/// Fraction of total score weight allocated to subjective dimensions.
pub const SUBJECTIVE_WEIGHT_FRACTION: f64 = 0.60;

/// Fraction of total score weight allocated to mechanical dimensions.
pub const MECHANICAL_WEIGHT_FRACTION: f64 = 0.40;

/// Tolerance band for subjective target score matching.
pub const SUBJECTIVE_TARGET_MATCH_TOLERANCE: f64 = 0.05;

/// Number of consecutive score misses before target is reset.
pub const SUBJECTIVE_TARGET_RESET_THRESHOLD: u32 = 2;
```

### 3.4 File Cap Thresholds

Per-file finding counts are capped to prevent any single file from
dominating the score:

| Finding Count in File | Cap Multiplier |
|---|---|
| >= `HIGH_THRESHOLD` (6) | 2.0 |
| >= `MID_THRESHOLD` (3) | 1.5 |
| < 3 | 1.0 |

```rust
pub const HIGH_THRESHOLD: u32 = 6;
pub const HIGH_CAP: f64       = 2.0;
pub const MID_THRESHOLD: u32  = 3;
pub const MID_CAP: f64        = 1.5;
pub const LOW_CAP: f64        = 1.0;
```

### 3.5 Dimensions

All scoring flows through named **dimensions**, each belonging to either the
`mechanical` or `subjective` pool.

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DimensionPool {
    Mechanical,
    Subjective,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Dimension {
    pub name:   String,
    pub pool:   DimensionPool,
    pub weight: f64,
}
```

#### Mechanical Dimensions

| Dimension | Weight |
|---|---|
| `file_health` | 2.0 |
| `code_quality` | 1.0 |
| `duplication` | 1.0 |
| `test_health` | 1.0 |
| `security` | 1.0 |

**Total mechanical weight:** 6.0

#### Subjective Dimensions

| Dimension | Weight |
|---|---|
| `high_level_elegance` | 22.0 |
| `mid_level_elegance` | 22.0 |
| `low_level_elegance` | 12.0 |
| `contract_coherence` | 12.0 |
| `type_safety` | 12.0 |
| `design_coherence` | 10.0 |
| `abstraction_fitness` | 8.0 |
| `logic_clarity` | 6.0 |
| `structure_navigation` | 5.0 |
| `error_consistency` | 3.0 |
| `naming_quality` | 2.0 |
| `ai_generated_debt` | 1.0 |

**Total subjective weight:** 115.0

### 3.6 DetectorScoringPolicy

Maps each detector to its scoring dimension and behaviour.

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DetectorScoringPolicy {
    pub detector:       String,
    pub dimension:      String,
    pub default_tier:   u8,
    pub file_based:     bool,
    pub use_loc_weight: bool,
    pub excluded_zones: HashSet<String>,
}
```

#### Detector-to-Dimension Mapping (29 policies)

| Detector(s) | Dimension | Notes |
|---|---|---|
| `unused`, `exports`, `logs`, `deprecated` | `code_quality` | Common code hygiene |
| `smells`, `complexity`, `large`, `gods` | `code_quality` | Structural quality |
| `concerns`, `flat_dirs`, `naming` | `code_quality` | Organization |
| `single_use`, `passthrough`, `signature_variance` | `code_quality` | API design |
| `review_coverage` | `code_quality` | Review staleness |
| `orphaned`, `coupling`, `cycles` | `file_health` | Dependency graph |
| `dupes`, `boilerplate_duplication` | `duplication` | Copy-paste detection |
| `test_coverage` | `test_health` | Test adequacy |
| `security` | `security` | Vulnerability detection |
| `subjective_review` | *(varies)* | Routed to the specific subjective dimension named in the finding |

### 3.7 ScoreBundle

Final output of the scoring engine for a given scan.

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoreBundle {
    /// Dimension name -> 0..=100 score.
    pub dimension_scores:                HashMap<String, f64>,
    pub strict_dimension_scores:         HashMap<String, f64>,
    pub verified_strict_dimension_scores: HashMap<String, f64>,
    pub overall_score:                   f64,
    pub objective_score:                 f64,
    pub strict_score:                    f64,
    pub verified_strict_score:           f64,
}
```

---

## 4. Zone System

### 4.1 Zone Enum

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Zone {
    Production,
    Test,
    Config,
    Generated,
    Script,
    Vendor,
}

/// Zones excluded from scoring by default.
pub const EXCLUDED_ZONES: &[Zone] = &[
    Zone::Test,
    Zone::Config,
    Zone::Generated,
    Zone::Vendor,
];
```

### 4.2 Zone Rules

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ZoneRule {
    pub zone:     Zone,
    pub patterns: Vec<String>,
}
```

#### Pattern Matching Semantics

| Pattern Form | Match Logic | Example |
|---|---|---|
| `/dir/` | Substring match on full path | `/generated/` matches `src/generated/foo.ts` |
| `.ext` | Suffix match on filename | `.g.dart` matches `model.g.dart` |
| `prefix_` | Starts-with match on basename | `_generated.` matches `_generated.foo` |
| `_suffix` | Ends-with match on basename (before extension) | `_pb2.py` matches `service_pb2.py` |
| `name.py` | Exact basename match | `Dockerfile` matches `Dockerfile` |

### 4.3 Common Zone Rules (built-in)

#### GENERATED

```
/generated/  .generated.  _generated.  .g.dart  _pb2.py  _pb2_grpc.py
```

#### VENDOR

```
/vendor/  /third_party/
```

#### CONFIG

```
Dockerfile          docker-compose      .github/        .circleci/
Makefile            Justfile            Taskfile        .editorconfig
.prettierrc         .eslintrc           tsconfig        jest.config
vite.config         webpack.config      babel.config    pyproject.toml
setup.cfg           Cargo.toml          go.mod          pubspec.yaml
build.gradle        pom.xml             Package.swift   *.nimble
*.fsproj            .csproj             dune-project    rebar.config
mix.exs             stack.yaml          cabal.project   build.sbt
build.zig
```

#### SCRIPT

```
/scripts/  /tools/  /bin/ (if not source)
```

### 4.4 Zone Policy

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ZonePolicy {
    pub skip_detectors:      HashSet<String>,
    pub downgrade_detectors: HashSet<String>,
    pub exclude_from_score:  bool,
}
```

---

## 5. Configuration Schema

User-facing configuration, typically stored in `.desloppify.toml` or the
`[tool.desloppify]` section of `pyproject.toml`.

### 5.1 Config Keys (17 total)

| Key | Rust Type | Default | Description |
|---|---|---|---|
| `target_strict_score` | `u32` | `95` | Target score on the strict scale. |
| `review_max_age_days` | `u32` | `30` | Maximum age in days before a review is considered stale. |
| `review_batch_max_files` | `u32` | `80` | Maximum files per review batch. |
| `holistic_max_age_days` | `u32` | `30` | Maximum age for holistic (subjective) assessments. |
| `generate_scorecard` | `bool` | `true` | Whether to emit a scorecard image on scan. |
| `badge_path` | `String` | `"scorecard.png"` | Output path for the scorecard badge. |
| `exclude` | `Vec<String>` | `[]` | Glob patterns for files/dirs to exclude from scanning entirely. |
| `ignore` | `Vec<String>` | `[]` | Glob patterns for files/dirs whose findings are suppressed. |
| `ignore_metadata` | `HashMap<String, Value>` | `{}` | Metadata annotations for ignore rules (audit trail). |
| `zone_overrides` | `HashMap<String, Value>` | `{}` | Per-path or per-pattern zone assignment overrides. |
| `review_dimensions` | `Vec<String>` | `[]` | Subset of subjective dimensions to review (empty = all). |
| `large_files_threshold` | `u32` | `0` | Override for the large-file LOC threshold (`0` = language default). |
| `props_threshold` | `u32` | `0` | Override for the max-props threshold (`0` = language default). |
| `finding_noise_budget` | `u32` | `10` | Per-detector noise budget before low-confidence findings are suppressed. |
| `finding_noise_global_budget` | `u32` | `0` | Global noise budget across all detectors (`0` = unlimited). |
| `needs_rescan` | `bool` | `false` | Flag indicating state requires a fresh scan (set after config changes). |
| `languages` | `HashMap<String, Value>` | `{}` | Per-language configuration overrides. |

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    #[serde(default = "default_target_strict_score")]
    pub target_strict_score:        u32,
    #[serde(default = "default_review_max_age_days")]
    pub review_max_age_days:        u32,
    #[serde(default = "default_review_batch_max_files")]
    pub review_batch_max_files:     u32,
    #[serde(default = "default_holistic_max_age_days")]
    pub holistic_max_age_days:      u32,
    #[serde(default = "default_true")]
    pub generate_scorecard:         bool,
    #[serde(default = "default_badge_path")]
    pub badge_path:                 String,
    #[serde(default)]
    pub exclude:                    Vec<String>,
    #[serde(default)]
    pub ignore:                     Vec<String>,
    #[serde(default)]
    pub ignore_metadata:            HashMap<String, serde_json::Value>,
    #[serde(default)]
    pub zone_overrides:             HashMap<String, serde_json::Value>,
    #[serde(default)]
    pub review_dimensions:          Vec<String>,
    #[serde(default)]
    pub large_files_threshold:      u32,
    #[serde(default)]
    pub props_threshold:            u32,
    #[serde(default = "default_noise_budget")]
    pub finding_noise_budget:       u32,
    #[serde(default)]
    pub finding_noise_global_budget: u32,
    #[serde(default)]
    pub needs_rescan:               bool,
    #[serde(default)]
    pub languages:                  HashMap<String, serde_json::Value>,
}

fn default_target_strict_score() -> u32 { 95 }
fn default_review_max_age_days() -> u32 { 30 }
fn default_review_batch_max_files() -> u32 { 80 }
fn default_holistic_max_age_days() -> u32 { 30 }
fn default_true() -> bool { true }
fn default_badge_path() -> String { "scorecard.png".into() }
fn default_noise_budget() -> u32 { 10 }
```

---

## 6. Detector Registry

### 6.1 DetectorMeta

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DetectorMeta {
    pub name:           String,
    pub display:        String,
    pub dimension:      String,
    pub action_type:    ActionTypeLabel,
    pub guidance:       String,
    pub fixers:         Vec<String>,
    pub tool:           Option<String>,
    pub structural:     bool,
    pub needs_judgment: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActionTypeLabel {
    AutoFix,
    Reorganize,
    Refactor,
    ManualFix,
    DebtReview,
}
```

### 6.2 Full Detector List (30+ entries)

| # | Detector Name | Dimension | Action Type | Structural | Needs Judgment |
|---|---|---|---|---|---|
| 1 | `unused` | `code_quality` | `auto_fix` | no | no |
| 2 | `logs` | `code_quality` | `auto_fix` | no | no |
| 3 | `exports` | `code_quality` | `auto_fix` | no | no |
| 4 | `smells` | `code_quality` | `refactor` | no | yes |
| 5 | `orphaned` | `file_health` | `reorganize` | yes | no |
| 6 | `uncalled_functions` | `code_quality` | `auto_fix` | no | no |
| 7 | `flat_dirs` | `code_quality` | `reorganize` | yes | no |
| 8 | `naming` | `code_quality` | `refactor` | no | yes |
| 9 | `single_use` | `code_quality` | `refactor` | no | yes |
| 10 | `coupling` | `file_health` | `refactor` | yes | yes |
| 11 | `cycles` | `file_health` | `refactor` | yes | yes |
| 12 | `facade` | `code_quality` | `refactor` | yes | yes |
| 13 | `structural` | `code_quality` | `reorganize` | yes | no |
| 14 | `props` | `code_quality` | `refactor` | no | yes |
| 15 | `react` | `code_quality` | `refactor` | no | yes |
| 16 | `dupes` | `duplication` | `refactor` | no | yes |
| 17 | `patterns` | `code_quality` | `refactor` | no | yes |
| 18 | `dict_keys` | `code_quality` | `refactor` | no | no |
| 19 | `test_coverage` | `test_health` | `manual_fix` | no | no |
| 20 | `signature` | `code_quality` | `refactor` | no | yes |
| 21 | `global_mutable_config` | `code_quality` | `refactor` | no | yes |
| 22 | `private_imports` | `code_quality` | `refactor` | no | no |
| 23 | `layer_violation` | `file_health` | `refactor` | yes | yes |
| 24 | `responsibility_cohesion` | `code_quality` | `refactor` | no | yes |
| 25 | `boilerplate_duplication` | `duplication` | `refactor` | no | yes |
| 26 | `stale_wontfix` | `code_quality` | `debt_review` | no | no |
| 27 | `concerns` | `code_quality` | `refactor` | no | yes |
| 28 | `deprecated` | `code_quality` | `auto_fix` | no | no |
| 29 | `stale_exclude` | `code_quality` | `debt_review` | no | no |
| 30 | `security` | `security` | `manual_fix` | no | yes |
| 31 | `review` | `code_quality` | `debt_review` | no | no |
| 32 | `subjective_review` | *(varies)* | `debt_review` | no | yes |

---

## 7. Language Framework

### 7.1 LangConfig

The central configuration object for each supported language.

```rust
#[derive(Debug, Clone)]
pub struct LangConfig {
    pub name:                 String,
    pub extensions:           Vec<String>,
    pub globs:                Vec<String>,
    pub depth:                LangDepth,
    pub tools:                Vec<ToolConfig>,
    pub zone_rules:           Vec<ZoneRule>,
    pub detect_markers:       Vec<String>,
    pub default_src:          String,
    pub exclude:              Vec<String>,
    pub test_coverage_module: Option<String>,
    pub large_threshold:      u32,
    pub complexity_threshold: u32,
    pub default_scan_profile: String, // "objective"
    pub external_test_dirs:   Vec<String>,
    pub phases:               Vec<PhaseRunner>,
    pub commands:             HashMap<String, String>,
    pub extractors:           HashMap<String, ExtractorFn>,
    pub fixers:               Vec<FixerConfig>,
    pub review_hooks:         HashMap<String, HookFn>,
    pub move_module:          Option<MoveModuleFn>,
    pub treesitter_spec:      Option<TreeSitterSpec>,
}
```

### 7.2 LangDepth

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LangDepth {
    Minimal,
    Shallow,
    Standard,
}
```

### 7.3 ToolConfig

External tool integration for linting/formatting.

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolConfig {
    pub name:     String,
    /// 2 or 3 — tier of findings produced by this tool.
    pub tier:     u8,
    pub fmt:      ToolFormat,
    pub id:       String,
    pub command:  String,
    pub fix_cmd:  Option<String>,
    pub auto_fix: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ToolFormat {
    Gnu,
    Json,
    Eslint,
    Rubocop,
    Cargo,
}
```

### 7.4 LangRun

Runtime context for a scan within a specific language.

```rust
#[derive(Debug, Clone)]
pub struct LangRun {
    pub config:    Arc<LangConfig>,
    pub zone_map:  FileZoneMap,       // HashMap<String, Zone>
    pub dep_graph: HashMap<String, Vec<String>>,
    pub file_list: Vec<String>,
    pub scan_path: PathBuf,
}

pub type FileZoneMap = HashMap<String, Zone>;
```

### 7.5 TreeSitterSpec

```rust
#[derive(Debug, Clone)]
pub struct TreeSitterSpec {
    pub grammar_name:   String,
    pub extensions:     Vec<String>,
    pub import_query:   Option<String>,
    pub resolve_import: Option<ResolveImportFn>,
    pub class_query:    Option<String>,
}
```

### 7.6 Extraction Types

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionInfo {
    pub name:              String,
    pub file:              String,
    pub line:              u32,
    pub loc:               u32,
    pub params:            Vec<String>,
    /// MD5 hex digest of the function body.
    pub body_hash:         String,
    pub return_annotation: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClassInfo {
    pub name:         String,
    pub file:         String,
    pub line:         u32,
    pub loc:          u32,
    pub methods:      Vec<FunctionInfo>,
    pub attributes:   Vec<String>,
    pub base_classes: Vec<String>,
}
```

### 7.7 Complexity & God-Class Rules

```rust
#[derive(Debug, Clone)]
pub struct ComplexitySignal {
    pub label:              String,
    /// Either a regex pattern string or a reference to a compute function.
    pub pattern_or_compute: ComplexitySource,
    pub weight:             i32,
    pub threshold:          i32,
}

#[derive(Debug, Clone)]
pub enum ComplexitySource {
    Pattern(String),
    Compute(Arc<dyn Fn(&str) -> i32 + Send + Sync>),
}

#[derive(Debug, Clone)]
pub struct GodRule {
    pub id:        String,
    pub label:     String,
    pub compute:   Arc<dyn Fn(&ClassInfo) -> i32 + Send + Sync>,
    pub threshold: i32,
}
```

### 7.8 Fixer Types

```rust
#[derive(Debug, Clone)]
pub struct FixerConfig {
    pub name:        String,
    pub detector:    String,
    pub description: String,
    pub run:         Arc<dyn Fn(&FixerContext) -> FixResult + Send + Sync>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FixResult {
    pub fixed_count: u32,
    pub skipped:     Vec<SkippedFix>,
    pub details:     Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkippedFix {
    pub reason: String,
    pub file:   String,
    pub symbol: String,
}
```

### 7.9 Supported Languages (28 total)

#### Full-Depth Languages (6)

| Language | Extensions | Depth | Complexity Threshold | Large Threshold |
|---|---|---|---|---|
| TypeScript | `.ts`, `.tsx` | `standard` | 15 | 500 |
| Python | `.py` | `standard` | 25 | 300 |
| C# | `.cs` | `standard` | 20 | 500 |
| Dart | `.dart` | `standard` | 16 | 500 |
| GDScript | `.gd` | `standard` | 16 | 500 |
| Go | `.go` | `standard` | 15 | 500 |

#### Generic Languages (22)

| Language | Extensions | Depth | Has Auto-Fix Tool |
|---|---|---|---|
| Bash | `.sh`, `.bash` | `minimal` | no |
| Clojure | `.clj`, `.cljs`, `.cljc` | `minimal` | no |
| C++ | `.cpp`, `.cc`, `.cxx`, `.h`, `.hpp` | `minimal` | no |
| Elixir | `.ex`, `.exs` | `shallow` | no |
| Erlang | `.erl`, `.hrl` | `minimal` | no |
| F# | `.fs`, `.fsx` | `minimal` | no |
| Haskell | `.hs` | `shallow` | no |
| Java | `.java` | `shallow` | no |
| JavaScript | `.js`, `.jsx`, `.mjs`, `.cjs` | `shallow` | yes (ESLint) |
| Kotlin | `.kt`, `.kts` | `shallow` | yes (ktlint) |
| Lua | `.lua` | `minimal` | no |
| Nim | `.nim` | `minimal` | no |
| OCaml | `.ml`, `.mli` | `shallow` | no |
| Perl | `.pl`, `.pm` | `minimal` | no |
| PHP | `.php` | `shallow` | no |
| PowerShell | `.ps1`, `.psm1` | `minimal` | no |
| R | `.R`, `.r` | `minimal` | no |
| Ruby | `.rb` | `shallow` | yes (rubocop) |
| Rust | `.rs` | `standard` | yes (clippy) |
| Scala | `.scala` | `shallow` | no |
| Swift | `.swift` | `shallow` | yes (swiftlint) |
| Zig | `.zig` | `minimal` | no |

---

## 8. Detector-Specific Constants & Thresholds

### 8.1 Duplicate Detection

```rust
/// Similarity ratio threshold for near-duplicate detection.
pub const NEAR_DUPLICATE_THRESHOLD: f64 = 0.9;

/// Minimum lines of code for a function to be considered for duplication.
pub const DUPE_MIN_LOC: u32 = 15;

/// Maximum LOC ratio between two functions to consider them as duplicates.
pub const DUPE_LOC_RATIO: f64 = 1.5;
```

**Algorithm:** `difflib::SequenceMatcher` equivalent with `quick_ratio()` gate,
followed by union-find clustering of duplicate pairs.

### 8.2 Complexity Thresholds (per language)

| Language | Default Threshold |
|---|---|
| Python | 25 |
| C# | 20 |
| Dart | 16 |
| GDScript | 16 |
| Go | 15 |
| TypeScript | 15 |
| *All others* | 15 |

### 8.3 Large File Thresholds (per language)

| Language | LOC Threshold |
|---|---|
| Python | 300 |
| *All others* | 500 |

### 8.4 God Class Rules

#### TypeScript

| Rule ID | Metric | Threshold |
|---|---|---|
| `context_hooks` | Context hooks in component | > 3 |
| `use_effects` | `useEffect` calls | > 4 |
| `use_states` | `useState` calls | > 5 |
| `custom_hooks` | Custom hook calls | > 8 |
| `hook_total` | Total hook calls | > 10 |

#### Python

| Rule ID | Metric | Threshold |
|---|---|---|
| `methods` | Method count | > 15 |
| `attributes` | Attribute count | > 10 |
| `base_classes` | Base class count | > 3 |
| `long_methods` | Methods with LOC > 50 | > 1 |

#### C#

| Rule ID | Metric | Threshold |
|---|---|---|
| `methods` | Method count | > 15 |
| `attributes` | Attribute/field count | > 10 |
| `base_classes` | Base class / interface count | > 4 |
| `long_methods` | Methods with LOC > 50 | > 2 |

### 8.5 Security Checks

#### TypeScript (10 checks)

| Check ID | Description |
|---|---|
| `service_role_on_client` | Service role key used in client-side code |
| `eval_injection` | Use of `eval()` or `new Function()` |
| `dangerouslySetInnerHTML` | React `dangerouslySetInnerHTML` usage |
| `innerHTML` | Direct `innerHTML` assignment |
| `dev_credential` | Hardcoded development credentials |
| `open_redirect` | Unvalidated redirect targets |
| `unverified_jwt` | JWT decoded without signature verification |
| `edge_function_missing_auth` | Edge function without authentication check |
| `json_parse_unguarded` | `JSON.parse()` without try/catch |
| `rls_bypass` | Supabase RLS bypass patterns |

#### Python (via Bandit adapter)

Severity mapping from Bandit to desloppify:

| Bandit Severity | Tier | Confidence |
|---|---|---|
| HIGH | 4 | `high` |
| MEDIUM | 3 | `medium` |
| LOW | 3 | `low` |

#### C# (4 checks)

| Check ID | Description |
|---|---|
| `sql_injection` | String concatenation in SQL queries |
| `insecure_random` | Use of `System.Random` for security |
| `weak_crypto_tls` | Weak TLS or crypto algorithm usage |
| `unsafe_deserialization` | Insecure `BinaryFormatter` deserialization |

### 8.6 Smell Counts by Language

| Language | Number of Smell Checks | Detection Method |
|---|---|---|
| TypeScript | 28 | Regex + AST dispatch |
| Python | 32 | Regex + AST dispatch |

---

## 9. Narrative & Action Planning

### 9.1 NarrativePhase

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NarrativePhase {
    FirstScan,
    Regression,
    Stagnation,
    EarlyMomentum,
    Maintenance,
    Refinement,
    MiddleGrind,
}
```

#### Phase Detection Rules

| Phase | Condition |
|---|---|
| `FirstScan` | `scan_count == 1` |
| `Regression` | Score dropped > 0.5 from previous scan |
| `Stagnation` | Score change within +/- 0.5 for 3+ consecutive scans |
| `EarlyMomentum` | `scan_count` in 2..=5 and score is rising |
| `Maintenance` | Score > 93 |
| `Refinement` | Score > 80 |
| `MiddleGrind` | Default / fallthrough |

### 9.2 ActionType

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[repr(u8)]
pub enum ActionType {
    IssueQueue  = 0,
    AutoFix     = 1,
    Reorganize  = 2,
    Refactor    = 3,
    ManualFix   = 4,
    DebtReview  = 5,
}
```

### 9.3 ActionItem

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActionItem {
    pub action_type: ActionType,
    pub detector:    String,
    pub impact:      f64,
    pub description: String,
    pub files:       Vec<String>,
    pub fixer:       Option<String>,
    pub cluster:     Option<String>,
}
```

### 9.4 Tool Inventory

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolFixer {
    pub name:     String,
    pub detector: String,
    pub auto:     bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolInventory {
    pub available: Vec<ToolFixer>,
    pub missing:   Vec<String>,
}
```

### 9.5 Lane System

The narrative engine groups action items into **lanes** using union-find
clustering based on file overlap.

| Lane Name | Detectors / Source |
|---|---|
| `cleanup` | Auto-fixable findings |
| `restructure` | Structural detectors |
| `refactor_N` | Numbered refactor batches |
| `test_coverage` | Test coverage findings |
| `debt_review` | Stale wontfix, review items |

#### Structural Merge Set

Findings from these detectors are merged into the same lane when they touch
overlapping files:

```rust
pub const STRUCTURAL_MERGE: &[&str] = &[
    "large", "complexity", "gods", "concerns",
];
```

#### Detector Cascade

When a detector produces findings, these downstream detectors are also
expected to fire on the same files:

```rust
pub const DETECTOR_CASCADE: &[(&str, &[&str])] = &[
    ("logs",   &["unused"]),
    ("smells", &["unused"]),
];
```

### 9.6 Reminder Decay

Narrative reminders (e.g., "consider running auto-fix") are **suppressed
after 3 occurrences** to prevent alert fatigue. Certain critical reminders
carry a `no_decay` flag and are exempt from suppression.

---

## 10. Review & Intelligence Layer

### 10.1 Dimension Definitions

22 dimension definitions are loaded from `dimensions.json`:

- 20 default dimensions (the 5 mechanical + 12 subjective listed in
  [Section 3.5](#35-dimensions), plus `review_coverage`, `complexity`,
  `large`)
- `comment_quality` (supplementary)
- `authorization_coherence` (supplementary)

### 10.2 NormalizedBatchFinding

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Severity {
    Low,
    Medium,
    High,
    Critical,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NormalizedBatchFinding {
    pub dimension:     String,
    pub identifier:    String,
    pub summary:       String,
    pub severity:      Severity,
    /// 0.0..=1.0
    pub confidence:    f64,
    pub related_files: Vec<String>,
    pub remediation:   String,
}
```

### 10.3 DimensionMergeScorer

The merge scorer blends multiple assessment sources into a single per-dimension
score.

```rust
/// Blending ratio: 70% weighted mean, 30% floor.
pub const MERGE_WEIGHTED_MEAN_RATIO: f64 = 0.70;
pub const MERGE_FLOOR_RATIO: f64         = 0.30;

/// Maximum penalty that can be applied from findings to a dimension score.
pub const MAX_PENALTY_CAP: f64 = 24.0;
```

Per-finding penalty is computed as:
`confidence x impact_scope x fix_scope x severity_weight`

### 10.4 Assessment Trust Model (4 tiers)

| Tier | Source | Label | Trust Level |
|---|---|---|---|
| 1 | `trusted_internal` | Run-batches (built-in engine) | Full trust |
| 2 | `attested_external` | Claude with attestation | Full trust if attested |
| 3 | `manual_override` | User-provided provisional | Expires on next scan |
| 4 | `findings_only` | Untrusted external import | Findings imported, scores discarded |

### 10.5 Provenance

Assessment integrity is verified via SHA-256 hash of the blind packet
(the assessment payload before scores are applied). This allows downstream
consumers to verify that assessment data has not been tampered with.

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AssessmentProvenance {
    /// SHA-256 hex digest of the blind packet.
    pub integrity_hash: String,
    pub source_tier:    u8,
    pub timestamp:      String,
}
```

---

## 11. Concern Synthesis

### 11.1 Concern

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Concern {
    pub concern_type:    ConcernType,
    pub file:            String,
    pub summary:         String,
    /// Immutable evidence lines supporting the concern.
    pub evidence:        Vec<String>,
    pub question:        String,
    /// First 16 hex chars of SHA-256 of the canonical concern content.
    pub fingerprint:     String,
    pub source_findings: Vec<String>,
}
```

### 11.2 ConcernType

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ConcernType {
    MixedResponsibilities,
    DuplicationDesign,
    StructuralComplexity,
    CouplingDesign,
    InterfaceDesign,
    DesignConcern,
    SystemicPattern,
    SystemicSmell,
}
```

### 11.3 Concern Thresholds

| Trigger Condition | Concern Type Generated |
|---|---|
| Function/method params >= 8 | `InterfaceDesign` |
| Nesting depth >= 6 | `StructuralComplexity` |
| File LOC >= 300 | `StructuralComplexity` |
| 3+ files sharing the same smell profile | `SystemicPattern` |
| 5+ files exhibiting the same specific smell | `SystemicSmell` |

### 11.4 Fingerprinting

Each concern is fingerprinted for deduplication and dismissal tracking:

```
fingerprint = sha256(canonical_concern_content)[:16]
```

Where `canonical_concern_content` is a deterministic serialization of the
concern type, file, and evidence tuple.

---

## 12. Output & Visualization

### 12.1 Scorecard Theme

```rust
pub struct ScorecardTheme {
    pub bg:        &'static str,
    pub text:      &'static str,
    pub excellent: &'static str,
    pub good:      &'static str,
    pub warning:   &'static str,
    pub poor:      &'static str,
}

pub const SCORECARD_THEME: ScorecardTheme = ScorecardTheme {
    bg:        "#F7F0E4",
    text:      "#3A3026",
    excellent: "#5A7A5A",
    good:      "#6B8B4A",
    warning:   "#B8A040",
    poor:      "#A05050",
};
```

### 12.2 Scorecard Limits

- Maximum **20 dimensions** rendered on a single scorecard.
- Elegance sub-dimensions (`high_level_elegance`, `mid_level_elegance`,
  `low_level_elegance`) are **collapsed to a single row** by averaging their
  scores.

### 12.3 Treemap Template Placeholders

The interactive treemap HTML template uses the following placeholder tokens
that are replaced at render time:

| Placeholder | Type | Description |
|---|---|---|
| `__D3_CDN_URL__` | `String` | CDN URL for D3.js library |
| `__TREE_DATA__` | `JSON` | Hierarchical file tree with metrics |
| `__TOTAL_FILES__` | `u32` | Total files in scan |
| `__TOTAL_LOC__` | `u64` | Total lines of code |
| `__TOTAL_FINDINGS__` | `u32` | Total findings (all statuses) |
| `__OPEN_FINDINGS__` | `u32` | Open findings count |
| `__OVERALL_SCORE__` | `f64` | Overall (lenient) score |
| `__OBJECTIVE_SCORE__` | `f64` | Objective (mechanical-only) score |
| `__STRICT_SCORE__` | `f64` | Strict score |

---

## Appendix A: ID Format Conventions

| Entity | Format | Example |
|---|---|---|
| Finding ID | `{detector}::{relpath}::{symbol}` | `unused::src/utils.ts::formatDate` |
| Cluster name (auto) | `auto/{cluster_key}` | `auto/dead_code_utils` |
| Concern fingerprint | SHA-256 hex, first 16 chars | `a1b2c3d4e5f67890` |
| Assessment provenance | Full SHA-256 hex | `a1b2c3d4...` (64 chars) |

## Appendix B: Score Formula Summary

The overall score is computed as:

```
overall = (mechanical_weighted_score * MECHANICAL_WEIGHT_FRACTION)
        + (subjective_weighted_score * SUBJECTIVE_WEIGHT_FRACTION)
```

Where each pool's weighted score is:

```
pool_score = 100 - sum(deductions_per_dimension * dimension_weight) / sum(dimension_weights)
```

Each dimension's deduction is the sum of per-finding penalties, subject to:
- Tier weight multiplication (`TIER_WEIGHTS`)
- Confidence scaling (`CONFIDENCE_WEIGHTS`)
- Per-file cap (`HIGH_CAP`, `MID_CAP`, `LOW_CAP`)
- LOC normalization against `MIN_SAMPLE`

Strict and verified-strict scores use progressively broader failure status sets
(see [Section 3.1](#31-score-mode)).

## Appendix C: Enum Value Quick Reference

### FindingStatus

| Variant | Serialized | Score Impact (Lenient) | Score Impact (Strict) | Score Impact (Verified Strict) |
|---|---|---|---|---|
| `Open` | `"open"` | Yes | Yes | Yes |
| `Fixed` | `"fixed"` | No | No | Yes |
| `AutoResolved` | `"auto_resolved"` | No | No | No |
| `Wontfix` | `"wontfix"` | No | Yes | Yes |
| `FalsePositive` | `"false_positive"` | No | No | Yes |

### Tier

| Variant | Value | Weight | Typical Action |
|---|---|---|---|
| `AutoFix` | 1 | 1.0 | Automated fix available |
| `QuickFix` | 2 | 2.0 | Simple manual fix |
| `Judgment` | 3 | 3.0 | Requires design judgment |
| `MajorRefactor` | 4 | 4.0 | Significant refactoring needed |

### Zone

| Variant | Scored | Detectors Run |
|---|---|---|
| `Production` | Yes | All |
| `Test` | No | Subset |
| `Config` | No | Subset |
| `Generated` | No | None |
| `Script` | Yes | Most |
| `Vendor` | No | None |

---

*This document is auto-maintained alongside the Rust rewrite. When adding new
types, detectors, or constants, update the corresponding section here.*
