# Terminal-Bench 2.1 Results

> Historical pilot using the previous adapter and explicit session/resource
> overrides. It does not validate the shared CLI integration introduced on
> 2026-09-20. Current commands and import paths are in [../README.md](../README.md).

This file records a sanitized pilot summary. Raw Harbor jobs, prompts, model
responses, sandbox contents, and credentials remain local and are ignored by
Git.

## 10-Task Pilot

- Job ID: `6e0b0bf4-5db9-4493-9783-43965ce37875`
- Dataset: `terminal-bench/terminal-bench-2-1`
- Agent: `openharness_harbor.agent:OpenHarnessAgent`
- Model: `deepseek/deepseek-flash`
- Environment: `openharness_harbor.e2b_one_hour:OneHourE2BEnvironment`
- Concurrency: `1`
- Attempts per task: `1`
- Runtime: 2026-09-20 00:58:27 to 01:54:51 UTC
- Result directory: `eval/terminal_bench_2_1/results/smoke/2026-09-20__00-58-13`

Harbor completed all 10 trials. Three tasks received reward `1.0`, five
received reward `0.0`, and two ended before a reward was produced. The native
Harbor mean over the ten tasks is `0.3`.

| Task | Reward | Outcome | Attribution |
| --- | ---: | --- | --- |
| `kv-store-grpc` | 1.0 | passed | none |
| `pypi-server` | 1.0 | verifier passed | agent exited non-zero after task completion |
| `openssl-selfsigned-cert` | 1.0 | passed | none |
| `dna-assembly` | 0.0 | verifier failed | task output did not satisfy verifier |
| `write-compressor` | 0.0 | agent error | CLI returned non-zero after model/agent loop; stderr empty |
| `schemelike-metacircular-eval` | 0.0 | agent error | CLI returned non-zero after model/agent loop; stderr empty |
| `regex-chess` | 0.0 | agent error | CLI returned non-zero after model/agent loop; stderr empty |
| `torch-pipeline-parallelism` | 0.0 | agent timeout | agent timeout at 900 seconds |
| `torch-tensor-parallelism` | n/a | verifier timeout | verifier timeout at 900 seconds |
| `qemu-alpine-ssh` | n/a | environment build error | E2B template provisioning failed on Debian package 404s |

The adapter setup and command contract were exercised by the nine trials that
reached agent setup. Their logs show wheel upload/install and the expected
`open-harness --cwd ... --mode json --no-session --no-resources --prompt-file`
command. No adapter setup, upload, API-key, or CLI-contract error was observed.

## Local Validation

- `python -m pytest -q`: `181 passed`
- `python -m pytest eval/terminal_bench_2_1/tests -q`: `4 passed`
- `python -m compileall -q eval`: passed
- Harbor: `0.23.0`
- Harness commit: `8c753930b6ab5f9b0a07f261e152f0fb238240c5`
- Wheel SHA-256: `738de2b04a91d5145ed2e43333cd6ef9eee90bf75947ef3a9421733580617ab8`
