#!/bin/bash
set -euo pipefail
umask 027
R=/ssd/chenkeyi/qwen35-sft-772-20261101
P="$R/old-four-arm"
exec 9>/data/chenkeyi/qwen35-sft-772-20261101/control/sequence-writer.lock
flock -n 9
export PYTHONPATH="$P/source/repository"
export PATH="$R/env/train-r1/bin:$PATH"
export OPENHARNESS_SFT_WORKSPACE="$P"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export TMPDIR="$R/tmp" TORCH_EXTENSIONS_DIR="$R/cache/torch_extensions" TRITON_CACHE_DIR="$R/cache/triton"
export XDG_CACHE_HOME="$R/cache" HF_HOME="$R/cache/hf" TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
PY="$R/env/train-r1/bin/python"
"$PY" -m studies.qwen35_m2_full_causal.launch_arm --evidence "$P" --arm A --stop-after-checkpoint-2
"$PY" "$R/verify-old-arm-native-r1.py" A 2
"$PY" -m studies.qwen35_m2_full_causal.launch_arm --evidence "$P" --arm A --resume "$R/runs/old-four-arm/A/checkpoint-2"
"$PY" "$R/verify-old-arm-native-r1.py" A 530
for arm in B C D; do
 "$PY" -m studies.qwen35_m2_full_causal.launch_arm --evidence "$P" --arm "$arm"
 "$PY" "$R/verify-old-arm-native-r1.py" "$arm" 530
done
date -u +%FT%TZ > "$P/checks/FOUR_NATIVE_TRAINING_RUNS_COMPLETED"
