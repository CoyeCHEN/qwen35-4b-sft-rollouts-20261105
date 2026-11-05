# Terminal-Bench-Science 0.1

Terminal-Bench-Science is already a native Harbor dataset. The RSI integration
therefore supplies only a pinned run preset and resource checks; it does not
copy task files or replace the benchmark verifiers.

The evaluated release is `terminal-bench-science/terminal-bench-science@v0.1.0`
from upstream commit
`f81afac4f11048e77a15dfc8fb1dbfb897fea0ce`. It contains 70 tasks. The task
manifest resolves to `sha256:0341d617c95a01594ca934019010625e3e2d2636b51f95952b87bd7235818316`.
Run `scripts/validate.py /path/to/terminal-bench-science-v0.1.0` before a
formal evaluation to check the checkout and resource assumptions.

All inspected v0.1.0 tasks request `gpus = 0`; the largest agent declaration
is 4 CPUs, 16 GiB memory and 50 GiB storage. Agent environments normally use
public network access because dependencies and scientific data are installed
there. Verifiers are generally separate and use no network. The separate
verifier receives only the task-declared artifacts, so the agent sandbox can be
destroyed after artifact collection without rerunning the agent.

Use E2B as the sandbox backend through
`harbor.environments.e2b_resumable:ResumableE2BEnvironment`. Science agent
budgets can be eight hours, so the one-hour backend is not suitable. The
resumable environment first relies on E2B's memory-preserving pause/resume;
when a fresh provider lifetime is required it forks the running sandbox,
validates identity and the durable command directory, switches to the child
and immediately kills the source. E2B briefly runs both copies while the
handoff is completed, so this is limited to one active agent command and is
not an atomic process migration. A fork is used only while the agent command
is still running. Once the agent exits, Harbor's separate verifier lifecycle
collects and hashes the declared artifacts, starts a clean verifier sandbox,
restores those artifacts, and runs the official tests.

## Smoke and full runs

Build an OpenHarness wheel and export `OPEN_HARNESS_WHEEL`, `E2B_API_KEY` and
`DEEPSEEK_API_KEY`. Until the v0.1.0 dataset is published in the Harbor
registry, also set `SCIENCE_SOURCE` to a checkout at the pinned upstream commit.
The run script creates a disposable flat symlink view for Harbor; it does not
copy or alter task files. The default model is
`deepseek/deepseek-flash` (the provider's DeepSeek V4.1 Flash ID); override it
with `SCIENCE_MODEL` only when the provider exposes a different accepted
identifier.

```bash
python benchmarks/terminal_bench_science/scripts/validate.py \
  /volume/wzhang/cky-workspace/my_projects/RSI/terminal-bench-science-v0.1.0
SCIENCE_SCOPE=smoke \
SCIENCE_SOURCE=/path/to/terminal-bench-science-v0.1.0 \
  bash benchmarks/terminal_bench_science/scripts/run.sh
```

After a representative smoke has passed, probe the 65 single-sandbox tasks with
`SCIENCE_SCOPE=compatible SCIENCE_N_CONCURRENT=8` over eight distinct tasks.
Lower it to 4, 2 or 1 only when the run provides evidence of E2B quota
exhaustion, model rate limiting or resource contention. `SCIENCE_SCOPE=full`
intentionally stops before dispatch because five release tasks require Docker
Compose sidecars; it must be run on a compose-capable backend. The E2B script
never silently removes those tasks from a full result. Select one task with
`SCIENCE_INCLUDE_TASK_NAME=<task>` for targeted debugging.

For RSI's artifact-based entry point, use the same dataset and pin
`benchmark.revision` to the manifest digest above. This keeps the wheel,
dataset content and Harbor-RSI revision auditable in the final result.
