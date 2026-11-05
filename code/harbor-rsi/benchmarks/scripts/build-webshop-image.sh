#!/usr/bin/env bash
set -euo pipefail

EVAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE_ROOT="${BENCHMARK_CACHE_ROOT:-$HOME/.cache/harbor-rsi}"
SOURCE_DIR="${WEBSHOP_SOURCE_ROOT:-$CACHE_ROOT/sources/webshop}"
mkdir -p "$CACHE_ROOT/build"
CONTEXT_DIR="$(mktemp -d "$CACHE_ROOT/build/webshop-actionlimit-XXXXXXXX")"
IMAGE="${WEBSHOP_IMAGE:-openharness-webshop:small-64fa2a5-actionlimit-v2}"
COMMIT="64fa2a5c15c7daa698b9ac93f5bb5437b634c9bd"

[[ "$(git -C "$SOURCE_DIR" rev-parse HEAD)" == "$COMMIT" ]] || {
  echo "WebShop source is not pinned to $COMMIT; run fetch-webshop-source.sh" >&2
  exit 1
}
for file in items_shuffle_1000.json items_ins_v2_1000.json items_human_ins.json; do
  [[ -s "$SOURCE_DIR/data/$file" ]] || {
    echo "Missing $SOURCE_DIR/data/$file; run fetch-webshop-source.sh" >&2
    exit 1
  }
done

mkdir -p "$CONTEXT_DIR/webshop/data" "$CONTEXT_DIR/runtime"
git -C "$SOURCE_DIR" archive "$COMMIT" | tar -x -C "$CONTEXT_DIR/webshop"
cp "$SOURCE_DIR/data/items_shuffle_1000.json" "$CONTEXT_DIR/webshop/data/"
cp "$SOURCE_DIR/data/items_ins_v2_1000.json" "$CONTEXT_DIR/webshop/data/"
cp "$SOURCE_DIR/data/items_human_ins.json" "$CONTEXT_DIR/webshop/data/"
cp "$EVAL_ROOT/webshop/runtime/service.py" "$CONTEXT_DIR/runtime/service.py"
cp "$EVAL_ROOT/webshop/runtime/build_index.py" "$CONTEXT_DIR/runtime/build_index.py"
cp "$EVAL_ROOT/webshop/images/Dockerfile.webshop" "$CONTEXT_DIR/Dockerfile"

docker build -t "$IMAGE" "$CONTEXT_DIR"
docker image inspect "$IMAGE" --format '{{.Id}} {{.Size}}'
