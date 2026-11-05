# Harbor-RSI Final Architecture Acceptance

Date: 2026-10-12

This report records the final architecture and evaluation evidence for the
`codex/final-architecture-acceptance` branch. It separates source-level proof,
offline/provider tests, and real model results. It does not turn failed trials
into zero scores and does not merge duplicate recovery runs into the unique
task count.

## Result

The provider boundary is implemented and tested. Harbor's normal execution
chain is usable with the OpenHarness adapter, and a custom provider can be
selected through `EnvironmentConfig.import_path` without changes to a Task,
Agent, Verifier, Job, or Trial. Remote Docker is an optional package; ordinary
Docker and cloud providers do not import it.

The five-benchmark campaign is partial, not a completed 50-case acceptance:

| benchmark | planned | attempted | valid scored | agent failures | infrastructure failures | not started |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ALFWorld | 10 | 10 | 10 | 0 | 0 | 0 |
| ClawGym | 10 | 10 | 10 | 0 | 0 | 0 |
| Terminal-Bench 2.1 | 10 | 10 | 3 | 2 | 5 | 0 |
| JobBench | 10 | 10 | 6 | 3 | 1 | 0 |
| WorkspaceBench Lite | 10 | 1 | 0 | 0 | 1 | 9 |
| **total** | **50** | **41** | **29** | **5** | **7** | **9** |

ClawGym and JobBench used a DeepSeek Judge and are diagnostic rather than
official-comparable scores. Workspace has no legal score. TB-Science was not
run. The complete task IDs, content hashes, statuses, and source hashes are in
[`harbor-rsi-phase3-final-case-ledger-v1.json`](harbor-rsi-phase3-final-case-ledger-v1.json)
and [`harbor-rsi-phase3-final-provenance-v1.json`](harbor-rsi-phase3-final-provenance-v1.json).

## Four architecture goals

### 1. Sandbox decoupling: implemented

`EnvironmentFactory.create_environment_from_import_path()` loads an external
`BaseEnvironment` class. The Remote Docker package exposes
`harbor_remote_docker:RemoteDockerEnvironment` and reuses Docker task/Compose
semantics while keeping SSH, Docker endpoint, staging root, project namespace,
timeouts, and cleanup policy in provider configuration. No host, jump host,
credential, WSL path, or Docker context is embedded in Harbor core.

The provider advertises `mounted=false`, rejects unsupported host-sensitive
features, records an identity-marked evidence file, verifies SHA-256 for file
transfers, and only removes resources after identity checks. A controller or
transport failure is an infrastructure event; commands are not silently
replayed. The final no-model smoke used a read-only rootfs, tmpfs, dropped
capabilities, upload/download, hash comparison, and identity-scoped cleanup:

`/tmp/remote-docker-provider-smoke-20261012f-trial/remote-docker-59369411446a46b38753fa1178af3b10.jsonl`

This proves the tested provider path. It does not prove every Docker feature
is supported remotely. Privileged containers, host networking, devices,
external mounts, GPU reservations, Docker socket mounts, and equivalent
host-sensitive features are rejected or remain unsupported.

### 2. New Benchmark without core changes: demonstrated offline

Reasoning Gym was used as a new-adapter acceptance case. Its existing adapter
generated a normal `task.toml`, instruction, Dockerfile, solution, and
`tests/test.sh`; no Harbor core, OpenHarness loop, EnvironmentFactory, or
Remote Docker changes were made for this acceptance. Repeated generation
produced identical task files and hashes. Harbor's normal `harbor run -p ...`
configuration contained the dataset path and agent only; it did not invoke the
RSI runner, freeze step, or a second launcher.

The verifier was exercised offline with an Oracle answer (reward `1.0`) and an
incorrect answer (reward `0.0`). The adapter wheel built successfully with SHA
`6a888c55d4f64fc032d144f96eef43cb77fb6efc2d8370334d0513244644e8be`. A real
Docker Job was not run because the local default Docker socket is unavailable.
The adapter should pin `reasoning-gym==0.1.25` in its generated environment or
record an image digest; its current unpinned `pip install reasoning-gym` is an
adapter reproducibility follow-up, not a Harbor core defect. The generator also
needs a follow-up review: `dataset_params.json` can retain the YAML default size
instead of the CLI `--size`, and the generated task identity does not include
every effective CLI parameter. This is an adapter task/scorer provenance issue;
it was not changed in Harbor core.

### 3. Official Harbor execution path: substantially restored

The standard path remains:

`TaskClient -> Job -> Trial -> EnvironmentFactory/BaseEnvironment -> InstalledAgent -> Verifier -> TrialResult`

`Execution.snapshot_tasks` defaults to `false`, so normal RSI preparation uses
TaskClient's materialization and cache. The compatibility snapshot is explicit,
not a required step. Existing result fields remain backward compatible;
`failure_phase` and `infrastructure_errors` have defaults and old `result.json`
files remain readable.

The RSI runner still writes provenance, freezes tasks when explicitly requested,
and supervises the Harbor subprocess. Those functions are retained as an
integration/provenance entry point, not as a second Trial scheduler or scoring
system. This is a transitional boundary, not proof that all RSI wrapper state
has disappeared.

### 4. Harbor, OpenHarness, and Sandbox responsibilities: implemented with
explicit contracts

Harbor owns task resolution, Job/Trial scheduling, deadlines, cancellation,
result persistence, verifier invocation, and artifact recovery. OpenHarness is
one `BaseInstalledAgent`: it validates one explicit wheel, installs it through
the Environment interface, writes the instruction/configuration, runs the CLI,
and preserves stdout, stderr, completion marker, ATIF trajectory, and exit
status. It imports no Docker, SSH, E2B, Modal, or provider SDK. The Sandbox
implements environment creation, capabilities, exec, transfer, and resource
cleanup; it does not own Jobs, Trials, scoring, or resume state.

The remaining OpenHarness-specific `openharness-cli-v1` and DeepSeek-compatible
options are versioned CLI contract requirements. They are not benchmark-specific
branches. A future incompatible Harness needs a new contract and tests.

## Confirmed runtime fixes

The final source includes these narrowly scoped fixes:

* `OpenHarnessAgent.install()` uses a selected compatible interpreter or a
  private managed Python environment, and exposes that interpreter to the
  lifecycle supervisor. It no longer assumes a task image has system
  `python3`.
* `run_agent_with_lifecycle()` preserves the primary Agent/Environment error;
  release or cleanup failures are attached as evidence instead of replacing
  it. Infrastructure failures remain attached to the owning Trial.
* OpenHarness error classification consumes structured terminal error events;
  free text in tool output cannot turn a third-party HTTP 429 into a model API
  rate-limit error.
* Remote Docker persists operation names, exit codes, bounded stdout/stderr
  tails, transport-loss evidence, and controller-loss markers.
* Compose interpolation follows standard `$`/`$$` semantics. Read-only
  containers use a tar stream through `docker exec -i -u root` when `docker cp`
  cannot write the container root filesystem. SHA-256 verification remains in
  place for both directions.

The source-level diagnosis remains conservative. Reasoning-only 32K output
truncations are a configuration/model/Harness interaction, not evidence of a
provider defect. QEMU cancellation and remote Compose startup failures have
confirmed failure layers but insufficient historical stderr to identify a
single lower-level cause. No model configuration was changed to rewrite those
results.

## Runtime identities and evidence

Final audited source identity:

* Harbor commit: `7895780caf7485f0e04cf84e45e4d61c262d97e7`
* Harbor wheel SHA-256: `0be824578b1e4176cc94f178f14ec1d9c973a9fa152d43748993c60bc2b86262`
* Remote Docker wheel SHA-256: `5b3010b289e262b67a9fa189028e1ea2711962145c3d4352d52be4fdda718b20`
* OpenHarness wheel SHA-256: `40c30be4de7cf7772780a7d3f43f32abfe49b5fdc7e3bbe5c7c7b166dc7b9b15`
* Isolated wheel venv: `/tmp/harbor-rsi-wheel-venv-20261012/bin/python`

The 29 legal scores retain their actual historical identities. Seventeen were
produced from an editable Harbor installation and remain separately identified;
they were not discarded or resampled. Later recovery jobs used older fixed
wheels and are not merged into the unique-case counts. The final wheel was
validated with offline/provider smoke tests but was not silently substituted
into old model results.

## Verification

The focused regression command, including the optional provider source tree,
was:

```text
PYTHONPATH=packages/remote-docker/src uv run pytest \
  tests/unit/rsi tests/unit/test_remote_docker_provider.py \
  tests/unit/test_trial_cleanup.py tests/unit/test_openhands_sdk_agent.py -q
```

It passed with `136 passed, 18 skipped`. Ruff check, Ruff format check, and
`git diff --check` passed. The earlier full focused run recorded 182 passing
tests when the optional package was installed into the environment; the
current reproducible checkout command uses `PYTHONPATH` explicitly because the
provider is intentionally optional.

## Workspace Gate 3 follow-up

The single formal Gate 3 r5 is recorded in
[`harbor-rsi-workspace-gate3-r5-acceptance-v1.md`](harbor-rsi-workspace-gate3-r5-acceptance-v1.md)
and [`harbor-rsi-workspace-gate3-trial-ledger-v1.json`](harbor-rsi-workspace-gate3-trial-ledger-v1.json).
The Agent exited normally, but the dispatched runtime loaded an older
RemoteDocker wheel. After native workdir cleanup, that runtime carried the
deleted cwd into artifact/verifier handoff, so no reward was produced. No
additional Workspace task was dispatched. Workspace remains 0/10 valid scores;
the nine unstarted task IDs are preserved for a future run after a fresh
target-wheel no-model gate.

## Remaining work and limits

* WorkspaceBench Lite needs a new-wheel, no-model gate followed by controlled
  recovery of its nine unstarted tasks before it can obtain legal scores. Its
  previous failure occurred before CLI/model execution at read-only-container
  `docker cp`; the tar fallback is now covered by provider tests and smoke, but
  has not been used for a new 10-case model batch. A fresh final-commit task
  tree was generated at
  `/tmp/phase3-workspace-harbor-tasks-final-20261012-1791773219318756722`:
  all ten Tasks parse, `DOCKER_CONTEXT=rsi-149 docker compose config` passes for
  all ten, and the target image is present. The old prepared task tree must not
  be reused because it contains the pre-fix single-dollar Compose entrypoint.
  The new-wheel gate then reached Harbor's real OpenHarness installation: wheel
  upload and dependency installation succeeded, but the task's explicit
  `tmpfs /tmp` is `noexec`. The console script returned exit 126 and a
  `python -m cli` probe also failed to map native `.so` dependencies. An
  `exec` remount made both probes succeed. This is a generic runtime contract
  gap, not a Workspace data failure; a future fix needs a provider-negotiated
  executable writable runtime mount (ideally a dedicated volume), rather than
  changing the Workspace task to weaken its security policy. Evidence:
  `/tmp/workspace-final-preflight-20261012/result.json` and
  `/tmp/workspace-cli-module-probe-20261012/result.json`. The noexec diagnosis
  was independently reproduced with identity `9a799b5992ec4351a30eea920bee7f00`;
  the `rw,exec` counterfactual succeeded with identity
  `eca6b6e6596b4b018634c563aff2bec9`. Both resources were cleaned by identity.
* The audited documentation commit `a6f2b04d` is on the pushed
  `codex/final-architecture-acceptance` branch and is tracked by PR #7:
  https://github.com/CoyeCHEN/harbor-rsi/pull/7. PR #5 is merged and PR #6 is
  closed; no merge or main rewrite was performed.
* Remote transport timeout behavior under a loaded QEMU/SSH path still needs a
  dedicated fault-injection regression. Existing evidence identifies the
  timeout barrier risk but does not prove a universal fix.
* The RSI runner's manifest and subprocess supervision remain transitional
  provenance layers. Removing them requires a separate compatibility migration;
  ordinary benchmark execution does not require task snapshots.

Accordingly the architecture acceptance is **implemented for the provider and
boundary contracts, partial for the five-benchmark campaign, and not complete
as a claim of 50 valid scored cases**.
