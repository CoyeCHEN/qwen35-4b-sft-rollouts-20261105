# Harbor-RSI architecture

Harbor-RSI composes native Harbor execution with an installed OpenHarness agent
and an explicit environment provider. Campaign readiness freezes the inputs to
that execution; it does not provide another scheduler or model transport.

## Upstream baseline

The fixed upstream baseline is Harbor `v0.23.0`, commit
`1e5c5c6db929a10a140d05e606882c671ae20729`. This is the verified Git merge base,
not a claim that the team distribution contains every later upstream change.
The upstream history and Apache-2.0 license remain intact.

`src/harbor/job.py`, `src/harbor/tasks/client.py`, and
`src/harbor/trial/queue.py` remain byte-identical to that baseline. Native Harbor
continues to resolve Tasks, expand agents and attempts, limit concurrency,
maintain its queue, invoke Trial lifecycle hooks, and persist Results. There is
no replacement Job, Queue, TaskClient, or Scheduler in the Campaign extension.

## Execution and ownership

```text
JobConfig + reviewed profiles/contracts + immutable public assets
                           |
         harbor rsi campaign prepare / validate / freeze
                           |
                  frozen Campaign lock
                           |
              harbor rsi campaign run
                           |
           native Job -> TrialQueue -> Trial
                           |
        RemoteDocker -> installed OpenHarness CLI
                           |
           official Verifier -> original Result
                           |
               read-only qualification/report
```

| Component | Owns | Boundary |
| --- | --- | --- |
| Native Harbor | Task resolution, concurrency, Trial deadlines, cancellation, verification, artifact collection, Result persistence | Keeps primary, secondary, and infrastructure failures distinguishable; does not treat a missing Reward as a model zero. |
| Campaign extension | Reviewed readiness contracts, deployment identities, validation, immutable freeze, one native dispatch | Uses native Job configuration; does not implement a parallel task queue, retry loop, or service manager. |
| RemoteDocker | Explicit endpoint/Engine identity, Compose validation, execution, file transfer, owned-resource cleanup | No model requests, benchmark scoring, global prune, or implicit command replay. |
| OpenHarnessAgent | SHA-pinned CLI wheel installation, instruction/config transport, native process lifecycle, raw outputs and Recorder collection | Uses the Environment interface; no adjacent Harness source import and no benchmark-specific solution logic. |
| OpenHarness and model transport | Agent loop, tools, context projection/compaction, request budgets, model calls, Session/Recorder events | Provider/model protocol handling stays outside Harbor's queue and the generic Agent Loop. |
| Benchmark Task and Verifier | Original instruction, public assets, resource limits, hidden tests, scoring | Hidden material stays on the trusted verification side; readiness cannot modify the official scoring contract. |

The production RSI CLI exposes `campaign`. Its `prepare`, `validate`, `freeze`,
and `run` operations share the same native configuration and content identities.
The former RSI `run`/`preflight` launcher and `extensions/rsi/runner`, `models`,
and `legacy` execution paths are not production alternatives.

## Readiness is separate from scoring

`prepare` resolves the native Task/agent/attempt matrix and records the actual
deployment. `validate` runs declared environment, asset, network, installation,
and verifier-bootstrap checks without calling the model or solving the Task.
Contracts contain only the existing `agent` and `verifier` phases. There is no
invented bootstrap lifecycle phase.

Equivalent attempt configurations can share a validation group. The frozen
identity still covers every planned Task, agent, and attempt; changing a model,
runtime, image, cache, contract, or replay-affecting option invalidates that
identity. Shared public caches do not imply shared writable Task workspaces.

Public CLI dependencies are mounted read-only. Installation-only environment
settings belong in `kwargs.install_env`, scoped to Agent installation and
restored afterwards. They must not leak package-index restrictions into the
Agent's task execution or the official Verifier. Original resource declarations
and Verifier deadlines remain part of the Task contract. A declared per-task
Agent timeout is passed through native `AgentConfig.override_timeout_sec`;
research limits must preserve a longer original Agent deadline rather than
shortening it.

`freeze` requires complete READY coverage, verified installed wheel origins,
unchanged inputs, and bounded readiness validity. `run` rechecks identities,
refuses an existing Job, claims dispatch once, and calls native `Job.run()`.
An exclusive external lock must cover the entire native run. The dispatch
receipt prevents replay of that lock; it is not a distributed-lock service.
Missing or conflicting evidence blocks dispatch rather than choosing another
backend or silently retrying a model attempt.

## Narrow core changes

The following differences from the upstream baseline are reviewed separately
from ordinary adapters and provider packages.

| Area | Retained purpose | Why this boundary is necessary |
| --- | --- | --- |
| Trial failure and collection isolation | Preserve primary, secondary, and infrastructure errors; retain evidence when final collection fails | A failing Trial must not escape recovery and cancel healthy peers in the native Job TaskGroup. A post-END report cannot repair an exception that already escaped. |
| Managed agent completion/termination | Require durable completion or confirmed cancellation of the owned command tree before verification | A remote waiter's exit is not proof that the CLI stopped. This is opt-in through the existing agent capability and native lifecycle helpers. |
| Final environment cleanup acknowledgement | Retain one Provider stop Task and wait through repeated caller cancellation; record failure before Result/END publication | `shield(stop())` alone allows the caller to return while cleanup is still running. A failed cleanup is infrastructure evidence, not a successful stopped flag. |
| Private agent runtime | Declare the agent's writable/executable runtime through a narrow capability before environment start | Installation must not depend on the Task's mutable cwd, user, or noexec layout. Provider policy remains outside the Agent Loop. |
| Recorder-aware redaction | Give the native content-addressed redactor the trusted final secret set; preserve references, hashes, sizes, bytes, and newlines | Generic text replacement must not corrupt Recorder artifacts. Verifier-only secrets never enter the Agent prompt or environment. |
| Verifier metadata | Preserve the actual script return code and distinguish missing Reward from execution failure | Official tests and reward parsing/precedence are unchanged; metadata explains scoring validity instead of manufacturing a score. |

OpenHarness options, scoped installation settings, and native configuration
passthrough belong in the installed-agent adapter. Environment readiness and
read-only qualification belong in RSI extensions. They do not require changes
to Job, TaskClient, or TrialQueue.

RemoteDocker `0.1.1` adds filesystem work outside the event loop, waits for an
in-flight archive writer before temporary-file cleanup, and executes trusted
transfer checks/tar operations from `/`. It preserves normal Agent/Verifier cwd
semantics. Cleanup phase timings supplement the existing identity and absence
checks; they do not change deadlines or authorize foreign-resource deletion.

## Evidence and release limits

Stage A has actual native evidence: NOP produced official Reward `0`; M0
produced official Reward `1` and passed its Recorder audit. It used Harbor
`0.23.0+rsi.4` and the existing Provider wheel with SHA-256
`e44a17d7cc5b650f3108ebb887e000c11daa7119d380498cc9a608b94438d132`.
This establishes the tested execution path, not a benchmark success rate or
completion of a formal batch. These artifacts are not acceptance of the new
Harbor release or Provider `0.1.1`.

The publishable sanitized Recorder summary has SHA-256
`488e91d8dfbd8c392f903cd574cb0afaafff4db5c7791a7cb45cdaac98ebfbe6`;
its sealed evidence index has SHA-256
`e888ca33c76e352662c7026b29d06d4c32f3dc671676954beb8b4ebc758b7ab0`.
These identities do not publish the raw Recorder or Result content.

The Provider `0.1.1` wheel has independent installed-wheel/source checks,
scoped lint/type checks, and 50 passing CPU regressions. Stage B then executed
all six planned native Trials: two models, one Task, three attempts per model.
It used the Harbor `0.23.0+rsi.5` candidate at
`bbab4f9f7f97b0c3606077f71a61429d439c33ed` (wheel SHA-256
`b7b162fa3309c96ac3b609adcf3c27a1ffed1c9b7edb16d718f279e4302cc637`)
and OpenHarness wheel `.5` (SHA-256
`5811dd31e800cc68278073e346dce6b3b6bbe7701e6f44cd084946778d10d279`).
M0 had three normal scored completions, including two successes (2/3).
NEW-M1 Epoch3 had three infrastructure UNKNOWN outcomes: unconfirmed tool
process-group cleanup and counter/transport failures. Its raw zeros are
preserved but are not a model result of 0/3. This is a completed runtime
diagnostic with partial scoring coverage, not a valid model comparison.

After the Harness fixes, a separate `fix-git` n=1 canary per model used
OpenHarness `.6`, commit `e14ebe361c82b1d9ac1f5317e3d77bee1738ebd1`, wheel
SHA-256 `8c84a8659c136b027c36c48a7100d956fdb58c873b347ef6b240b561cc75e85d`.
Its actual Harbor commit was `d28ec97ad9e15f9266aac0c173068bd0cf3afeac`,
wheel SHA-256
`674b4453a5c6d7abc68c71c8ee241660ee94b13f66de4b6dda99aa16efd99f9f`,
with Provider `0.1.1`. M0 had a normal complete Reward `1`; NEW-M1 Epoch3
had a normal complete Reward `0`. Both passed Session/Finish, Recorder
reference/SHA/size, tool semantics, and exact-input-count versus Serving-input
checks. Real failed tool calls remain in the audited trajectories. These are
two single-Task acceptance results, not benchmark-wide success rates.

The publishable sanitized M0 summary SHA-256 is
`bf64577be4749c0f9908b3c0ffb42721d413a8700717e08ebaa468d3c91538f0`;
the NEW-M1 normal-zero summary SHA-256 is
`3e115f25cef57c76b5b1ce7b65f0fa194e7ee70a10f70a9c86dae1a0f790cbb8`.
These summary identities do not publish raw prompts, Recorders or Results.

The later Source5 checkpoint is commit
`2ad876b5490715d1fcc3bc7d3e17f4a7451636ca`, Harbor wheel SHA-256
`c6f61e6c4dbf7fc0ecbcefb0933295aa75f6a1480a1b506e41b4072bc4d5690d`.
The six PR checks passed at that source. Its 32-Task CLI validation passed,
and three new synthetic32 native Jobs have Agent-start evidence. They do not
yet have completed evaluation results or a final score. Common30 remains
blocked on complete readiness; neither its six-model 180-Trial group nor the
combined 212-Trial plan is declared complete. Separate Source5 QEMU and SAM
NOP checks produced legal official zeros and confirmed cleanup. The earlier
32/32 NOP environment check used source `2cb8783cf5dd92be6d80770081b4f14ea8e9bbbd`;
it is not relabeled as a Source5 model run. A built wheel, READY manifest or
Agent-start event does not substitute for a completed and qualified Trial.

Raw Result/Reward, Recorder, failed attempts, and recovery evidence retain their
original identities. Scoring infrastructure failures or missing evidence
required by the frozen scoring policy remain UNKNOWN. Recorder completeness
is reported separately from raw official score validity; a legal official zero
is not rewritten because the trajectory is incomplete. Recovery never
overwrites first-pass results.

The R51–H54 runtime orchestration artifacts remain preserved outside the product
source in `runtime-evidence`; this release does not add that directory to Git.
Their production invocation path is retired in favor of native Campaigns.
This does not claim deletion of historical scripts, rewriting of frozen
experiments, or termination of healthy in-flight Trials. Public documentation
contains no raw prompts, Recorder content, credentials, private host identities,
or deployment paths.

The reported “984-task” collection is **UNVERIFIED** in this release review:
its source, membership, and unique-task denominator are not established here.
It is not a frozen formal evaluation denominator.
