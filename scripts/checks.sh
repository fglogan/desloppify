#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR"

SOURCE_TARGETS=(
  "desloppify/commands/review_cmd.py"
  "desloppify/commands/review_prepare.py"
  "desloppify/commands/review_batches.py"
  "desloppify/commands/review_import.py"
  "desloppify/commands/review_runtime.py"
  "desloppify/commands/scan/scan_reporting_dimensions.py"
  "desloppify/commands/scan/scan_reporting_progress.py"
  "desloppify/commands/scan/scan_reporting_breakdown.py"
  "desloppify/commands/scan/scan_reporting_subjective_paths.py"
  "desloppify/cli_parser.py"
  "desloppify/cli_parser_groups.py"
)

TEST_TARGETS=(
  "tests/commands/test_cli.py"
  "tests/commands/fix/test_cmd_fix_review.py"
  "tests/core/test_subjective_integrity_direct.py"
  "tests/lang/common/test_lang_contract_validation.py"
  "tests/review/test_review_integrity_direct.py"
  "tests/scan/test_scan_workflow_wontfix_direct.py"
  "tests/review/test_review.py"
  "tests/scan/test_scan_reporting_direct.py"
  "tests/scoring/test_scoring.py"
  "tests/lang/common/test_import_boundaries.py"
)

ruff check --select F,B "${SOURCE_TARGETS[@]}" "${TEST_TARGETS[@]}"
mypy
./scripts/cli_smoke_check.sh
pytest -q "${TEST_TARGETS[@]}"
