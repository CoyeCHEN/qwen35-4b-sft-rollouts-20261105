# Qwen3.5 launch acceptance

Formal stages use the existing `python -m sft --workspace ... run` remote job. They
keep one native Trainer/DeepSpeed lifecycle through evaluation and checkpoint saves.
They require explicit stage authorization, current-source GPU acceptance, frozen data,
and a fresh authorized GPU check. Old driver evidence alone cannot open this gate.

For a bounded acceptance config, keep the formal LR, GA4, BF16, ZeRO-3, warmup,
seed and loss contract; set max_steps=3, save_steps=1, save_total_limit=3, do_eval=false,
eval_strategy=no, with a separate `verify-...` output. `sft.runtime.canary` calls the
same `sft.runtime.lf_train` twice: stop after checkpoint-2, then full-state resume
at step3 with the same config and scheduler horizon. Step1 at LR=0 is expected;
steps2 and3 must show real FP32 master changes. No polling, retries or formal SFT
are launched by this command. It refuses allocated GPUs and existing outputs.
Use a detached user service with a finite RuntimeMaxSec for GPU acceptance.

`checks/readiness.json` joins four real rank logs and complete native checkpoints.
It requires source fingerprint, GA4 batch counts, finite gradients/loss, FP32 Adam,
same PID/CUDA context/engine across save+step2, and model/Adam/scheduler/RNG
restoration in a different process. 128K requires >=130000 nonpadding tokens per
microbatch and a second representative-target run with >=3000 supervised tokens.
Historical GA1/old-entry passes remain separate evidence. Native Trainer data
position/scheduler/RNG continuation is also compared against uninterrupted GA4 in
CPU regression tests. CPU tests do not prove CUDA capacity.

M1 adoption reuses the immutable Arrow cache and original task split. Readiness also
requires the complete row/labels/Collator proof tied to the imported source manifest.
The configured shared project lock coordinates this checkout with existing GPU queues.

`python -m sft.candidates --help` materializes candidates from pinned normalized
exports, native identity proof and an immutable token/label index. This never approves
data. Tool declarations and current-assistant targets are retained without rewriting.
The text budget reserves the pinned LF collator's 66 masked dummy-image tokens;
whole decisions beyond the budget are rejected, never truncated.

`adopt-m2-candidates` is a separate explicit release gate for
`TB21_SAME_TASK_ADAPTATION`. It requires an approved release, finalized tool schema,
complete Loader proof and immutable dataset SHA. It never converts these data into
CLEAN/unseen-task data. Independent CLEAN sources retain the original stricter raw
Recorder/Verifier source gate via `prepare-m2`. Finish remains disabled.

LF saves final full HF weights natively at stage end. `python -m
sft.runtime.hf_export MODEL_DIR` seals those weights, config and fixed official
Tokenizer after checking completed stage state; `--smoke` adds CPU load/generation.
A ZeRO shard directory does not qualify. M1-to-M2 loads final HF weights and starts a
new optimizer/scheduler. Same-stage `--resume` must point to an explicit complete
checkpoint with matching stage/config identity. Neither command selects `latest`.
