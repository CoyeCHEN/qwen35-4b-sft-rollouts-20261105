# Version and environment record

The following are the exact read-only audit worktrees used to define the
adapters. They were clean when checked on 2026-10-13; no upstream worktree was
modified by this project.

| Component | Path | Commit | Commit time |
|---|---|---|---|
| Open-Harness2 | `audits/openharness2-20261013/repos/open-harness2` | `03e65d03e0575fc77b40628bf58b8d375a94fca2` | 2026-10-13 17:43:16 +08:00 |
| openharness-rl | `audits/openharness2-20261013/repos/openharness-rl` | `5ed11a3fe5d9fed68475ff7ed4fd4a17d5b76252` | 2026-10-13 15:25:29 +08:00 |
| harbor-rsi | `audits/openharness2-20261013/repos/harbor-rsi` | `34584831354e59c69059ca5fb5c2e569f8ee82b8` | 2026-10-13 16:11:45 +08:00 |

The requested A800 path `/home/chenkeyi/tmax_sft` is not visible on this host.
An older local copy exists at `/home/cky/tmax_sft`, but it was not treated as
the A800 training state. The system Python has no `transformers` or `torch`; the
old virtual environment has Transformers but no PyTorch and no local TMax
tokenizer cache. No model download was attempted.

## A800 tokenizer preflight

Read-only SSH probing found `aibox-167` with ten visible GPUs, including eight
`NVIDIA A800 80GB PCIe` devices. Its existing `/home/chenkeyi/tmax_sft` virtual
environment reports PyTorch `2.8.0+cu128`, Transformers `5.14.0`, Accelerate
`1.15.0`, Python `3.12.3`, and CUDA `12.8`. The fixed
`models/allenai--tmax-2b-39227cc1` checkout was used with `local_files_only=True`;
its model, tokenizer, config, and chat-template hashes are recorded in
`reports/sft_data_validation.md`. No optimizer or model-forward training step
was started.

The package itself is an uncommitted local Git repository under
`/home/cky/workspace/RSI/openharness-sft`; it has no remote. Source revisions,
model revisions, tokenizer revisions, and checkpoint hashes must be filled in
from the A800 run before training.

## Runtime smoke version distinction

The non-Git directory `/home/cky/workspace/RSI/open-harness2` is an older
`open-harness-ai` 0.1.0 source tree and has no Recorder-v2 `foundation/rollouts`
package. It was not silently upgraded. The real smoke used the clean audited
Git worktree above, installed editable into the existing Harbor virtualenv as
`open-harness-ai` 0.3.0; its Recorder manifest contains the source-file hash
`9a9225f126e1ab19e4f52d9cbe43909f273bed5514198563191f315e08635ada`.
No wheel was copied into a Harbor sandbox and no upstream repository was
modified. A future Harbor Trial must build and SHA-256-pin a wheel from the
chosen Open-Harness commit before claiming the same Recorder behavior.

## Harbor Trial

The one E2B smoke used Harbor `0.23.0+rsi.1`, Open-Harness commit
`03e65d03e0575fc77b40628bf58b8d375a94fca2`, wheel SHA-256
`05bcd684f8c37beaa280927248dbb239f79807fe33e43cfb47b3d8e2c7851b83`, and
model `deepseek/deepseek-flash`. It ran one attempt with no retries and
`thinking=low`, `max_tokens=2048`, and `provider_retries=0`. The E2B template
build and Trial completed; exact Trial/reward hashes are in
`/home/cky/workspace/RSI/runtime-evidence/deepseek-20261013/harbor-reward-association.json`.
