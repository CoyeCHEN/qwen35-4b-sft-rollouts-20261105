# TMax-2B 32K controlled study

This directory preserves the real TMax training and delivery implementation.
It does not own a Harness loop, a benchmark Provider, Task dispatch or scoring.
The matching controller is in
[Harbor-RSI](https://github.com/CoyeCHEN/harbor-rsi/tree/feat/tmax-remote-controller-20261024/examples/tmax32k).
Neither PR automatically upgrades the running study.

## Historical experiment identity

Eight full trainings and thirteen scalar NLL archives already exist. Do not
train or score them again merely to install this repository. Their weight,
configuration, data and archive identities are in `historical-*.json`.

| Stage | Training / validation calls | Updates | Supervised training tokens | Initial model |
|---|---:|---:|---:|---|
| Six M2 precision/LR arms | 743 / 29 | 186 each | 559108 each | Original M1-32K |
| M1 FP32 parameters/state | 5364 / 194 | 1341 | 18409013 | Original M0 |
| Paired M2 FP32, LR 5e-7 | 743 / 29 | 186 | 559108 | New M1 FP32 |

All use full parameters, length 32768, microbatch 1, accumulation 4, one epoch,
seed 42, fused AdamW, cosine, warmup 3%, decay .01, clip 1, SDPA, Liger fused
CE and gradient checkpointing. Exact per-arm settings override this summary.
The six M2 rates are 5e-7, 2e-6 and 1e-5 for each implementation. M1 uses 2e-6.
The original M1, M2-8K and M2-32K are separate historical models, not equivalent
arms assumed to share these settings.

P0 updates BF16 parameters with BF16 moments. P1 updates FP32 trainable master
parameters and moments under BF16 autocast. Embedding, normalization and
residual computation can differ: this is a comparison of two mixed precision
implementations, not a pure optimizer-dtype intervention. No best Agent claim
follows from teacher-state NLL. The M2 TB2.1 teacher data is same-task adaptation,
not clean unseen-task generalization. Its 29 validation calls come from only
three independent Tasks.

## Reproduce an explicitly authorized NEW run

Run GPU/model/large CPU commands on an allocated server, never a small WSL
observer. Supply the approved parquet, validation report, tokenizer/model
directory, original canonical data and frozen reader as external artifacts.
They are deliberately absent from Git. Do not replace data by a newer archive.

```bash
git clone https://github.com/CoyeCHEN/openharness-sft.git
cd openharness-sft
git checkout <REVIEWED_INTEGRATION_COMMIT>
python3.12 -m venv /srv/venvs/tmax-training
/srv/venvs/tmax-training/bin/pip install --extra-index-url https://download.pytorch.org/whl/cu128 -r studies/tmax32k/requirements-training.txt
python3 studies/tmax32k/prepare_arm.py \
  --arm M2-P0-L0-32K-seed42 --name M2-reproduction-explicit-id \
  --runtime /srv/tmax/new-training --stage /srv/tmax/new-training/training/M2-reproduction-explicit-id \
  --model /srv/approved/original-M1-32K/final \
  --data /srv/approved/M2-32K --report /srv/approved/validation.json
```

Preparation streams hashes, enforces original data identity, refuses historical
IDs/existing output, copies the versioned source, and freezes input/config/source
identity in the queue. Training still performs its own tokenizer/mask and dtype
checks. Preparation is not a training PASS. Obtain explicit GPU authority and
check actual UUID/UID/process occupancy before the following command. A file
lock is only cooperation within this study.

```bash
export TMAX_ABLATION_ROOT=/srv/tmax/new-training
export TMAX_GPU_LOCK_PREFIX=/srv/tmax/locks/gpu-
export TMAX_INFERENCE_PYTHON=/srv/venvs/inference/bin/python
export TMAX_SSD_ROOT=/srv/tmax/private-ssd
export TMAX_NFS_ROOTS='["/srv/approved-nfs/tmax-training"]'
export FINAL_STUDY_LEASE_UNTIL_UNIX=REPLACE_WITH_REAL_AUTHORIZED_EXPIRY
/srv/venvs/tmax-training/bin/python "$TMAX_ABLATION_ROOT/scripts/gpu_job.py" M2-reproduction-explicit-id REPLACE_WITH_ALLOCATED_GPU_UUID
```

The runner refuses source/config/data/model drift and a completed arm. Checkpoint
restoration verifies native tensors, tied weights, optimizer, scheduler and RNG
before the next real microbatch. Resume requires a reviewed checkpoint plan with
all file SHA values; do not invent a plan to restart a failed arm. SSD→NFS commits
occur after the Trainer exits and releases CUDA. Failed copies retain evidence
and the SSD source. Historical `sources/` files remain byte-for-byte pinned;
the wrapper applies the already validated native-save/AMP changes. Portability
changes here have CPU tests; they have not been used to retrain historical arms.

The deleted root `train.py` and `configs/tmax2b*` were unused external-Trainer
stubs. This study loads only its SHA-pinned `sources/original-train.py` and
`original-sft_data.py`, copied by `prepare_arm.py`; it does not depend on those
root files or on Qwen's LLaMA-Factory modules. Keep its Transformers 5.14
training environment separate from Qwen's 5.8 and the vLLM serving environment.

After CUDA has exited and strict final-state checks have passed, persist the
closed artifacts to the **existing approved NFS/Ceph mount** and verify the copy:

```bash
python3 studies/tmax32k/commit_archive.py \
  --source /srv/tmax/new-training/training/M2-reproduction-explicit-id \
  --destination /srv/approved-nfs/tmax-training/M2-reproduction-explicit-id
```

No final archive receipt is published on a failed copy/SHA/fsync. Keep partial
copies for diagnosis; do not delete source checkpoints or overwrite an existing
archive. If an approved SSD/NFS `checkpoint-io.json` plan is supplied, the existing
storage helper also supports its original verified post-Trainer commit path.
Merely setting NFS environment variables does not create such a plan.

## Model delivery and inference

```bash
python3 studies/tmax32k/deliver_model.py --model /srv/approved/final \
  --sha256 REPLACE_WITH_VERIFIED_FINAL_SHA --output /srv/tmax/model-descriptor.json
/srv/venvs/inference/bin/pip install -r studies/tmax32k/requirements-serving.txt
/srv/venvs/inference/bin/pip install ./studies/tmax32k/serving
```

Install serving separately from training: the historical environments use
different Torch/Transformers versions. The small vLLM registration package is
the actual installed text-model adapter, with source SHA preserved. It delegates
forward and weight loading to vLLM and rejects unexpected weight prefixes.
Copy the four versioned `thinking/` files into the inference runtime, and place
verified descriptors under explicit model IDs in `MODEL_REGISTRY.json`.
Use Harbor's paired controller/runbook for lease-bound serving and Agent scoring.

For a separately authorized new NLL run, set `TMAX_MODEL_CACHE`,
`TMAX_CANONICAL_ROOT`, `TMAX_M2_DATA_ROOT`, `TMAX_APPROVED_READER` and
`TMAX_ABLATION_ROOT`; the reader's `PINNED_SFT_READER.json` is mandatory.
Run `scripts/region_nll.py --model /approved/final --name NEW-ID` on the server.
Outputs use exclusive creation and contain scalar statistics, not training
prompts or token IDs. `aggregate_nll.py` requires the approved trajectory coverage
index and archived scalar JSONL files; it refuses existing report outputs.
It reports token weighted, call macro and independent Task macro metrics
separately. Never rerun the thirteen completed archives on installation.

## Tests and compatibility

```bash
uv run --no-project --with pytest python -m pytest -q
TMAX_AUDIT_HARNESS=/absolute/pinned/audit-checkout \
  uv run --no-project --with pytest python -m pytest -q tests/test_current_recorder_contract.py
```

The opt-in test uses a real asynchronous Recorder and real export, then the SFT
file reader. It checks native tool/thinking messages, provider payload, artifact
hashes, incomplete flush rejection and corrupted artifacts. It is not a model or
benchmark smoke. The data conversion/training core used by other experiments is
unchanged. See Harbor's `COMPATIBILITY.md` for the pinned upstream comparison and
the reason an automatic main/wheel upgrade is prohibited.
