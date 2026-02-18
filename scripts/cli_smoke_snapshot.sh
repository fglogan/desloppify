#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE_DIR="$ROOT_DIR/tests/fixtures/cli_smoke_project"
SNAPSHOT_DIR="${1:-$ROOT_DIR/tests/snapshots/cli_smoke}"
STATE_FILE="$SNAPSHOT_DIR/state-python.json"
QUERY_FILE="$ROOT_DIR/.desloppify/query.json"

mkdir -p "$SNAPSHOT_DIR"
rm -f "$STATE_FILE" "$SNAPSHOT_DIR"/*.txt "$SNAPSHOT_DIR"/*.json

export NO_COLOR=1
export PYTHONPATH="$ROOT_DIR"

python3 -m desloppify --lang python scan \
  --path "$FIXTURE_DIR/src" \
  --state "$STATE_FILE" \
  --no-badge \
  >"$SNAPSHOT_DIR/scan.txt" 2>&1

python3 -m desloppify --lang python status \
  --state "$STATE_FILE" \
  >"$SNAPSHOT_DIR/status.txt" 2>&1

python3 -m desloppify --lang python review --prepare \
  --path "$FIXTURE_DIR/src" \
  --state "$STATE_FILE" \
  >"$SNAPSHOT_DIR/review_prepare.txt" 2>&1

if [[ -f "$QUERY_FILE" ]]; then
  cp "$QUERY_FILE" "$SNAPSHOT_DIR/query.json"
fi

echo "Smoke snapshots written to: $SNAPSHOT_DIR"
