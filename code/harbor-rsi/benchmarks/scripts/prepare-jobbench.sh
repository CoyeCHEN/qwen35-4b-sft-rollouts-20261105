#!/usr/bin/env bash
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOBBENCH_ROOT="$EVAL_ROOT/jobbench"
CACHE_ROOT="${BENCHMARK_CACHE_ROOT:-$HOME/.cache/harbor-rsi}"
SOURCE_ROOT="${JOBBENCH_SOURCE_ROOT:?Set JOBBENCH_SOURCE_ROOT to the official JobBench source checkout}"
OUTPUT_ROOT="${JOBBENCH_DATASET_ROOT:-$CACHE_ROOT/datasets/jobbench-e2b}"
SPLIT="${JOBBENCH_SPLIT:-main}"
PYTHON="${JOBBENCH_PYTHON:-python3}"

case "$SPLIT" in
  main|easy) ;;
  *) echo "JOBBENCH_SPLIT must be main or easy, got: $SPLIT" >&2; exit 2 ;;
esac

export PYTHONPATH="$JOBBENCH_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$OUTPUT_ROOT"

"$PYTHON" -m jobbench_e2b.main \
  --source-root "$SOURCE_ROOT" \
  --output-root "$OUTPUT_ROOT" \
  --split "$SPLIT" \
  "$@"

"$PYTHON" "$JOBBENCH_ROOT/scripts/validate_dataset.py" \
  "$OUTPUT_ROOT/$SPLIT" --strict
