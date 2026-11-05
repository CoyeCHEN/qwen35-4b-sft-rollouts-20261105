#!/bin/bash
set -euo pipefail
umask 027
R=/ssd/chenkeyi/qwen35-sft-772-20261101
D=/data/chenkeyi/qwen35-sft-772-20261101/staging/assets17-r1
for ((i=0;i<720;i++)); do
 if test -f "$D/SEALED.json"; then break; fi
 sleep 5
done
test -f "$D/SEALED.json"
test ! -e "$R/assets/source17-r1"
rsync -a --stats "$D/" "$R/staging/source17-r1/"
python3 "$R/verify-transfer-r2.py" "$R/staging/source17-r1"
mv "$R/staging/source17-r1" "$R/assets/source17-r1"
"$R/assets/source17-r1/python/bin/python3.11" -m venv --without-pip "$R/env/train-r1"
rsync -a --stats "$R/assets/source17-r1/package-payload/" "$R/env/train-r1/lib/python3.11/site-packages/"
P="$R/env/train-r1/bin/python"
if test -f "$R/env/train-r1/lib/python3.11/site-packages/ninja/data/bin/ninja"; then
 ln -s ../lib/python3.11/site-packages/ninja/data/bin/ninja "$R/env/train-r1/bin/ninja"
fi
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "$P" "$R/check-runtime-r1.py"
