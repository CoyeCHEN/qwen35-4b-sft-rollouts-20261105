#!/usr/bin/env bash
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE_ROOT="${BENCHMARK_CACHE_ROOT:-$HOME/.cache/harbor-rsi}"
OUTPUT_ROOT="${WEBSHOP_DATASET_ROOT:-$CACHE_ROOT/datasets/webshop/official-test-500-100-actions}"
FULL_ROOT="${WEBSHOP_FULL_ROOT:-$CACHE_ROOT/sources/webshop-full}"
PYTHON="${WEBSHOP_ADAPTER_PYTHON:-python3}"
IMAGE="${WEBSHOP_FULL_IMAGE:-openharness-webshop:full-64fa2a5-actionlimit-v1}"
GOALS=()
for index in $(seq 0 499); do
  GOALS+=(--goal-index "$index")
done

export PYTHONPATH="$EVAL_ROOT/webshop/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m webshop_harbor.adapter \
  --output-root "$OUTPUT_ROOT" --image "$IMAGE" --max-steps 100 \
  --product-set full --full-root "$FULL_ROOT" "${GOALS[@]}" "$@"
