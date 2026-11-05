#!/usr/bin/env bash
set -euo pipefail

CACHE_ROOT="${BENCHMARK_CACHE_ROOT:-$HOME/.cache/harbor-rsi}"
SOURCE_DIR="${WEBSHOP_SOURCE_ROOT:-$CACHE_ROOT/sources/webshop}"
COMMIT="64fa2a5c15c7daa698b9ac93f5bb5437b634c9bd"
DATA_DIR="$SOURCE_DIR/data"

if [[ ! -d "$SOURCE_DIR/.git" ]]; then
  git clone https://github.com/princeton-nlp/WebShop.git "$SOURCE_DIR"
fi
git -C "$SOURCE_DIR" fetch origin master
git -C "$SOURCE_DIR" checkout --detach "$COMMIT"
mkdir -p "$DATA_DIR"

docker run --rm -v "$DATA_DIR:/data" python:3.11-slim sh -ceu '
python -m pip install --no-cache-dir gdown
mirror=https://huggingface.co/datasets/YWZBrandon/webshop-data/resolve/ce990fff5aee388db2706f07820c578ab68e0453
download() {
  name=$1
  drive_id=$2
  test -s "/data/$name" && return
  if ! gdown "$drive_id" -O "/data/$name"; then
    rm -f "/data/$name"
    python -c "import urllib.request; urllib.request.urlretrieve(\"$mirror/$name?download=true\", \"/data/$name\")"
  fi
  test -s "/data/$name"
}
download items_shuffle_1000.json 1EgHdxQ_YxqIQlvvq5iKlCrkEKR6-j0Ib
download items_ins_v2_1000.json 1IduG0xl544V_A_jv3tHXC0kyFi7PnyBu
download items_human_ins.json 14Kb5SPBk_jfdLZ_CDBNitW98QLDlKR5O
'

printf 'WebShop source: %s\n' "$SOURCE_DIR"
git -C "$SOURCE_DIR" rev-parse HEAD
sha256sum "$DATA_DIR"/*.json
