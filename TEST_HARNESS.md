# Genesis Deslop -- Test Harness Specification

> Comprehensive test strategy for the Rust implementation of genesis-deslop.
> Covers unit tests, integration tests, property-based tests, cross-validation
> against the Python v0.8.0 reference, snapshot tests, and benchmarks.

---

## Table of Contents

1. [Test Strategy Overview](#1-test-strategy-overview)
2. [Per-Crate Test Plans](#2-per-crate-test-plans)
3. [Golden File Test Infrastructure](#3-golden-file-test-infrastructure)
4. [Cross-Validation Test Framework](#4-cross-validation-test-framework)
5. [Property-Based Tests](#5-property-based-tests-proptest)
6. [Benchmark Tests](#6-benchmark-tests-criterion)
7. [CI Pipeline](#7-ci-pipeline)
8. [Test Utilities Module](#8-test-utilities-module)

---

## 1. Test Strategy Overview

### 1.1 Test Layers

| Layer | Tool | Location | Purpose |
|-------|------|----------|---------|
| Unit tests | `#[cfg(test)]` | Co-located in each `.rs` source file | Per-function, per-module correctness |
| Integration tests | `cargo test` | `crates/*/tests/` directories | Per-crate public API contracts |
| Property-based tests | `proptest` | `crates/*/tests/property_*.rs` | Invariant verification over random inputs |
| Cross-validation tests | Custom harness + Python subprocess | `tests/cross-validation/` | Bit-for-bit scoring parity with Python v0.8.0 |
| Snapshot tests | `insta` | Inline in unit/integration tests | Output formatting consistency |
| Benchmark tests | `criterion` | `crates/*/benches/` | Performance regression detection |

### 1.2 Coverage Target

**>80% line coverage** across all crates, enforced in CI via `cargo-llvm-cov`.

Per-crate minimum thresholds:

| Crate | Minimum Coverage | Rationale |
|-------|-----------------|-----------|
| `genesis-deslop-core` | 90% | Pure types and config -- no excuse for gaps |
| `genesis-deslop-engine` | 85% | Scoring and state are correctness-critical |
| `genesis-deslop-lang` | 75% | Language plugins have external tool dependencies |
| `genesis-deslop-intel` | 80% | Review and narrative logic must be well-tested |
| `genesis-deslop-cli` | 70% | CLI integration tests cover the rest |

### 1.3 Test Naming Convention

```
test_{module}_{scenario}_{expected_outcome}
```

Examples:
- `test_config_parse_valid_toml_all_17_keys`
- `test_scoring_empty_findings_returns_100`
- `test_merge_scan_reopen_increments_count`

### 1.4 Test Dependencies

```toml
# workspace Cargo.toml [workspace.dependencies]
proptest = "1.4"
insta = { version = "1.38", features = ["json", "yaml"] }
criterion = { version = "0.5", features = ["html_reports"] }
tempfile = "3.10"
assert_approx_eq = "1.1"
serde_json = "1.0"
```

### 1.5 Feature-Gated Tests

Tests requiring external resources are gated behind features or `#[ignore]`:

| Gate | Tests Behind It | When to Run |
|------|----------------|-------------|
| `#[ignore]` | Cross-validation (requires Python 3.12+) | CI only: `cargo test -- --ignored` |
| `#[cfg(feature = "tree-sitter")]` | AST-dependent detector tests | When tree-sitter grammars compiled |
| `#[cfg(feature = "scorecard-png")]` | PNG rendering tests | When image deps available |
| `#[ignore]` | External linter tests (ESLint, ruff, clippy) | CI only with tools installed |

---

## 2. Per-Crate Test Plans

### 2.1 genesis-deslop-core

#### config tests

| Test | Description | Type |
|------|-------------|------|
| `parse_valid_toml_all_keys` | Parse TOML config with all 17 keys populated. Assert each field matches expected value. | Unit |
| `parse_minimal_toml_all_defaults` | Parse empty `[scan]` section. Assert all fields have documented default values. | Unit |
| `reject_negative_threshold` | `scoring.mechanical_weight = -0.5` returns `Err` with `GD-2xxx` code. | Unit |
| `reject_unknown_keys` | TOML with `[scoring]\nfoo = 123` returns `Err` (deny unknown fields via serde). | Unit |
| `merge_cli_overrides` | CLI flag `--parallelism=4` overrides `config.toml` value of `0`. CLI wins. | Unit |
| `merge_cli_preserves_file_values` | CLI flag absent, file value preserved exactly. | Unit |
| `round_trip_serialize_deserialize` | Property: `deserialize(serialize(config)) == config` for all fields. | Property |
| `env_var_override` | `GDESLOP_SCAN_EXCLUDE` overrides file-based exclude list. | Unit |
| `config_path_resolution` | Config loaded from workspace root, not CWD when invoked from subdirectory. | Integration |

```rust
#[test]
fn test_config_parse_valid_toml_all_keys() {
    let toml = r#"
        [scan]
        exclude = ["target/", "vendor/"]
        parallelism = 4
        
        [scoring]
        mechanical_weight = 0.6
        subjective_weight = 0.4
        
        [review]
        model = "claude-3"
        batch_size = 15
        
        [output]
        color = "always"
        scorecard_path = "custom-scorecard.png"
    "#;
    let config = Config::from_toml(toml).unwrap();
    assert_eq!(config.scan.exclude, vec!["target/", "vendor/"]);
    assert_eq!(config.scan.parallelism, 4);
    assert_approx_eq!(config.scoring.mechanical_weight, 0.6, 1e-10);
}
```

#### discovery tests

| Test | Description | Type |
|------|-------------|------|
| `discover_files_sample_tree` | Given a temp directory with known structure, discover returns expected file list. | Integration |
| `respect_exclude_patterns` | Files matching `exclude = ["target/"]` are not returned. | Unit |
| `handle_symlinks` | Symlink to file: included. Symlink loop: detected and skipped without panic. | Integration |
| `empty_directory_returns_empty` | Empty directory returns empty `Vec<SourceFile>`. | Unit |
| `relative_path_computation` | Discovered files have paths relative to project root, not absolute. | Unit |
| `gitignore_integration` | `.gitignore` patterns respected when `use_gitignore = true`. | Integration |
| `hidden_directories_excluded` | `.hidden/` directories excluded by default. | Unit |

#### registry tests

| Test | Description | Type |
|------|-------------|------|
| `all_detectors_registered` | `DetectorRegistry::all()` returns exactly 31 entries (30 mechanical + concerns). | Unit |
| `display_order_includes_all` | `display_order()` contains every registered detector ID. | Unit |
| `detector_meta_fields_non_empty` | Every `DetectorMeta` has non-empty `id`, `label`, `description`. | Unit |
| `dimension_mappings_valid` | Every detector maps to a valid `Dimension` variant. No orphan detectors. | Unit |
| `no_duplicate_detector_ids` | All detector IDs are unique. | Unit |
| `detector_lookup_by_id` | `registry.get("smells")` returns `Some(DetectorMeta)` with correct fields. | Unit |

#### enums tests

| Test | Description | Type |
|------|-------------|------|
| `status_round_trip` | `serde_json` serialize then deserialize preserves all `Status` variants. | Unit |
| `confidence_round_trip` | Same for `Confidence` (High, Medium, Low). | Unit |
| `tier_round_trip` | Same for `Tier` (T1, T2, T3, T4). | Unit |
| `zone_round_trip` | Same for `Zone` (Production, Test, Config, Generated, Vendor). | Unit |
| `status_display` | `Status::Open.to_string() == "open"`, etc. | Unit |
| `confidence_weight_lookup` | `Confidence::High.weight() == 1.0`, `Medium == 0.7`, `Low == 0.3`. | Unit |
| `tier_weight_lookup` | `Tier::T1.weight() == 1`, `T2 == 2`, `T3 == 3`, `T4 == 4`. | Unit |
| `status_from_str_invalid` | `Status::from_str("garbage")` returns `Err`. | Unit |
| `enum_exhaustive_match` | All enum variants covered by scoring constants (compile-time via match). | Compile |

---

### 2.2 genesis-deslop-engine

#### state tests

| Test | Description | Type |
|------|-------------|------|
| `load_valid_state_golden` | Load `tests/golden/state/sample_state.json` (exported from Python v0.8.0). Assert all fields parsed. | Integration |
| `save_reload_preserves_data` | Save state, reload from disk, assert deep equality. | Integration |
| `atomic_write_no_corruption` | Simulate failure mid-write (kill temp file). Original state file intact. | Integration |
| `backup_created_on_save` | After `save_state()`, `.genesis-deslop/state.json.bak` exists with previous content. | Integration |
| `empty_state_initialization` | `StateModel::new()` has zero findings, version field set, empty scan history. | Unit |
| `merge_scan_empty_findings_no_change` | Property: `merge_scan(state, vec![], opts)` does not change existing scores. | Property |
| `merge_scan_idempotent` | Property: applying same findings twice produces identical state. | Property |
| `finding_id_format` | Finding IDs match `"{detector}::{relpath}::{symbol}"` pattern. | Unit |
| `reopen_count_increments` | Fixed finding reproduced on scan: status -> open, reopen_count += 1. | Unit |
| `reopen_count_never_resets` | After multiple reopen/fix cycles, reopen_count only increases. | Unit |
| `auto_resolve_disappeared` | Open finding not in scan results -> status = auto_resolved. | Unit |
| `auto_resolve_preserves_manual` | Manually resolved (fixed/wontfix) findings not auto-resolved. | Unit |
| `resolve_valid_transitions` | open -> fixed, open -> wontfix, open -> false_positive: all valid. | Unit |
| `resolve_invalid_transitions` | auto_resolved -> wontfix: returns `Err`. | Unit |
| `scan_history_appended` | Each `merge_scan` appends to `state.scan_history`. | Unit |
| `content_hash_tracking` | Finding content hash updated on re-scan. | Unit |

```rust
#[test]
fn test_load_valid_state_golden() {
    let state = StateModel::load_from_path("tests/golden/state/sample_state.json").unwrap();
    assert!(state.findings.len() > 0);
    assert_eq!(state.version, 1);
    assert!(state.scan_history.len() >= 1);
}

proptest! {
    #[test]
    fn merge_scan_empty_preserves_scores(state in arbitrary_state()) {
        let original_scores = state.scores.clone();
        let mut state = state;
        merge_scan(&mut state, vec![], &MergeScanOptions::default());
        prop_assert_eq!(state.scores, original_scores);
    }
}
```

#### scoring tests (CRITICAL -- must match Python exactly)

**Constants verification:**

| Test | Description | Type |
|------|-------------|------|
| `confidence_weights_correct` | `CONFIDENCE_WEIGHTS[High] == 1.0`, `[Medium] == 0.7`, `[Low] == 0.3`. | Unit |
| `tier_weights_correct` | `TIER_WEIGHTS[T1] == 1`, `[T2] == 2`, `[T3] == 3`, `[T4] == 4`. | Unit |
| `file_cap_thresholds` | 1 finding/file -> cap 1.0, 3 findings -> cap 1.5, 6 findings -> cap 2.0. | Unit |
| `pool_weights` | `MECHANICAL_WEIGHT_FRACTION == 0.40`, `SUBJECTIVE_WEIGHT_FRACTION == 0.60`. | Unit |
| `min_sample_constant` | `MIN_SAMPLE == 200`. | Unit |

**Scoring pipeline tests:**

| Test | Description | Type |
|------|-------------|------|
| `empty_findings_all_scores_100` | No findings, no potentials -> all four channels = 100.0. | Unit |
| `single_high_confidence_t1` | One high-conf T1 finding: verify exact score reduction matches formula. | Unit |
| `single_medium_confidence_t3` | One medium-conf T3 finding: weight = 0.7, verify dimension score. | Unit |
| `file_cap_low_boundary` | 2 findings in same file: cap = 1.0, sum capped at 1.0. | Unit |
| `file_cap_mid_boundary` | 3 findings in same file: cap = 1.5. | Unit |
| `file_cap_high_boundary` | 6 findings in same file: cap = 2.0. | Unit |
| `min_sample_dampening` | Dimension with 50 checks (< MIN_SAMPLE=200): effective_wt = configured_wt * 0.25. | Unit |
| `pool_blending` | Given known mech_avg and subj_avg, verify overall = 0.4*mech + 0.6*subj. | Unit |
| `no_subjective_data_fallback` | No subjective assessments: overall = mechanical average only. | Unit |
| `no_mechanical_data_fallback` | No mechanical findings: overall = subjective average only. | Unit |
| `four_channel_scoring` | Lenient, strict, verified_strict all computed; verify strict <= overall. | Unit |
| `wontfix_counted_in_strict` | Finding with status=wontfix: passes lenient, fails strict. | Unit |
| `fixed_counted_in_verified` | Finding with status=fixed (not scan-verified): passes strict, fails verified_strict. | Unit |
| `auto_resolved_passes_all` | auto_resolved finding: passes all score modes. | Unit |
| `zone_exclusion_security` | Security finding in test zone: excluded from scoring. | Unit |
| `holistic_multiplier_display_only` | Holistic findings use 10x multiplier for display/priority, NOT in score computation. | Unit |

**Cross-validation tests (CRITICAL):**

| Test | Description | Type |
|------|-------------|------|
| `cross_validate_lenient_scores` | Same findings JSON -> Rust lenient scores match Python within 0.001. | Cross |
| `cross_validate_strict_scores` | Same findings JSON -> Rust strict scores match Python within 0.001. | Cross |
| `cross_validate_verified_strict` | Same findings JSON -> Rust verified_strict matches Python within 0.001. | Cross |
| `cross_validate_dimension_scores` | Per-dimension scores match Python within 0.001. | Cross |
| `cross_validate_large_finding_set` | 5000+ findings -> scores match Python within 0.001. | Cross |
| `cross_validate_mixed_statuses` | Findings with all 5 statuses -> all channels match Python. | Cross |

**Property-based tests:**

| Test | Description | Type |
|------|-------------|------|
| `scores_always_bounded` | For any finding set: all scores in [0.0, 100.0]. | Property |
| `strict_leq_overall` | For any finding set: strict_score <= overall_score. | Property |
| `verified_leq_strict` | For any finding set: verified_strict_score <= strict_score. | Property |
| `more_findings_lower_score` | Adding findings never increases scores (monotone decreasing). | Property |
| `dimension_scores_bounded` | Every dimension score in [0.0, 100.0]. | Property |

```rust
proptest! {
    #[test]
    fn scores_always_bounded(findings in vec(arbitrary_finding(), 0..1000)) {
        let scores = compute_health_breakdown(
            &findings, ScoreMode::Lenient, &Config::default()
        );
        prop_assert!(scores.overall_score >= 0.0);
        prop_assert!(scores.overall_score <= 100.0);
        prop_assert!(scores.strict_score >= 0.0);
        prop_assert!(scores.strict_score <= 100.0);
        prop_assert!(scores.verified_strict_score >= 0.0);
        prop_assert!(scores.verified_strict_score <= 100.0);
    }

    #[test]
    fn strict_leq_overall(findings in vec(arbitrary_finding(), 0..500)) {
        let scores = compute_health_breakdown(
            &findings, ScoreMode::Lenient, &Config::default()
        );
        prop_assert!(
            scores.strict_score <= scores.overall_score + 0.001,
            "strict {} > overall {}",
            scores.strict_score,
            scores.overall_score
        );
    }

    #[test]
    fn verified_leq_strict(findings in vec(arbitrary_finding(), 0..500)) {
        let scores = compute_health_breakdown(
            &findings, ScoreMode::Lenient, &Config::default()
        );
        prop_assert!(
            scores.verified_strict_score <= scores.strict_score + 0.001,
            "verified {} > strict {}",
            scores.verified_strict_score,
            scores.strict_score
        );
    }
}
```

**Anti-gaming tests:**

| Test | Description | Type |
|------|-------------|------|
| `target_match_detection` | Subjective assessment matching target within 0.05 tolerance: flagged. | Unit |
| `target_match_penalty` | Flagged dimensions reset to score 0. | Unit |
| `subjective_target_reset` | Threshold >= 2 dimensions flagged: all subjective targets reset. | Unit |
| `placeholder_detection` | Assessment with generic placeholder text: flagged. | Unit |
| `wontfix_accountability` | >30% findings wontfixed: accountability warning raised. | Unit |

#### detector tests (per detector)

For **each** of the 31+ detectors, the following test matrix applies:

| Test Pattern | Description | Type |
|--------------|-------------|------|
| `test_{detector}_positive_case` | Known bad code pattern produces expected finding. | Unit |
| `test_{detector}_negative_case` | Clean code produces zero findings. | Unit |
| `test_{detector}_threshold_boundary` | Exactly at threshold: no finding. Threshold + 1: finding. | Unit |
| `test_{detector}_zone_exclusion` | Detector correctly skips excluded zones. | Unit |
| `test_{detector}_golden_file` | Sample input produces expected findings list (golden file comparison). | Integration |

**Key detectors requiring exhaustive tests:**

##### Duplicate detection (`dupes`)

| Test | Description | Type |
|------|-------------|------|
| `exact_hash_match` | Two identical functions -> duplicate finding. | Unit |
| `near_duplicate_threshold` | Functions at 0.9 similarity -> duplicate. Functions at 0.89 -> no duplicate. | Unit |
| `loc_ratio_pruning` | Functions with LOC ratio > 1.5x: pruned from duplicate pair. | Unit |
| `union_find_clustering` | 3 pairwise-similar functions form one cluster, not three pairs. | Unit |
| `cross_file_duplicates` | Duplicate detected across different files. | Unit |
| `ignore_trivial_functions` | Functions < 4 lines: excluded from duplicate detection. | Unit |
| `stable_cluster_ids` | Same inputs produce same cluster assignments. | Property |

##### Cycle detection (`cycles`)

| Test | Description | Type |
|------|-------------|------|
| `tarjan_scc_simple_cycle` | A -> B -> A produces SCC {A, B}. | Unit |
| `tarjan_scc_complex` | Diamond with back-edge: correct SCC identification. | Unit |
| `no_false_cycles_deferred_imports` | Python `TYPE_CHECKING` imports excluded from cycle graph. | Unit |
| `self_import_ignored` | File importing itself: no cycle reported. | Unit |
| `multi_component_sccs` | Graph with 3 independent SCCs: all found. | Unit |

##### Complexity (`complexity`)

| Test | Description | Type |
|------|-------------|------|
| `cyclomatic_if_else` | Single if/else: complexity = 2. | Unit |
| `cyclomatic_nested_loops` | Nested for/while: complexity compounds correctly. | Unit |
| `cyclomatic_match_arms` | Match with 5 arms: complexity = 5. | Unit |
| `cyclomatic_boolean_operators` | `&&` and `||` each add 1 to complexity. | Unit |
| `nesting_depth_calculation` | 4 levels of nesting: depth = 4. | Unit |
| `threshold_boundary` | Complexity exactly 15 (default threshold): no finding. 16: finding. | Unit |

##### Security (`security`)

| Test | Description | Type |
|------|-------------|------|
| `hardcoded_secret_detection` | `password = "hunter2"` in source: finding produced. | Unit |
| `api_key_pattern` | `AKIA...` pattern detected as AWS key. | Unit |
| `test_file_exclusion` | Security patterns in test files: excluded by zone. | Unit |
| `false_positive_suppression` | Known safe patterns (e.g., `password_hash`) not flagged. | Unit |
| `per_language_patterns` | TypeScript, Python, C# each have language-specific security rules. | Unit |
| `severity_classification` | Hardcoded secrets = high confidence. Weak crypto = medium. | Unit |

##### Additional detectors

Each of the following detectors has the standard 5-test matrix plus
detector-specific edge cases:

- `structural` (large files): threshold at 500 lines, LOC counting excludes blanks
- `unused`: unused exports, dead code detection
- `smells`: per-language smell patterns (TS: 28, Python: 32)
- `coupling`: high fan-in/fan-out detection
- `orphaned`: files with zero importers
- `naming`: naming convention violations
- `gods`: god class/module detection (TS, Python, C# only)
- `test_coverage`: test-to-source file mapping
- `single_use`: single-use wrapper detection
- `passthrough`: passthrough/facade detection
- `boilerplate_duplication`: boilerplate pattern detection
- `responsibility_cohesion`: class responsibility analysis
- `private_imports`: private module boundary violations
- `layer_violation`: architectural layer boundary detection
- `global_mutable_config`: global mutable state detection
- `react`: React-specific patterns (TSX only)
- `deprecated`: deprecated API usage
- `flat_dirs`: overly flat directory structures
- `stale_exclude`: stale exclusion pattern detection
- `signature`: function signature analysis
- `review_coverage`: subjective review freshness tracking
- `concerns`: concern generator (mechanical -> subjective bridge)

#### work_queue tests

| Test | Description | Type |
|------|-------------|------|
| `clusters_before_findings` | Clusters always sort before individual findings in queue. | Unit |
| `tier_ordering` | T1 findings before T2, T2 before T3, T3 before T4. | Unit |
| `mechanical_before_subjective` | Within same tier: mechanical findings before subjective. | Unit |
| `confidence_ordering` | Within same tier+pool: high before medium before low. | Unit |
| `cluster_sort_by_member_count` | Larger clusters sort before smaller ones. | Unit |
| `cluster_action_priority` | auto_fix clusters before reorganize before refactor before manual_fix. | Unit |
| `skip_filtering` | Skipped findings excluded when `include_skipped = false`. | Unit |
| `wontfix_filtering` | Wontfix findings excluded when `include_wontfix = false`. | Unit |
| `chronic_reopener_surface` | Findings with reopen_count >= 2 surface with `--chronic` flag. | Unit |
| `stable_sort_on_equal_keys` | Equal-ranked items maintain insertion order (stable sort). | Unit |
| `empty_findings_empty_queue` | No findings produces empty work queue. | Unit |

```rust
#[test]
fn test_queue_clusters_before_findings() {
    let items = build_work_queue(&state_with_cluster_and_findings(), &QueueOptions::default());
    assert!(matches!(items[0].kind, WorkItemKind::Cluster { .. }));
    assert!(matches!(items[1].kind, WorkItemKind::Finding { .. }));
}

#[test]
fn test_queue_tier_ordering() {
    let items = build_work_queue(&state_with_mixed_tiers(), &QueueOptions::default());
    let tiers: Vec<Tier> = items.iter().filter_map(|i| i.effective_tier()).collect();
    assert!(tiers.windows(2).all(|w| w[0] <= w[1]));
}
```

#### plan tests

| Test | Description | Type |
|------|-------------|------|
| `load_valid_plan_golden` | Load `tests/golden/plan/sample_plan.json` (from Python v0.8.0). | Integration |
| `skip_unskip_round_trip` | Skip finding, then unskip: finding status restored to open. | Unit |
| `cluster_create` | Create cluster with 3 findings: cluster exists, findings linked. | Unit |
| `cluster_delete` | Delete cluster: findings unlinked, cluster removed. | Unit |
| `cluster_update_members` | Add/remove findings from existing cluster. | Unit |
| `auto_cluster_union_find` | `auto_cluster()` uses union-find to group overlapping files. | Unit |
| `plan_reconciliation_superseded` | Finding absent for 90+ days: marked superseded in plan. | Unit |
| `plan_reconciliation_resurface` | Stale skip (finding reappeared): skip record surfaced for review. | Unit |
| `queue_ordering_persistence` | Queue order survives save/reload cycle. | Integration |
| `empty_plan_initialization` | `PlanModel::new()` has empty skip/cluster/override maps. | Unit |

#### concern tests

| Test | Description | Type |
|------|-------------|------|
| `per_file_concern_generation` | File with 5+ smells + high complexity: concern generated. | Unit |
| `cross_file_pattern_3_plus` | 3+ files with same concern profile: cross-file concern raised. | Unit |
| `systemic_smell_5_plus` | 5+ files sharing same smell: systemic concern raised. | Unit |
| `fingerprint_determinism` | Same input always produces same concern fingerprint. | Property |
| `concern_evidence_populated` | Generated concerns include evidence (finding IDs, file paths). | Unit |
| `concern_question_non_empty` | Every concern has a non-empty investigation question. | Unit |

---

### 2.3 genesis-deslop-lang

#### framework tests

| Test | Description | Type |
|------|-------------|------|
| `lang_config_construction` | `LangConfig` with all required fields: no panic. | Unit |
| `generic_lang_factory` | `generic_lang("ruby", ...)` produces valid `LangConfig`. | Unit |
| `phase_ordering_preserved` | Phases registered in order 1..12 are returned in that order. | Unit |
| `zone_rules_match_expected` | TypeScript zone rules: `*.test.ts` -> Test, `*.config.ts` -> Config. | Unit |
| `file_discovery_respects_exclusions` | Build artifacts (`dist/`, `node_modules/`) excluded. | Unit |

#### per-language tests (28 languages)

For **each** registered language, the following tests apply:

| Test | Description | Type |
|------|-------------|------|
| `test_{lang}_extension_matching` | Language correctly matches its registered extensions. | Unit |
| `test_{lang}_file_discovery_excludes_build` | Language-specific build dirs excluded. | Unit |
| `test_{lang}_function_extraction` | Sample source file -> expected `FunctionInfo` list. | Integration |
| `test_{lang}_class_extraction` | Sample source -> expected `ClassInfo` list (where applicable). | Integration |
| `test_{lang}_complexity_signals` | Sample functions -> expected complexity values. | Integration |

**Full-depth languages** (Python, TypeScript, JavaScript, Rust, Go, Java) additionally require:

| Test | Description | Type |
|------|-------------|------|
| `test_{lang}_god_rule_evaluation` | Known god class -> finding (TS, Python, C# only). | Integration |
| `test_{lang}_dependency_graph` | Sample project -> correct dep graph edges. | Integration |
| `test_{lang}_security_detection` | Known security patterns -> correct findings. | Integration |
| `test_{lang}_smell_detection` | Known smell patterns -> expected findings. | Integration |
| `test_{lang}_move_module_imports` | Module rename -> correct import replacement computation. | Integration |
| `test_{lang}_linter_output_parsing` | Sample linter JSON -> correct findings. | Unit |

Language-specific test counts for smell detection:

| Language | Expected Smell Checks | Test File |
|----------|--------------------|-----------|
| TypeScript | 28 | `tests/langs/typescript_smells.rs` |
| Python | 32 | `tests/langs/python_smells.rs` |
| JavaScript | 28 | `tests/langs/javascript_smells.rs` |
| Rust | 18 | `tests/langs/rust_smells.rs` |
| Go | 14 | `tests/langs/go_smells.rs` |
| C# | 20 | `tests/langs/csharp_smells.rs` |

#### tree-sitter integration tests (feature-gated)

| Test | Description | Type |
|------|-------------|------|
| `parser_init_all_grammars` | All 28 tree-sitter grammar parsers initialize without error. | Integration |
| `import_query_extraction` | TypeScript: `import { foo } from './bar'` -> correct ImportInfo. | Unit |
| `class_query_extraction` | Python: `class Foo(Bar):` -> ClassInfo with parent `Bar`. | Unit |
| `import_resolution_per_lang` | Each language resolves relative/absolute imports correctly. | Unit |
| `graceful_degradation` | Missing grammar: detector degrades to shallow mode, no panic. | Unit |

```rust
#[test]
#[cfg(feature = "tree-sitter")]
fn test_parser_init_typescript() {
    let parser = TreeSitterParser::for_language("typescript").unwrap();
    let source = b"function hello(): void { console.log('hi'); }";
    let tree = parser.parse(source, None).unwrap();
    assert!(!tree.root_node().has_error());
}
```

---

### 2.4 genesis-deslop-intel

#### review tests

| Test | Description | Type |
|------|-------------|------|
| `blind_packet_excludes_scores` | `prepare_review()` output contains no score fields. | Unit |
| `blind_packet_includes_context` | Packet contains file content, zone, neighbors, existing findings. | Unit |
| `batch_result_normalization_valid` | Valid LLM JSON output -> `NormalizedBatchResult` with correct fields. | Unit |
| `batch_result_normalization_invalid` | Malformed JSON -> `Err` with `GD-4xxx` code. | Unit |
| `batch_result_confidence_normalization` | "HIGH" -> High, "med" -> Medium, "L" -> Low. | Unit |
| `merge_dedup_jaccard` | Two findings with Jaccard > threshold: deduplicated (keep higher confidence). | Unit |
| `merge_dedup_below_threshold` | Two findings with Jaccard < threshold: both kept. | Unit |
| `import_trusted_internal` | Trusted findings + assessments imported, scores applied. | Unit |
| `import_attested_external` | External findings imported, attestation required before scoring. | Unit |
| `import_findings_only` | Findings imported, no assessments applied. | Unit |
| `import_manual_override` | Direct score override with attestation recorded. | Unit |
| `provenance_sha256` | Import provenance includes SHA-256 of source data. | Unit |
| `dimension_merge_scorer` | 70/30 blend, max penalty 24.0 per dimension. | Unit |
| `holistic_overwrites_per_file` | Holistic assessment overwrites per-file for same dimension. | Unit |
| `per_file_no_overwrite_holistic` | Per-file assessment does not overwrite existing holistic. | Unit |
| `assessment_score_clamped` | Score values clamped to [0, 100]. | Unit |

```rust
#[test]
fn test_blind_packet_no_scores() {
    let state = load_test_state_with_scores();
    let packets = prepare_review(&state, &ReviewOptions::default()).unwrap();
    for packet in &packets {
        let json = serde_json::to_string(packet).unwrap();
        assert!(!json.contains("\"score\""));
        assert!(!json.contains("\"overall_score\""));
        assert!(!json.contains("\"strict_score\""));
    }
}
```

#### narrative tests

| Test | Description | Type |
|------|-------------|------|
| `phase_detection_first_scan` | Empty scan history -> "first_scan". | Unit |
| `phase_detection_regression` | Strict dropped > 0.5 from previous -> "regression". | Unit |
| `phase_detection_stagnation` | Last 3 scans within 0.5 spread -> "stagnation". | Unit |
| `phase_detection_early_momentum` | Scans 2-5 with rising score -> "early_momentum". | Unit |
| `phase_detection_maintenance` | Strict > 93 -> "maintenance". | Unit |
| `phase_detection_refinement` | Strict 80-93 -> "refinement". | Unit |
| `phase_detection_middle_grind` | Default fallthrough -> "middle_grind". | Unit |
| `action_auto_fix` | Findings with available fixers -> "auto_fix" action. | Unit |
| `action_manual_fix` | Findings without fixers -> "manual_fix" action. | Unit |
| `action_reorganize` | Flat directory findings -> "reorganize" action. | Unit |
| `action_debt_review` | High wontfix count -> "debt_review" action. | Unit |
| `lane_grouping_union_find` | Actions touching same files grouped into same lane. | Unit |
| `lane_grouping_independent` | Actions on disjoint files -> separate lanes. | Unit |
| `reminder_decay` | Reminder shown 3 times -> suppressed on 4th scan. | Unit |
| `reminder_resurfacing` | After decay threshold scans, reminder re-shown. | Unit |
| `headline_per_phase` | Each of 7 phases produces a non-empty headline. | Unit |
| `milestone_detection_90` | Previous strict < 90, current >= 90 -> "Crossed 90%!" | Unit |
| `milestone_detection_zero_open` | Zero open findings (total > 0) -> "Zero open findings!" | Unit |

```rust
#[test]
fn test_phase_detection_regression() {
    let history = vec![
        ScanRecord { strict_score: 85.0, .. },
        ScanRecord { strict_score: 84.0, .. }, // dropped 1.0 > 0.5
    ];
    let phase = detect_phase(&history);
    assert_eq!(phase, Phase::Regression);
}
```

#### integrity tests

| Test | Description | Type |
|------|-------------|------|
| `target_match_at_tolerance` | Assessment score within 0.05 of target: flagged. | Unit |
| `target_match_outside_tolerance` | Assessment score > 0.05 from target: not flagged. | Unit |
| `placeholder_detection_generic` | "This looks good" or similar generic text: flagged. | Unit |
| `placeholder_detection_specific` | Detailed, specific assessment text: not flagged. | Unit |
| `wontfix_accountability_threshold` | >30% wontfix rate: warning raised. | Unit |
| `wontfix_accountability_below` | <30% wontfix rate: no warning. | Unit |
| `integrity_status_disabled` | When anti-gaming disabled in config: no checks run. | Unit |

---

### 2.5 genesis-deslop-cli

#### command tests (integration)

| Test | Description | Type |
|------|-------------|------|
| `scan_produces_state` | `gdeslop scan` on sample project -> `.genesis-deslop/state.json` created. | Integration |
| `status_displays_scores` | `gdeslop status` -> output contains score values. | Integration |
| `next_returns_highest_priority` | `gdeslop next` -> returns T1/cluster item first. | Integration |
| `plan_skip_marks_skipped` | `gdeslop plan skip <id>` -> finding marked skipped in plan.json. | Integration |
| `all_commands_parse` | Each of 18 commands with `--help` exits 0. | Integration |
| `error_codes_in_range` | Filesystem error -> GD-1xxx, config error -> GD-2xxx, etc. | Integration |
| `unknown_command_error` | `gdeslop foobar` -> helpful error message, exit code 2. | Integration |
| `version_flag` | `gdeslop --version` -> "genesis-deslop v1.0.0". | Integration |
| `no_color_flag` | `gdeslop --color=never status` -> output has no ANSI codes. | Integration |
| `json_output` | `gdeslop status --json` -> valid JSON on stdout. | Integration |
| `legacy_state_detection` | `.desloppify/` present -> note[GD-6001] printed. | Integration |

```rust
#[test]
fn test_scan_produces_state() {
    let project = sample_typescript_project();
    let output = Command::new(env!("CARGO_BIN_EXE_gdeslop"))
        .args(["scan", "--lang", "typescript"])
        .current_dir(project.path())
        .output()
        .unwrap();
    assert!(output.status.success());
    assert!(project.path().join(".genesis-deslop/state.json").exists());
}
```

#### output tests (snapshot)

| Test | Description | Type |
|------|-------------|------|
| `scorecard_png_reference` | Generated PNG pixel-level comparison at 95% tolerance against reference. | Snapshot |
| `treemap_html_valid` | Generated HTML passes basic validity checks (balanced tags, DOCTYPE). | Snapshot |
| `tree_text_format` | Tree text output matches expected indentation and formatting. | Snapshot |
| `table_formatting_narrow` | Table with narrow terminal width: truncation correct. | Snapshot |
| `table_formatting_wide` | Table with wide terminal: columns expand correctly. | Snapshot |
| `status_output_snapshot` | `status` command output matches `insta` snapshot. | Snapshot |
| `next_output_snapshot` | `next` command output matches `insta` snapshot. | Snapshot |

```rust
#[test]
fn test_status_output_snapshot() {
    let state = load_golden_state();
    let output = format_status(&state, &FormatOptions::default());
    insta::assert_snapshot!(output);
}
```

---

## 3. Golden File Test Infrastructure

### 3.1 Directory Structure

```
tests/golden/
├── state/
│   ├── sample_state.json              # Exported from Python v0.8.0 `desloppify`
│   ├── sample_state_empty.json        # Empty state (fresh initialization)
│   ├── sample_state_mixed_status.json # Findings in all 5 statuses
│   └── expected_scores.json           # Python-computed scores for sample_state.json
│
├── findings/
│   ├── sample_findings.json           # Raw detector output (50+ findings)
│   ├── sample_findings_large.json     # 5000+ findings for stress testing
│   └── expected_queue.json            # Expected work queue ordering
│
├── plan/
│   ├── sample_plan.json               # From Python v0.8.0
│   ├── sample_plan_with_clusters.json # Plan with cluster definitions
│   └── expected_reconciled.json       # After 90-day reconciliation
│
├── detectors/
│   ├── dupes/
│   │   ├── input_functions.json       # Function extraction input
│   │   └── expected_clusters.json     # Expected duplicate clusters
│   ├── complexity/
│   │   ├── input_source.json          # Source with known complexity
│   │   └── expected_findings.json     # Expected complexity findings
│   ├── security/
│   │   ├── input_patterns.json        # Source with security issues
│   │   └── expected_findings.json     # Expected security findings
│   └── {detector}/                    # Same pattern for each detector
│       ├── input_{scenario}.json
│       └── expected_{scenario}.json
│
├── scoring/
│   ├── input_simple.json              # Simple case: 3 findings
│   ├── expected_simple.json           # Expected scores
│   ├── input_complex.json             # Complex: mixed statuses, all tiers
│   ├── expected_complex.json          # Expected scores
│   ├── input_file_capping.json        # Multiple findings per file
│   └── expected_file_capping.json     # Expected capped scores
│
└── samples/
    ├── typescript/                     # Sample TypeScript project
    │   ├── package.json
    │   ├── tsconfig.json
    │   └── src/
    │       ├── index.ts
    │       ├── utils.ts               # Contains known patterns
    │       └── components/
    │           ├── Header.tsx
    │           └── GodComponent.tsx    # Known god class
    ├── python/                         # Sample Python project
    │   ├── pyproject.toml
    │   └── src/
    │       ├── __init__.py
    │       ├── main.py
    │       └── utils.py
    └── rust/                           # Sample Rust project
        ├── Cargo.toml
        └── src/
            ├── lib.rs
            └── main.rs
```

### 3.2 Golden File Generation

Golden files are generated from the Python v0.8.0 reference implementation using
a dedicated export script:

```bash
# Run from the Python desloppify root
python -m desloppify.tests.export_golden \
    --state tests/golden/state/sample_state.json \
    --findings tests/golden/findings/sample_findings.json \
    --scores tests/golden/scoring/expected_simple.json \
    --plan tests/golden/plan/sample_plan.json
```

The export script computes and serializes:
1. Raw state after scanning a sample project
2. Findings from each detector
3. Exact scores from `compute_score_bundle()`
4. Plan after reconciliation

Golden files are version-stamped:
```json
{
  "golden_version": "0.8.0",
  "generated_at": "2026-02-28T00:00:00Z",
  "python_version": "3.12.0",
  "tool": "desloppify",
  ...
}
```

### 3.3 Golden File Test Macro

```rust
/// Macro for golden file tests. Loads input, runs function, compares to expected.
macro_rules! golden_test {
    ($name:ident, $input_path:expr, $expected_path:expr, $transform:expr) => {
        #[test]
        fn $name() {
            let input = load_golden_file($input_path);
            let expected = load_golden_file($expected_path);
            let actual = ($transform)(input);
            assert_golden_match(actual, expected, stringify!($name));
        }
    };
}

golden_test!(
    scoring_simple,
    "tests/golden/scoring/input_simple.json",
    "tests/golden/scoring/expected_simple.json",
    |input| compute_health_breakdown_from_json(input)
);
```

---

## 4. Cross-Validation Test Framework

### 4.1 Architecture

Cross-validation tests run both Rust and Python implementations on the same input
and assert output equality within tolerance.

```
┌───────────────────────┐     ┌──────────────────────┐
│  Golden Input JSON    │     │  Golden Input JSON    │
│  (shared fixture)     │     │  (shared fixture)     │
└──────────┬────────────┘     └──────────┬───────────┘
           │                             │
           ▼                             ▼
┌───────────────────────┐     ┌──────────────────────┐
│  Rust Implementation  │     │  Python v0.8.0       │
│  (direct call)        │     │  (subprocess)        │
└──────────┬────────────┘     └──────────┬───────────┘
           │                             │
           ▼                             ▼
┌───────────────────────┐     ┌──────────────────────┐
│  Rust Output JSON     │     │  Python Output JSON  │
└──────────┬────────────┘     └──────────┬───────────┘
           │                             │
           └──────────┬─────────────────┘
                      │
                      ▼
            ┌──────────────────────┐
            │  assert_scores_equal │
            │  (tolerance: 0.001)  │
            └──────────────────────┘
```

### 4.2 Python Bridge

```rust
/// Runs a Python function from the desloppify reference implementation
/// and returns the output as a serde_json::Value.
fn run_python_reference(function: &str, input: &serde_json::Value) -> serde_json::Value {
    let input_path = tempfile::NamedTempFile::new().unwrap();
    serde_json::to_writer(&input_path, input).unwrap();

    let output = std::process::Command::new("python3")
        .args([
            "-m", "desloppify.tests.cross_validation_bridge",
            "--function", function,
            "--input", input_path.path().to_str().unwrap(),
        ])
        .output()
        .expect("Python 3.12+ required for cross-validation tests");

    assert!(
        output.status.success(),
        "Python bridge failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    serde_json::from_slice(&output.stdout).unwrap()
}
```

### 4.3 Cross-Validation Test Suite

```rust
/// Cross-validation tests. Require Python 3.12+ with desloppify installed.
/// Run with: cargo test -- --ignored
mod cross_validation {
    use super::*;

    #[test]
    #[ignore] // Only run in CI with Python available
    fn cross_validate_scoring_lenient() {
        let findings = load_golden_findings("tests/golden/findings/sample_findings.json");
        let rust_scores = compute_health_breakdown(
            &findings, ScoreMode::Lenient, &Config::default()
        );
        let python_scores = run_python_reference("compute_scores_lenient", &findings);
        assert_scores_equal(rust_scores.overall_score, python_scores["overall_score"], 0.001);
        assert_scores_equal(rust_scores.objective_score, python_scores["objective_score"], 0.001);
    }

    #[test]
    #[ignore]
    fn cross_validate_scoring_strict() {
        let findings = load_golden_findings("tests/golden/findings/sample_findings.json");
        let rust_scores = compute_health_breakdown(
            &findings, ScoreMode::Strict, &Config::default()
        );
        let python_scores = run_python_reference("compute_scores_strict", &findings);
        assert_scores_equal(rust_scores.strict_score, python_scores["strict_score"], 0.001);
    }

    #[test]
    #[ignore]
    fn cross_validate_scoring_verified_strict() {
        let findings = load_golden_findings("tests/golden/findings/sample_findings.json");
        let rust_scores = compute_health_breakdown(
            &findings, ScoreMode::VerifiedStrict, &Config::default()
        );
        let python_scores = run_python_reference("compute_scores_verified", &findings);
        assert_scores_equal(
            rust_scores.verified_strict_score,
            python_scores["verified_strict_score"],
            0.001
        );
    }

    #[test]
    #[ignore]
    fn cross_validate_per_dimension_scores() {
        let findings = load_golden_findings("tests/golden/findings/sample_findings.json");
        let rust_dims = compute_dimension_scores(&findings, &Config::default());
        let python_dims = run_python_reference("compute_dimension_scores", &findings);

        for (dim_name, rust_score) in &rust_dims {
            let python_score = python_dims[dim_name].as_f64().unwrap();
            assert_scores_equal(*rust_score, python_score, 0.001);
        }
    }

    #[test]
    #[ignore]
    fn cross_validate_large_finding_set() {
        let findings = load_golden_findings("tests/golden/findings/sample_findings_large.json");
        let rust_scores = compute_health_breakdown(
            &findings, ScoreMode::Lenient, &Config::default()
        );
        let python_scores = run_python_reference("compute_scores_lenient", &findings);
        assert_scores_equal(rust_scores.overall_score, python_scores["overall_score"], 0.001);
    }

    #[test]
    #[ignore]
    fn cross_validate_work_queue_ordering() {
        let state = load_golden_state("tests/golden/state/sample_state.json");
        let rust_queue = build_work_queue(&state, &QueueOptions::default());
        let python_queue = run_python_reference("build_work_queue", &state);

        let rust_ids: Vec<&str> = rust_queue.iter().map(|i| i.id.as_str()).collect();
        let python_ids: Vec<String> = python_queue.as_array().unwrap()
            .iter().map(|v| v["id"].as_str().unwrap().to_string()).collect();
        assert_eq!(rust_ids, python_ids, "Work queue ordering mismatch");
    }

    #[test]
    #[ignore]
    fn cross_validate_state_merge() {
        let state = load_golden_state("tests/golden/state/sample_state.json");
        let findings = load_golden_findings("tests/golden/findings/sample_findings.json");

        let mut rust_state = state.clone();
        merge_scan(&mut rust_state, findings.clone(), &MergeScanOptions::default());

        let python_result = run_python_reference("merge_scan", &serde_json::json!({
            "state": state,
            "findings": findings,
        }));

        assert_eq!(
            rust_state.findings.len(),
            python_result["finding_count"].as_u64().unwrap() as usize
        );
    }
}
```

### 4.4 Tolerance Policy

| Comparison Type | Tolerance | Rationale |
|----------------|-----------|-----------|
| Score values (f64) | 0.001 | Floating-point arithmetic differences between Rust and Python |
| Finding counts | Exact | Integer values must match exactly |
| Finding IDs | Exact | String comparisons must be identical |
| Queue ordering | Exact | Item order must match exactly |
| Timestamps | Ignored | Timestamps naturally differ between runs |
| Content hashes | Exact | SHA-256 hashes must be identical |

---

## 5. Property-Based Tests (proptest)

### 5.1 Arbitrary Generators

```rust
use proptest::prelude::*;

/// Generates an arbitrary Finding with valid field combinations.
fn arbitrary_finding() -> impl Strategy<Value = Finding> {
    (
        prop::sample::select(vec![
            "structural", "smells", "coupling", "dupes", "security",
            "naming", "orphaned", "unused", "complexity", "test_coverage",
        ]),
        "[a-z]{1,20}/[a-z]{1,20}\\.(ts|py|rs)",
        "[a-z_]{3,30}",
        prop::sample::select(vec![
            Status::Open, Status::Fixed, Status::AutoResolved,
            Status::Wontfix, Status::FalsePositive,
        ]),
        prop::sample::select(vec![
            Confidence::High, Confidence::Medium, Confidence::Low,
        ]),
        prop::sample::select(vec![Tier::T1, Tier::T2, Tier::T3, Tier::T4]),
    ).prop_map(|(detector, path, symbol, status, confidence, tier)| {
        Finding {
            id: format!("{detector}::{path}::{symbol}"),
            detector: detector.to_string(),
            path: path.to_string(),
            symbol: symbol.to_string(),
            status,
            confidence,
            tier,
            first_seen: chrono::Utc::now(),
            last_seen: chrono::Utc::now(),
            reopen_count: 0,
            detail: FindingDetail::default(),
            resolution_attestation: None,
        }
    })
}

/// Generates an arbitrary StateModel with 0..N findings.
fn arbitrary_state() -> impl Strategy<Value = StateModel> {
    prop::collection::vec(arbitrary_finding(), 0..200)
        .prop_map(|findings| {
            let mut state = StateModel::new();
            for f in findings {
                state.findings.insert(f.id.clone(), f);
            }
            state
        })
}

/// Generates an arbitrary Config with valid ranges.
fn arbitrary_config() -> impl Strategy<Value = Config> {
    (0.0..=1.0f64, 0.0..=1.0f64, 1u32..=32)
        .prop_map(|(mech_w, subj_w, parallelism)| {
            let total = mech_w + subj_w;
            Config {
                scoring: ScoringConfig {
                    mechanical_weight: mech_w / total,
                    subjective_weight: subj_w / total,
                },
                scan: ScanConfig {
                    parallelism,
                    ..Default::default()
                },
                ..Default::default()
            }
        })
}
```

### 5.2 Property Test Suite

```rust
proptest! {
    /// Scores are always in [0.0, 100.0] regardless of input.
    #[test]
    fn scores_always_bounded(findings in vec(arbitrary_finding(), 0..1000)) {
        let scores = compute_health_breakdown(
            &findings, ScoreMode::Lenient, &Config::default()
        );
        prop_assert!(scores.overall_score >= 0.0 && scores.overall_score <= 100.0);
        prop_assert!(scores.strict_score >= 0.0 && scores.strict_score <= 100.0);
        prop_assert!(scores.verified_strict_score >= 0.0 && scores.verified_strict_score <= 100.0);
        prop_assert!(scores.objective_score >= 0.0 && scores.objective_score <= 100.0);
    }

    /// Strict score never exceeds overall score (more findings count as failures).
    #[test]
    fn strict_leq_overall(findings in vec(arbitrary_finding(), 0..500)) {
        let scores = compute_health_breakdown(
            &findings, ScoreMode::Lenient, &Config::default()
        );
        prop_assert!(scores.strict_score <= scores.overall_score + 0.001);
    }

    /// Verified strict never exceeds strict.
    #[test]
    fn verified_leq_strict(findings in vec(arbitrary_finding(), 0..500)) {
        let scores = compute_health_breakdown(
            &findings, ScoreMode::Lenient, &Config::default()
        );
        prop_assert!(scores.verified_strict_score <= scores.strict_score + 0.001);
    }

    /// merge_scan is idempotent: applying the same findings twice
    /// produces identical state.
    #[test]
    fn merge_scan_idempotent(
        state in arbitrary_state(),
        findings in vec(arbitrary_finding(), 0..100)
    ) {
        let mut state1 = state.clone();
        let mut state2 = state.clone();

        merge_scan(&mut state1, findings.clone(), &MergeScanOptions::default());
        merge_scan(&mut state2, findings.clone(), &MergeScanOptions::default());
        merge_scan(&mut state2, findings, &MergeScanOptions::default());

        prop_assert_eq!(state1.findings, state2.findings);
    }

    /// Config round-trip: serialize then deserialize preserves all fields.
    #[test]
    fn config_round_trip(config in arbitrary_config()) {
        let toml_str = toml::to_string(&config).unwrap();
        let roundtripped: Config = toml::from_str(&toml_str).unwrap();
        prop_assert_eq!(config, roundtripped);
    }

    /// Finding IDs are deterministic: same inputs produce same ID.
    #[test]
    fn finding_id_deterministic(
        detector in "[a-z_]+",
        path in "[a-z/]+\\.[a-z]+",
        symbol in "[a-z_]+"
    ) {
        let id1 = Finding::compute_id(&detector, &path, &symbol);
        let id2 = Finding::compute_id(&detector, &path, &symbol);
        prop_assert_eq!(id1, id2);
    }

    /// Work queue ordering is total: no panics from comparison.
    #[test]
    fn work_queue_total_ordering(state in arbitrary_state()) {
        let queue = build_work_queue(&state, &QueueOptions::default());
        // Verify no panic occurred and result is non-empty iff state has open findings
        let open_count = state.findings.values()
            .filter(|f| f.status == Status::Open)
            .count();
        if open_count > 0 {
            prop_assert!(!queue.is_empty());
        }
    }

    /// Concern fingerprints are deterministic.
    #[test]
    fn concern_fingerprint_deterministic(
        findings in vec(arbitrary_finding(), 1..50)
    ) {
        let concerns1 = generate_concerns(&findings);
        let concerns2 = generate_concerns(&findings);
        let fps1: Vec<_> = concerns1.iter().map(|c| &c.fingerprint).collect();
        let fps2: Vec<_> = concerns2.iter().map(|c| &c.fingerprint).collect();
        prop_assert_eq!(fps1, fps2);
    }

    /// Dimension scores are always in [0.0, 100.0].
    #[test]
    fn dimension_scores_bounded(findings in vec(arbitrary_finding(), 0..500)) {
        let dims = compute_dimension_scores(&findings, &Config::default());
        for (name, score) in &dims {
            prop_assert!(
                *score >= 0.0 && *score <= 100.0,
                "Dimension {} has score {} out of bounds",
                name, score
            );
        }
    }

    /// Adding more findings never increases any score.
    #[test]
    fn more_findings_lower_score(
        base_findings in vec(arbitrary_finding(), 0..100),
        extra_findings in vec(arbitrary_finding(), 1..50),
    ) {
        let base_scores = compute_health_breakdown(
            &base_findings, ScoreMode::Lenient, &Config::default()
        );
        let mut all_findings = base_findings;
        all_findings.extend(extra_findings);
        let more_scores = compute_health_breakdown(
            &all_findings, ScoreMode::Lenient, &Config::default()
        );
        // Note: score can stay same or decrease, never increase
        prop_assert!(
            more_scores.overall_score <= base_scores.overall_score + 0.001,
            "Score increased: {} -> {}",
            base_scores.overall_score, more_scores.overall_score
        );
    }
}
```

---

## 6. Benchmark Tests (criterion)

### 6.1 Benchmark Suite

```rust
use criterion::{criterion_group, criterion_main, Criterion, BenchmarkId};

fn scoring_benchmarks(c: &mut Criterion) {
    let small = load_golden_findings("benches/fixtures/findings_100.json");
    let medium = load_golden_findings("benches/fixtures/findings_1000.json");
    let large = load_golden_findings("benches/fixtures/findings_10000.json");

    let mut group = c.benchmark_group("scoring");
    for (name, findings) in [("100", &small), ("1000", &medium), ("10000", &large)] {
        group.bench_with_input(
            BenchmarkId::new("compute_health_breakdown", name),
            findings,
            |b, findings| {
                b.iter(|| {
                    compute_health_breakdown(findings, ScoreMode::Lenient, &Config::default())
                })
            },
        );
    }
    group.finish();
}

fn state_benchmarks(c: &mut Criterion) {
    let state_json = std::fs::read_to_string("benches/fixtures/state_50k.json").unwrap();

    c.bench_function("state_load_50k", |b| {
        b.iter(|| StateModel::from_json_str(&state_json))
    });

    let state: StateModel = serde_json::from_str(&state_json).unwrap();
    c.bench_function("state_save_50k", |b| {
        let dir = tempfile::tempdir().unwrap();
        b.iter(|| state.save_to_path(dir.path().join("state.json")))
    });
}

fn work_queue_benchmarks(c: &mut Criterion) {
    let state = load_golden_state("benches/fixtures/state_50k.json");

    c.bench_function("work_queue_build_50k", |b| {
        b.iter(|| build_work_queue(&state, &QueueOptions::default()))
    });
}

fn duplicate_detection_benchmarks(c: &mut Criterion) {
    let functions = load_functions("benches/fixtures/functions_5000.json");

    c.bench_function("duplicate_detection_5k", |b| {
        b.iter(|| detect_duplicates(&functions, &DupeOptions::default()))
    });
}

fn merge_scan_benchmarks(c: &mut Criterion) {
    let state = load_golden_state("benches/fixtures/state_50k.json");
    let findings = load_golden_findings("benches/fixtures/findings_10000.json");

    c.bench_function("merge_scan_10k_into_50k", |b| {
        b.iter_batched(
            || state.clone(),
            |mut state| merge_scan(&mut state, findings.clone(), &MergeScanOptions::default()),
            criterion::BatchSize::SmallInput,
        )
    });
}

criterion_group!(
    benches,
    scoring_benchmarks,
    state_benchmarks,
    work_queue_benchmarks,
    duplicate_detection_benchmarks,
    merge_scan_benchmarks,
);
criterion_main!(benches);
```

### 6.2 Performance Targets

| Operation | Input Size | Target | Hard Limit |
|-----------|-----------|--------|------------|
| `compute_health_breakdown` | 100 findings | <0.5ms | 2ms |
| `compute_health_breakdown` | 1,000 findings | <2ms | 5ms |
| `compute_health_breakdown` | 10,000 findings | <10ms | 25ms |
| `StateModel::load` | 50,000 findings | <100ms | 250ms |
| `StateModel::save` | 50,000 findings | <100ms | 250ms |
| `build_work_queue` | 50,000 findings | <50ms | 100ms |
| `detect_duplicates` | 5,000 functions | <1s | 3s |
| `merge_scan` | 10,000 into 50,000 | <200ms | 500ms |
| `auto_cluster` | 1,000 findings | <50ms | 200ms |
| `compute_narrative` | 50,000 findings | <100ms | 300ms |

### 6.3 Regression Detection

Benchmarks run in CI on every PR. A performance regression of >15% on any
target triggers a CI warning. A regression of >50% fails the build.

Configuration in `criterion.toml`:
```toml
[output]
significance_level = 0.05
noise_threshold = 0.02
```

---

## 7. CI Pipeline

### 7.1 GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Test Suite

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  CARGO_TERM_COLOR: always
  RUSTFLAGS: "-D warnings"

jobs:
  # Fast checks: formatting, clippy, compile
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy
      - run: cargo fmt --all -- --check
      - run: cargo clippy --workspace --all-targets -- -D warnings

  # Unit + integration tests
  test:
    runs-on: ubuntu-latest
    needs: check
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - run: cargo test --workspace
      - run: cargo test --workspace --features tree-sitter

  # Cross-validation tests (require Python)
  cross-validation:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -e .  # Install Python desloppify
      - run: cargo test --workspace -- --ignored

  # Benchmarks (performance regression detection)
  bench:
    runs-on: ubuntu-latest
    needs: test
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - run: cargo bench --workspace -- --output-format bencher
        # Compare against main branch baseline

  # Coverage
  coverage:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          components: llvm-tools-preview
      - uses: taiki-e/install-action@cargo-llvm-cov
      - run: cargo llvm-cov --workspace --lcov --output-path lcov.info
      - name: Check coverage threshold
        run: |
          COVERAGE=$(cargo llvm-cov --workspace --summary-only 2>&1 | grep -oP '\d+\.\d+%' | head -1 | tr -d '%')
          echo "Coverage: ${COVERAGE}%"
          if (( $(echo "$COVERAGE < 80.0" | bc -l) )); then
            echo "::error::Coverage ${COVERAGE}% is below 80% threshold"
            exit 1
          fi
      - uses: codecov/codecov-action@v4
        with:
          files: lcov.info

  # Snapshot tests (update check)
  snapshots:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - run: cargo insta test --workspace --review
      - name: Check for pending snapshot updates
        run: |
          if cargo insta test --workspace 2>&1 | grep -q "pending"; then
            echo "::error::Snapshot tests have pending updates. Run 'cargo insta review' locally."
            exit 1
          fi
```

### 7.2 CI Matrix

| Job | Trigger | Duration Target | Blocks Merge |
|-----|---------|----------------|-------------|
| `check` | All PRs | <2 min | Yes |
| `test` | All PRs | <10 min | Yes |
| `cross-validation` | All PRs | <15 min | Yes |
| `bench` | PRs only | <10 min | Warning only (>15% regression) |
| `coverage` | All PRs | <15 min | Yes (if <80%) |
| `snapshots` | All PRs | <5 min | Yes |

### 7.3 Local Development Commands

```bash
# Run all fast tests
cargo test --workspace

# Run with cross-validation (requires Python)
cargo test --workspace -- --ignored

# Run benchmarks
cargo bench --workspace

# Check coverage locally
cargo llvm-cov --workspace --html --open

# Review snapshot changes
cargo insta test --workspace --review

# Run a specific crate's tests
cargo test -p genesis-deslop-engine

# Run a specific test by name
cargo test -p genesis-deslop-engine test_scoring_empty_findings
```

---

## 8. Test Utilities Module

### 8.1 Location

```
crates/genesis-deslop-test-utils/
├── Cargo.toml
└── src/
    ├── lib.rs
    ├── generators.rs      # proptest Arbitrary implementations
    ├── golden.rs           # Golden file loading and comparison
    ├── python_bridge.rs    # Python cross-validation subprocess
    ├── fixtures.rs         # Sample project creation
    └── assertions.rs       # Custom assertion helpers
```

This is a workspace-internal crate, `publish = false`, used only as a
`[dev-dependency]` by other crates.

### 8.2 API Reference

#### generators.rs

```rust
/// Generates an arbitrary Finding with valid field combinations.
pub fn arbitrary_finding() -> impl Strategy<Value = Finding>;

/// Generates an arbitrary Finding with a specific status.
pub fn arbitrary_finding_with_status(status: Status) -> impl Strategy<Value = Finding>;

/// Generates an arbitrary StateModel with 0..max_findings findings.
pub fn arbitrary_state() -> impl Strategy<Value = StateModel>;

/// Generates an arbitrary StateModel with exactly N findings.
pub fn arbitrary_state_with_count(n: usize) -> impl Strategy<Value = StateModel>;

/// Generates an arbitrary Config with valid field ranges.
pub fn arbitrary_config() -> impl Strategy<Value = Config>;

/// Generates an arbitrary PlanModel.
pub fn arbitrary_plan() -> impl Strategy<Value = PlanModel>;

/// Generates a vector of FunctionInfo for duplicate detection tests.
pub fn arbitrary_functions(max: usize) -> impl Strategy<Value = Vec<FunctionInfo>>;
```

#### golden.rs

```rust
/// Loads a golden file and deserializes it.
pub fn load_golden_file<T: DeserializeOwned>(path: &str) -> T;

/// Loads golden findings from a JSON file.
pub fn load_golden_findings(path: &str) -> Vec<Finding>;

/// Loads golden state from a JSON file.
pub fn load_golden_state(path: &str) -> StateModel;

/// Loads golden plan from a JSON file.
pub fn load_golden_plan(path: &str) -> PlanModel;

/// Asserts that two golden file outputs match, with a detailed diff on failure.
pub fn assert_golden_match<T: Serialize + PartialEq + std::fmt::Debug>(
    actual: T,
    expected: T,
    test_name: &str,
);

/// Updates a golden file with new expected output (for `--update` mode).
pub fn update_golden_file<T: Serialize>(path: &str, value: &T);
```

#### python_bridge.rs

```rust
/// Runs a Python function from the desloppify reference and returns JSON output.
/// Panics if Python 3.12+ is not available.
pub fn run_python_reference(function: &str, input: &serde_json::Value) -> serde_json::Value;

/// Checks if Python cross-validation is available in the current environment.
pub fn python_available() -> bool;

/// Runs Python scoring and returns a ScoreBundle-compatible JSON value.
pub fn python_compute_scores(
    findings: &[Finding],
    mode: ScoreMode,
) -> serde_json::Value;
```

#### fixtures.rs

```rust
/// Creates a temporary directory with a sample TypeScript project.
/// Returns a TempDir that cleans up on drop.
pub fn sample_typescript_project() -> TempDir;

/// Creates a temporary directory with a sample Python project.
pub fn sample_python_project() -> TempDir;

/// Creates a temporary directory with a sample Rust project.
pub fn sample_rust_project() -> TempDir;

/// Creates a temporary directory with a mixed-language project.
pub fn sample_mixed_project() -> TempDir;

/// Creates a temporary directory with a known-bad project (all detector patterns).
pub fn sample_project_all_patterns() -> TempDir;

/// Creates a state file in the given directory with the specified findings.
pub fn create_state_file(dir: &Path, findings: &[Finding]) -> PathBuf;

/// Creates a config file in the given directory.
pub fn create_config_file(dir: &Path, config: &Config) -> PathBuf;
```

#### assertions.rs

```rust
/// Asserts two f64 scores are equal within tolerance.
/// Provides detailed error message on failure.
pub fn assert_scores_equal(actual: f64, expected: f64, tolerance: f64);

/// Asserts two ScoreBundle values are equal within tolerance.
pub fn assert_score_bundles_equal(
    actual: &ScoreBundle,
    expected: &ScoreBundle,
    tolerance: f64,
);

/// Asserts that a finding list matches expected IDs in order.
pub fn assert_finding_ids_eq(actual: &[Finding], expected_ids: &[&str]);

/// Asserts that a work queue matches expected ordering by ID.
pub fn assert_queue_order(actual: &[WorkItem], expected_ids: &[&str]);

/// Asserts that output contains no ANSI escape codes.
pub fn assert_no_ansi(output: &str);

/// Asserts that a JSON value matches the insta snapshot.
pub fn assert_json_snapshot(name: &str, value: &serde_json::Value);
```

### 8.3 Usage in Crate Tests

```rust
// In crates/genesis-deslop-engine/tests/scoring_tests.rs

use genesis_deslop_test_utils::{
    golden::load_golden_findings,
    assertions::assert_scores_equal,
    generators::arbitrary_finding,
};

#[test]
fn test_scoring_matches_golden() {
    let findings = load_golden_findings("tests/golden/findings/sample_findings.json");
    let expected = load_golden_findings("tests/golden/scoring/expected_simple.json");
    let scores = compute_health_breakdown(&findings, ScoreMode::Lenient, &Config::default());
    assert_scores_equal(scores.overall_score, expected["overall_score"], 0.001);
}
```

---

## Appendix A: Test Count Estimates

| Crate | Unit | Integration | Property | Cross-Val | Snapshot | Total |
|-------|------|-------------|----------|-----------|----------|-------|
| `genesis-deslop-core` | ~60 | ~15 | ~5 | 0 | 0 | ~80 |
| `genesis-deslop-engine` | ~250 | ~40 | ~15 | ~10 | 0 | ~315 |
| `genesis-deslop-lang` | ~120 | ~60 | ~5 | 0 | 0 | ~185 |
| `genesis-deslop-intel` | ~80 | ~20 | ~5 | 0 | 0 | ~105 |
| `genesis-deslop-cli` | ~30 | ~25 | 0 | 0 | ~15 | ~70 |
| **Total** | **~540** | **~160** | **~30** | **~10** | **~15** | **~755** |

## Appendix B: Test Priority Order

Tests should be implemented in this order, matching the crate migration strategy
from ARCHITECTURE.md:

1. **genesis-deslop-core** -- enums, config, registry (foundation types)
2. **genesis-deslop-engine/scoring** -- the mathematical core (highest risk)
3. **genesis-deslop-engine/state** -- state persistence and merge
4. **Cross-validation harness** -- Python bridge infrastructure
5. **genesis-deslop-engine/work_queue** -- queue ranking
6. **genesis-deslop-engine/plan** -- plan operations
7. **genesis-deslop-lang** -- one full-depth language (Python), then expand
8. **genesis-deslop-engine/detectors** -- one detector at a time with golden files
9. **genesis-deslop-intel** -- review and narrative
10. **genesis-deslop-cli** -- integration and snapshot tests last

## Appendix C: Detector Test Matrix Template

For each new detector implementation, create tests following this template:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use genesis_deslop_test_utils::*;

    // --- Positive case ---
    #[test]
    fn detects_known_pattern() {
        let source = include_str!("../testdata/{detector}_positive.{ext}");
        let findings = detect(source, &DetectorOptions::default());
        assert!(!findings.is_empty(), "Should detect pattern in positive case");
        assert_eq!(findings[0].detector, "{detector}");
    }

    // --- Negative case ---
    #[test]
    fn clean_code_no_findings() {
        let source = include_str!("../testdata/{detector}_negative.{ext}");
        let findings = detect(source, &DetectorOptions::default());
        assert!(findings.is_empty(), "Should not detect in clean code");
    }

    // --- Threshold boundary ---
    #[test]
    fn at_threshold_no_finding() {
        let source = include_str!("../testdata/{detector}_at_threshold.{ext}");
        let findings = detect(source, &DetectorOptions::default());
        assert!(findings.is_empty(), "At threshold should not trigger");
    }

    #[test]
    fn above_threshold_triggers() {
        let source = include_str!("../testdata/{detector}_above_threshold.{ext}");
        let findings = detect(source, &DetectorOptions::default());
        assert!(!findings.is_empty(), "Above threshold should trigger");
    }

    // --- Zone exclusion ---
    #[test]
    fn excluded_zone_skipped() {
        let source = include_str!("../testdata/{detector}_positive.{ext}");
        let opts = DetectorOptions { excluded_zones: vec![Zone::Test], ..Default::default() };
        let findings = detect_with_zone(source, Zone::Test, &opts);
        assert!(findings.is_empty(), "Should skip excluded zones");
    }

    // --- Golden file ---
    #[test]
    fn matches_golden_output() {
        let input = load_golden_file("tests/golden/detectors/{detector}/input.json");
        let expected = load_golden_file("tests/golden/detectors/{detector}/expected.json");
        let actual = detect_from_json(input);
        assert_golden_match(actual, expected, "{detector}_golden");
    }
}
```

---

*This document is the test specification for genesis-deslop. All test
implementations must conform to these patterns and coverage targets. Update this
document when adding new detectors, scoring rules, or test infrastructure.*
