#!/usr/bin/env bash
set -euo pipefail

CACHE_ROOT="${BENCHMARK_CACHE_ROOT:-$HOME/.cache/harbor-rsi}"
SOURCE_DIR="${WEBSHOP_SOURCE_ROOT:-$CACHE_ROOT/sources/webshop}"
DATA_DIR="$SOURCE_DIR/data"
MIRROR="https://huggingface.co/datasets/YWZBrandon/webshop-data/resolve/ce990fff5aee388db2706f07820c578ab68e0453"
mkdir -p "$DATA_DIR"

download() {
  local name="$1" expected="$2" target="$DATA_DIR/$1" temporary="$DATA_DIR/$1.part"
  if [[ -s "$target" ]] && printf '%s  %s\n' "$expected" "$target" | sha256sum -c -; then
    return
  fi
  rm -f "$target"
  curl --fail --location --retry 8 --continue-at - \
    --output "$temporary" "$MIRROR/$name?download=true"
  printf '%s  %s\n' "$expected" "$temporary" | sha256sum -c -
  mv "$temporary" "$target"
}

download items_shuffle.json 2ef591d65df3af89e972ab72468eb82cbf124d876552d9f3678667edd620a6c8
download items_ins_v2.json 1d36af476bdb8f82a5da62bd8acdabe54cd8de2fa84010d37da5c4890feb447e
[[ -s "$DATA_DIR/items_human_ins.json" ]] || {
  echo "Missing items_human_ins.json; run fetch-webshop-source.sh first" >&2
  exit 1
}
sha256sum "$DATA_DIR/items_shuffle.json" "$DATA_DIR/items_ins_v2.json" "$DATA_DIR/items_human_ins.json"
