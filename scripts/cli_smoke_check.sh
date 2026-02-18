#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASELINE_DIR="$ROOT_DIR/tests/snapshots/cli_smoke"
TMP_DIR="$(mktemp -d)"
TMP_NORM_DIR="$(mktemp -d)"
BASE_NORM_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR" "$TMP_NORM_DIR" "$BASE_NORM_DIR"
}
trap cleanup EXIT

if [[ ! -d "$BASELINE_DIR" ]]; then
  echo "Baseline directory not found: $BASELINE_DIR" >&2
  exit 1
fi

"$ROOT_DIR/scripts/cli_smoke_snapshot.sh" "$TMP_DIR" >/dev/null

normalize_snapshot() {
  local src_file="$1"
  local dst_file="$2"
  sed -E \
    -e 's/Last scan: [0-9T:+.-]+/Last scan: <TIMESTAMP>/g' \
    "$src_file" >"$dst_file"
}

status=0
for filename in scan.txt status.txt review_prepare.txt; do
  normalize_snapshot "$BASELINE_DIR/$filename" "$BASE_NORM_DIR/$filename"
  normalize_snapshot "$TMP_DIR/$filename" "$TMP_NORM_DIR/$filename"
  if ! diff -u "$BASE_NORM_DIR/$filename" "$TMP_NORM_DIR/$filename"; then
    echo "Smoke snapshot mismatch: $filename" >&2
    status=1
  fi
done

if [[ $status -eq 0 ]]; then
  echo "CLI smoke snapshots match baseline."
fi

exit $status
