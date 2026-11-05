#!/usr/bin/env bash
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE_ROOT="${BENCHMARK_CACHE_ROOT:-$HOME/.cache/harbor-rsi}"
BASE_IMAGE="${WEBSHOP_BASE_IMAGE:-openharness-webshop:small-64fa2a5-actionlimit-v2}"
IMAGE="${WEBSHOP_FULL_IMAGE:-openharness-webshop:full-64fa2a5-actionlimit-v1}"
CONTEXT="$(mktemp -d "$CACHE_ROOT/build/webshop-full-runtime-XXXXXXXX")"
trap 'rm -rf "$CONTEXT"' EXIT

docker image inspect "$BASE_IMAGE" >/dev/null 2>&1 || {
  echo "Missing base image $BASE_IMAGE; run build-webshop-image.sh first" >&2
  exit 1
}
mkdir -p "$CONTEXT/runtime"
cp "$EVAL_ROOT/webshop/runtime/service.py" "$CONTEXT/runtime/service.py"
cp "$EVAL_ROOT/webshop/runtime/full_environment.py" "$CONTEXT/runtime/full_environment.py"
cp "$EVAL_ROOT/webshop/runtime/build_full_index.py" "$CONTEXT/runtime/build_full_index.py"
cp "$EVAL_ROOT/webshop/images/Dockerfile.webshop-full" "$CONTEXT/Dockerfile"
docker build --build-arg "BASE_IMAGE=$BASE_IMAGE" -t "$IMAGE" "$CONTEXT"
docker image inspect "$IMAGE" --format '{{.Id}} {{.Size}}'
