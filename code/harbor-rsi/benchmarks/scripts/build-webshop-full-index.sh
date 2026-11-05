#!/usr/bin/env bash
set -euo pipefail

CACHE_ROOT="${BENCHMARK_CACHE_ROOT:-$HOME/.cache/harbor-rsi}"
SOURCE_DIR="${WEBSHOP_SOURCE_ROOT:-$CACHE_ROOT/sources/webshop}"
FULL_ROOT="${WEBSHOP_FULL_ROOT:-$CACHE_ROOT/sources/webshop-full}"
IMAGE="${WEBSHOP_FULL_IMAGE:-openharness-webshop:full-64fa2a5-actionlimit-v1}"
OVERWRITE=()
[[ "${WEBSHOP_REBUILD_FULL_INDEX:-0}" == 1 ]] && OVERWRITE=(--overwrite)
RESUME=()
if [[ -s "$FULL_ROOT/manifest.json" && "${WEBSHOP_REBUILD_FULL_INDEX:-0}" != 1 ]]; then
  echo "Full WebShop assets already exist at $FULL_ROOT"
  exit 0
fi
if [[ -s "$FULL_ROOT/products.sqlite" && "${WEBSHOP_REBUILD_FULL_INDEX:-0}" != 1 ]]; then
  RESUME=(--resume)
fi

for file in items_shuffle.json items_ins_v2.json items_human_ins.json; do
  [[ -s "$SOURCE_DIR/data/$file" ]] || {
    echo "Missing $SOURCE_DIR/data/$file; run fetch-webshop-full-data.sh" >&2
    exit 1
  }
done
docker image inspect "$IMAGE" >/dev/null 2>&1 || {
  echo "Missing $IMAGE; run build-webshop-full-image.sh" >&2
  exit 1
}
mkdir -p "$FULL_ROOT"
docker run --rm --memory 10g \
  -v "$SOURCE_DIR/data:/input:ro" \
  -v "$FULL_ROOT:/output" \
  --entrypoint python "$IMAGE" /opt/webshop/build_full_index.py \
  --products /input/items_shuffle.json \
  --attributes /input/items_ins_v2.json \
  --human /input/items_human_ins.json \
  --output /output --threads 1 "${OVERWRITE[@]}" "${RESUME[@]}"
