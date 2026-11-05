#!/usr/bin/env bash
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE_ROOT="${BENCHMARK_CACHE_ROOT:-$HOME/.cache/harbor-rsi}"
OUTPUT_ROOT="${WEBSHOP_DATASET_ROOT:-$CACHE_ROOT/datasets/webshop/comparison-100-actions}"
PYTHON="${WEBSHOP_ADAPTER_PYTHON:-python3}"

export PYTHONPATH="$EVAL_ROOT/webshop/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m webshop_harbor.adapter \
  --output-root "$OUTPUT_ROOT" \
  --image "${WEBSHOP_IMAGE:-openharness-webshop:small-64fa2a5-actionlimit-v2}" \
  --max-steps "${WEBSHOP_MAX_STEPS:-100}" \
  --product-set small \
  "$@"
