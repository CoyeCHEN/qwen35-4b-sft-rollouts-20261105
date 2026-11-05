# WorkspaceBench Lite integration

中文迁移过程、canary 证据和 ScienceAgentBench 复用清单见
[`MIGRATION.zh-CN.md`](MIGRATION.zh-CN.md)。

This directory integrates **WorkspaceBench** into Harbor-RSI without converting
its tasks into Harbor task packages. WorkspaceBench has a shared role
filesystem, task-specific input injection, office-file outputs, and a native
rubric judge. Reusing that runner and judge preserves benchmark semantics;
Harbor-RSI owns source pinning, OpenHarness launch settings, provenance,
validation, and result/trajectory packaging.

Only WorkspaceBench is adapted here. No ScienceAgentBench source or runtime is
changed by this work.

## Pinned inputs

- WorkspaceBench repository:
  https://github.com/OpenDataBox/Workspace-Bench
- Commit: 3fbd0f1a136720fece86786545983e26642c3db2
- Dataset: English Lite, 100 tasks
- Lite task asset digest:
  sha256:f47d396a4a75ea8125a3683807198d23183cb70a38bb1ca0137675ff972d4847
- Agent: a caller-supplied OpenHarness wheel, hashed during preparation
- Default model: deepseek-flash
- Agent settings: thinking high, images enabled, context 200,000,
  max output 65,536, timeout 2,400 seconds
- Judge: WorkspaceBench's native rubric LLM judge

The upstream download helper does not record a Hugging Face revision for the
five multi-gigabyte role workspaces. The validator therefore pins all Lite task
metadata and task-local inputs byte-for-byte, and records the workspace
language plus file counts. A publication run should additionally archive the
five workspace directory manifests or an upstream HF revision. This limitation
must not be hidden in a report.

## Ownership boundary

Harbor-RSI owns source pinning, validation, a disposable patched worktree,
OpenHarness wheel provenance, launch settings, summaries, trajectory indexes,
retry policy, and final audit. WorkspaceBench continues to own prompt
construction, role workspaces, task-local input materialization, per-task
container isolation, output extraction, and the native rubric Judge.

This distinction matters: an LLM Judge rubric pass rate is a score produced by
WorkspaceBench's judge. It is not a deterministic unit-test pass rate, and a
local DeepSeek-Judge run is not automatically comparable to the official
leaderboard.

## Runtime layout

Preparation creates a detached worktree beneath the ignored
benchmarks/workspacebench/datasets/ directory. It applies
patches/workspacebench-openharness.patch, copies the OpenHarness bridge, and
stores the wheel under evaluation/.generated/artifacts/. It also creates the
ignored `evaluation/tasks` and `evaluation/tasks_lite` mount targets before the
repository is mounted read-only in a task container.

The approximately 7 GB of downloaded Lite data is **not copied**. Docker mounts
tasks_lite and the five *_raw directories read-only from the original
WorkspaceBench checkout. Standard and working directories are created in the
disposable runtime worktree. This protects disk space and the source dataset.

The PR intentionally does not bundle benchmark data, a model key, or an
OpenHarness wheel. Each user first follows WorkspaceBench's upstream download
instructions so that `evaluation/tasks_lite` and all five
`evaluation/filesys/*_raw` directories exist, then points
`WORKSPACEBENCH_SOURCE` at that checkout. `validate.py` rejects a wrong source
commit or incomplete assets before execution. The host runner and Docker use
the same `WORKSPACEBENCH_ASSET_EVAL` path, so downloaded assets remain external
to Harbor-RSI and are never resolved through a machine-specific hard-coded
path.

The compatibility patch is deliberately narrow:

- registers OpenHarness in the upstream config builder;
- maps container-returned config paths back to host paths;
- mounts only the selected role workdir writable in each task container;
- falls back to filename when an upstream data record omits target_path;
- uses cp --reflink=auto before the portable Python copy fallback;
- mounts the large source assets read-only.
- derives the required workspace roles from the selected task IDs, instead of
  materializing all five role workspaces for every smoke or subset run;
- hides the detached worktree's file-form `.git` metadata with a file-form
  read-only mount, preserving Docker's file/directory mount type contract;
- falls back from metadata-preserving `copy2` to byte-preserving `copyfile`
  when a WSL/NTFS bind mount rejects timestamp updates;
- installs the pinned OpenHarness wheel into a benchmark-scoped Docker volume,
  avoiding Python venv creation on NTFS while reusing it across task containers;

It does not alter prompts, rubrics, Judge logic, task selection, or scores.

## Commands

Run from WSL because the upstream Docker protocol expects POSIX paths:

~~~bash
cd /mnt/d/open-harness-benchmarks-cache/sources/harbor-rsi
export WORKSPACEBENCH_SOURCE=/mnt/d/open-harness-benchmarks-cache/sources/workspace-bench
export OPEN_HARNESS_WHEEL=/path/to/openharness-0.1.0-py3-none-any.whl

python3 benchmarks/workspacebench/scripts/validate.py "$WORKSPACEBENCH_SOURCE"

WORKSPACEBENCH_SCOPE=smoke \
  bash benchmarks/workspacebench/scripts/run.sh --dry-run --print-config

export DEEPSEEK_API_KEY=...
WORKSPACEBENCH_SCOPE=smoke \
  WORKSPACEBENCH_RUN_NAME=OpenHarness-DeepSeek-Flash-smoke-001 \
  bash benchmarks/workspacebench/scripts/run.sh

WORKSPACEBENCH_SCOPE=lite \
  WORKSPACEBENCH_RUN_NAME=OpenHarness-DeepSeek-Flash-lite-001 \
  bash benchmarks/workspacebench/scripts/run.sh
~~~

Selection flags such as --task-ids 33 or --persona "Researcher" are passed
through. Smoke adds --task-limit 1 only when no explicit selection is present.
Secrets are written only to the ignored runtime .env and Judge YAML.
`run.sh` uses system `python3` by default because the native runner only needs
PyYAML on the host; this avoids installing Harbor-RSI's unrelated GPU and
training dependencies. Set `HARBOR_PYTHON` explicitly when using another
interpreter.

## Trajectory and result contract

Each task directory remains the source of truth and contains agent.json,
raw/openharness_stdout.jsonl, raw/openharness_stderr.log, the sanitized
raw/openharness_invocation.json, output files, and the native
rubrics_judge--MODEL.json. The normalized agent record contains status,
duration, token metrics, returned paths, and trace.executionTrace.

scripts/summarize.py writes summary.json, tasks.csv, and
trajectory-index.json. The index records task-to-artifact paths and SHA-256
hashes. Raw JSONL is retained even when normalized events are embedded in
agent.json. Parsers must split JSONL only on LF; Unicode line-separator
characters inside document or tool content are data.

A release audit must check all 100 task IDs, first-valid-result selection,
status, Judge totals, normalized reward, token totals, duration coverage, and
artifact hashes. Natural model failures and timeouts remain in the denominator.

## Failure attribution

- **agent/model**: malformed command, wrong file, natural timeout, tool misuse.
  Keep the result; do not rerun to improve score.
- **provider/external**: confirmed 429/5xx/disconnect before a valid result.
  A bounded retry is allowed and remains visible.
- **environment/adapter**: bad mount, wheel install failure, Docker failure, or
  path translation bug. Stop expansion, fix, and rerun only invalid attempts.
- **judge**: inspect detailed Judge artifacts and request logs. Never infer a
  retry solely from a generic judge_failure label.

## ScienceAgentBench migration playbook

1. Freeze repository, commit, task count, dataset revisions, licenses,
   resources, and score semantics before writing agent code.
2. Decide ownership explicitly. Use native Harbor tasks only when environment
   and verifier semantics are faithfully representable; otherwise retain the
   benchmark-native runner and let Harbor-RSI own reproducibility.
3. Keep upstream immutable. Use a detached worktree and a small, commit-pinned
   patch, never ad-hoc replacement in a shared checkout.
4. Keep large assets outside code. Mount datasets read-only; put standards,
   workdirs, caches, and outputs in an ignored runtime. Measure disk before
   raising concurrency.
5. Use one explicit asset-root contract on both host and container. A Docker
   bind mount alone is insufficient when the host launcher also selects tasks
   or stages agent-visible inputs.
6. Scope expensive shared-environment preparation to the selected tasks. A
   benchmark-native helper may otherwise initialize every role or shard even
   for a one-task canary.
7. Preserve filesystem object types at isolation boundaries. In a detached
   worktree `.git` is a file, while in a primary checkout it is a directory;
   Docker bind-mount masks must match the target type. Create ignored mount
   targets before mounting their parent repository read-only.
8. Treat host filesystem metadata operations as optional portability features.
   Input bytes are required; preserving timestamps is not, and may be rejected
   by NTFS/DrvFS bind mounts under a capability-restricted container.
9. Bridge only prompt, workdir, timeout, provider, and the
   openharness-cli-v1 contract. Do not reimplement benchmark scoring.
10. Preserve raw CLI JSONL and normalized agent.json, token usage, duration,
   stderr, output files, and Judge evidence.
11. Prove that rubrics and evaluation-only metadata are absent from the
   agent-visible mount. Expose only the selected task and writable workdir.
12. Validate in layers: static source/data check, patch check, dry-run
   provenance, one real canary, a heterogeneous sample, then full evaluation.
13. Recompute coverage, scores, usage, duration, hashes, and retry selection
   from raw artifacts before reporting.
14. Distinguish local-Judge results from official leaderboard results and avoid
    causal harness claims when protocols differ.

The reusable pieces for ScienceAgentBench are validate.py, prepare.py, the CLI
bridge, the raw-plus-normalized trajectory contract, and the failure taxonomy.
Its own environment and verifier still require an independent analysis.
