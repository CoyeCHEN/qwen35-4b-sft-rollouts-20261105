#!/bin/bash
set -euo pipefail
R=/ssd/chenkeyi/qwen35-sft-772-20261101
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export TMPDIR="$R/tmp" TORCH_EXTENSIONS_DIR="$R/cache/torch_extensions" TRITON_CACHE_DIR="$R/cache/triton"
export XDG_CACHE_HOME="$R/cache" HF_HOME="$R/cache/hf" TOKENIZERS_PARALLELISM=false
export PYTHONPATH="$R/old-four-arm/source/repository"
export PATH="$R/env/train-r1/bin:$PATH"
flock /data/chenkeyi/qwen35-sft-772-20261101/control/training.lock "$R/env/train-r1/bin/python" -m torch.distributed.run --standalone --nproc_per_node=8 "$R/nccl8-r1.py"
