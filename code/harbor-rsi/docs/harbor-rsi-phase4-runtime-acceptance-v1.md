# Harbor-RSI Phase 4 Runtime Compatibility

Date: 2026-10-12

## Scope

Phase 4 addresses the generic OpenHarness runtime contract exposed by the
WorkspaceBench preflight. The task image deliberately mounts `/tmp` with
`noexec`; wheel installation succeeded there, but the console script and
native Python runtime could not execute from that mount. No Workspace model
trial was dispatched while that condition was unresolved.

## Implementation

`BaseAgent.runtime_requirements()` is empty by default. OpenHarness declares a
writable and executable runtime requirement. `Trial` collects requirements from
the target and simulated-user agents and passes them to the selected
`BaseEnvironment` before `start()`.

The base environment keeps the ordinary `/tmp/harbor-agent-runtime` default
for providers whose normal `/tmp` is executable. `RemoteDockerEnvironment`
overrides the contract with `/harbor/agent-runtime`, a Compose volume scoped to
the current provider identity. The volume is added only when an agent requests
it, is chmod'ed after container startup, is labelled in the generated Compose
document, and is removed only through the provider's existing identity-checked
cleanup path.

OpenHarness uses the selected runtime directory for its venv, managed Python,
uv binary, uv cache, wheel, CLI session files, and lifecycle interpreter. It
probes execution before uploading the wheel and reports an explicit runtime
compatibility error when the provider path is writable but `noexec`.

No Benchmark name, verifier, prompt, model loop, Docker core branch, or second
Job/Trial scheduler was added.

## Evidence

Offline contract and provider tests: `139 passed, 18 skipped` in the
reproducible Phase 1/2 selection. Ruff check, formatting, and diff checks pass.
The new tests cover runtime requirement propagation, provider Compose volume
identity, provider-path selection, noexec failure reporting, managed Python,
and the existing native Harbor fixture job.

The real no-model Remote Docker smoke used a temporary standard Python image
with `read_only: true` and `/tmp:rw,noexec`. It verified:

* `/tmp` remained `noexec`;
* `/harbor/agent-runtime` was a writable executable volume;
* the OpenHarness wheel installed and `open-harness --version` returned 0;
* Python `_ssl`, `zlib`, and `ctypes` native loading returned 0;
* the Provider evidence recorded one resource identity and cleanup removed
  only that identity.

The first probe attempted to import `pydantic_core`, which is not a dependency
of the audited wheel. It was discarded as an invalid probe; the corrected
stdlib-native probe is the evidence used for acceptance. No model API was
called.

## Security boundary

The runtime volume does not remount or change the task's `/tmp`, rootfs,
capabilities, network, device, or Docker socket settings. It is nevertheless an
additional executable storage location. A benchmark that explicitly forbids
any executable writable storage beyond its declared mounts must be rejected by
configuration rather than silently given this volume. WorkspaceBench's
`/tmp:noexec` declaration alone does not establish that stronger prohibition;
the official security contract still needs to be checked before its model
trials resume.

## Evaluation status

The fixed five-benchmark ledger remains unchanged: 50 planned, 41 attempted,
29 valid scored, 5 agent failures, 7 infrastructure failures, and 9
WorkspaceBench tasks not started. Existing valid results were not rerun. The
next permitted Workspace action is a fresh final-wheel, no-model preflight;
model execution remains blocked until the runtime-volume security equivalence
is confirmed.
