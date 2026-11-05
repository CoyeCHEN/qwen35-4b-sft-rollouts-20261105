# SFT Smoke Status

The original local rollout in this report had `reward_status: missing` because
it was executed without a Harbor Trial or verifier. It remains diagnostic data
only and cannot be promoted to the successful SFT set. The A800 tokenizer/mask
gate passed after the per-call history mask fix. The follow-up section below
records the later Harbor Trial with a positive reward and the one-step training
smoke using its complete Recorder export.

The current host also has no PyTorch CUDA runtime. The existing full-parameter
Trainer is available at `/home/chenkeyi/tmax_sft` on `aibox-167`; the fixed TMax
model and tokenizer loaded successfully there. Before a training smoke, copy
only the canonical data and this repository to an isolated run directory and
use the existing Trainer with BF16, max length 8192, learning rate `2e-6`,
per-device batch size 1, gradient accumulation 4, and an independent checkpoint.

The positive-reward gate is satisfied by one non-TB independent E2B Trial
(`reward=1.0`), and the complete Recorder-v2 sample satisfies the direct TMax
tokenizer gate on the A800. The later one-step smoke satisfies the optimizer,
parameter-update, and checkpoint reload gates. There is still no M0/M1 Agent
Reward comparison or generalization claim.

The first batch dataset was subsequently re-audited. The `hello-user` source
contains the Terminal-Bench canary GUID in `solution/solve.sh`, so its four-call
trajectory and the checkpoint trained with it are excluded. The clean replacement
dataset is recorded outside Git at
`runtime-evidence/openharness-teacher-batch-20261014/canonical_positive_batch_clean_v1.jsonl`.

Harbor preflight was read-only:

```text
harbor 0.23.0+rsi.1
harbor run --dry-run --yes --env e2b --agent nop --model deepseek/deepseek-flash \
  --n-concurrent 1 --n-attempts 1 --path \
  audits/openharness2-20261013/repos/harbor-rsi/examples/jobs/skills-merge/runtime-skill-merge
=> Dry run OK - 1 trial(s); nothing was run.
```

The Harbor virtual environment contains `e2b==2.51.0`; the local Docker daemon
was not used. The completed Trial used E2B and produced the verifier reward.
The next unblock is a Harbor run that preserves Recorder-v2 (or an equivalent
lossless provider-payload export) and joins that exact trajectory to its Trial
UUID and Reward before tokenization.

## Follow-up positive Trial smoke (2026-10-14)

The Harbor Recorder opt-in was subsequently enabled for Trial
`98a24372-de12-4897-81f0-33047af13e16`, which returned verifier reward `1.0` and
three complete provider-payload calls. Its canonical data was tokenized into
three task-group-preserving samples (2754 context tokens, 216 supervised tokens)
and trained for one optimizer step on an NVIDIA A800 80GB PCIe with the fixed
TMax 2B revision, with the recorded Provider tool definitions passed into the
student template. The independent holdout loss changed from `0.5935968` to
`0.5841535`, train loss from `1.1504825` to `0.7804408`, and the checkpoint
reloaded with exact tensor equality. The complete evidence is in
`reports/overnight_sft_pipeline_report.md` and
`runtime-evidence/openharness-positive-sft-20261014/a800-tools-forwarding/`.

This remains a one-task pipeline smoke rather than a generalization result. The
clean batch replacement completed one epoch and five optimizer steps on four
non-canary training task groups; its metrics and checkpoint hash are recorded in
`reports/overnight_sft_pipeline_report.md`. M0/M1 Agent Reward comparison remains
unrun.
