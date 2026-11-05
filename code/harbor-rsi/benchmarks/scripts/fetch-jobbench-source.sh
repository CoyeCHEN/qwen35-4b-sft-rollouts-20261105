#!/usr/bin/env bash
set -euo pipefail

CACHE_ROOT="${BENCHMARK_CACHE_ROOT:-$HOME/.cache/harbor-rsi}"
SOURCE_ROOT="${JOBBENCH_SOURCE_ROOT:-$CACHE_ROOT/sources/job-bench-eval}"
REPO="${JOBBENCH_SOURCE_REPO:-https://github.com/Job-Bench/job-bench-eval.git}"
REVISION="${JOBBENCH_DATA_REVISION:-}"

mkdir -p "$(dirname "$SOURCE_ROOT")"
if [[ ! -d "$SOURCE_ROOT/.git" ]]; then
  git clone "$REPO" "$SOURCE_ROOT"
else
  git -C "$SOURCE_ROOT" pull --ff-only
fi

ARGS=()
if [[ -n "$REVISION" ]]; then
  ARGS+=(--revision "$REVISION")
fi

cd "$SOURCE_ROOT"
JOBBENCH_DATASET_ONLY=1 ./setup.sh "${ARGS[@]}"
printf 'JobBench source ready at %s\n' "$SOURCE_ROOT"
