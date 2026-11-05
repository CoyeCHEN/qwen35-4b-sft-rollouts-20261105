# openharness-sft implementation status

This status is for the independent SFT repository and is intentionally separate
from the upstream Open-Harness, RLBridge and Harbor worktrees.

| Check | Result | Evidence |
|---|---|---|
| Real Open-Harness Recorder v2 export found | `verified` | `/home/cky/workspace/RSI/runtime-evidence/deepseek-20261013/trajectory` contains a real DeepSeek run with 4 model calls and 3 tool executions |
| Real RLBridge rollout found | `absent` | Audit workspace search found no RLBridge `.json`/`.log` rollout pair |
| Open-Harness adapter | `real Recorder v2 validated` | Real `events.jsonl` converted to canonical JSONL; artifact hashes, calls, tools, contexts and observations passed validation |
| RLBridge adapter | `fixture/schema validated` | JSON plus reward-log fixture in `fixtures/rlbridge` |
| Harbor reward association | `real Recorder + Reward join verified` | Harbor Trial `98a24372-de12-4897-81f0-33047af13e16` and its Recorder directory share the Trial metadata; verifier reward is `1.0` |
| Real TMax 2B tokenizer/mask | `verified on A800` | Three positive-Trial calls with recorded Provider tools tokenized with the fixed `39227cc1...` checkout; per-call masks supervise only the current response (`145/39/32` tokens; `2754` context tokens) |
| Full BF16 SFT | `1-step smoke verified` | Existing Trainer at `/home/chenkeyi/tmax_sft` ran the tools-complete positive Trial data on an NVIDIA A800; checkpoint reload and parameter-update gates passed |
| End-to-end Open-Harness -> Harbor -> SFT | `partial; one-task chain complete` | DeepSeek -> Open-Harness -> Recorder -> Harbor Reward -> canonical data -> TMax 2B -> A800 Trainer is real for one independent task; batch collection and M0/M1 Reward comparison remain unrun |

No upstream repository was modified. The package does not claim that synthetic
fixtures prove Recorder or RLBridge runtime behavior. The direct smoke evidence
is described in `reports/runtime_smoke.md`, `reports/trajectory_validation.md`,
and `reports/sft_data_validation.md`.
