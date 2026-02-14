---
name: desloppify
description: >
  Codebase health scanner and technical debt tracker. Use when the user asks
  about code quality, technical debt, dead code, large files, god classes,
  duplicate functions, code smells, naming issues, import cycles, or coupling
  problems. Also use when asked for a health score, what to fix next, or to
  create a cleanup plan. Supports TypeScript/React and Python.
allowed-tools: Bash(desloppify *)
---

# Desloppify — Codebase Health Scanner

## Goal

**Your goal is to get strict scores as high as possible.** Strict scoring counts wontfix items as failures — it's the true measure of codebase health. After every scan, ALWAYS share with the user:
1. **Overall health** (lenient and strict)
2. **All dimension scores** (lenient and strict) in a table
3. **Review dimension scores** (lenient and strict) — these are 0% until reviews are run

Never skip the scores. The user needs to see progress.

## Prerequisite

!`command -v desloppify >/dev/null 2>&1 && echo "desloppify: installed" || echo "NOT INSTALLED — run: pip install --upgrade git+https://github.com/peteromallet/desloppify.git"`

## Workflow

1. **Scan**: `desloppify scan --path src/` — detect issues, update state, show diff
2. **Act on scan output**: The scan ends with "INSTRUCTIONS FOR AGENTS". **Execute the recommended strategy immediately.** Do NOT summarize findings or ask what to work on — just start fixing.
3. **Read query.json**: After ANY command, read `.desloppify/query.json` for structured narrative context (phase, actions, reminders). Follow the `actions` list — it has exact commands.
4. **Fix → Resolve → Rescan**: Fix the issue, `desloppify resolve fixed "<id>"`, rescan to verify.

## Commands

```bash
desloppify scan --path src/               # scan, update state, show diff
desloppify status                          # health score + tier breakdown
desloppify show <pattern>                  # findings by file, dir, detector, or ID
desloppify next --count 5                  # highest-priority open findings
desloppify plan                            # prioritized markdown plan
desloppify resolve fixed "<pattern>"       # mark as fixed
desloppify resolve wontfix "<pattern>" --note "reason"
desloppify fix <fixer> --dry-run           # auto-fix (always dry-run first)
desloppify move <src> <dst> --dry-run      # move file + update imports
desloppify detect <name> --path src/       # run one detector raw
desloppify zone show                       # list files with zones
desloppify zone set <path> production      # override a misclassified zone
```

## Narrative Context (query.json)

After every command, `.desloppify/query.json` has a `"narrative"` key. Use it:

- **`actions`**: Prioritized next steps with exact commands. Follow the `type`:
  - `auto_fix` → run `fix` command (dry-run first)
  - `reorganize` → use `move` for file restructuring
  - `refactor` → manual changes needed, read the flagged file
  - `debt_review` → review wontfix items, some may be worth fixing now
- **`phase`**: Guides your framing (first_scan, early_momentum, middle_grind, refinement, maintenance, stagnation, regression)
- **`reminders`**: Surface these to the user
- **`debt`**: Wontfix gap and trend direction

### Phase Behavior
- `first_scan` / `early_momentum`: Push toward clearing T1/T2 with auto-fixers
- `middle_grind`: T3/T4 dominate — push structural refactors
- `refinement` / `maintenance` (90+): Per-dimension tuning, watch for regressions
- `stagnation`: Score stuck — surface wontfix debt, suggest revisiting decisions
- `regression`: Score dropped — investigate cascade effects

### Stay Honest
- When wontfix count grows, call it out
- When a dimension is stuck 3+ scans, suggest a different approach
- When auto-fixers exist for open findings, ask why they haven't been run
- Always surface the strict-lenient gap as "wontfix debt"

## Tiers

| Tier | Meaning | Action |
|------|---------|--------|
| T1 | Auto-fixable | `desloppify fix <fixer> --dry-run` then apply |
| T2 | Quick manual fix | Fix directly, then resolve |
| T3 | Needs judgment | Review, fix or wontfix with note |
| T4 | Major refactor | Decompose, plan before acting |

## Auto-Fixers (TypeScript only)

`unused-imports`, `unused-vars`, `unused-params`, `debug-logs`, `dead-exports`, `dead-useeffect`, `empty-if-chain`. Always `--dry-run` first. Python has no auto-fixers.

## Zones

Files are classified by path: **production** (scored), **test**, **config**, **generated**, **vendor** (not scored), **script** (scored, limited detectors). Use `zone set` to fix misclassifications.

## Tips

- `--skip-slow` skips duplicate detection (faster iteration)
- `--lang python` or `--lang typescript` to force language
- Score can temporarily drop after fixes (cascade effects are normal)
- Note false positives or missing detectors — suggest the user report at https://github.com/peteromallet/desloppify/issues
