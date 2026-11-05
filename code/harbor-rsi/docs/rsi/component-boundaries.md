# Harbor-RSI Component Boundaries

This is the phase-one boundary contract.  The default execution path is the
upstream Harbor path:

```text
TaskClient -> Job -> Trial -> BaseEnvironment -> InstalledAgent -> Verifier -> Result
```

## Harbor core

Harbor owns task resolution, the Job and Trial lifecycle, timeouts, cancellation,
result persistence, artifact collection, and verifier invocation.  A provider
failure is recorded on the owning Trial as an infrastructure error.  It must not
escape the Trial task and cancel unrelated siblings.

`EnvironmentFactory.create_environment_from_import_path()` is the extension
point for custom providers.  A provider is selected by `environment.import_path`
in the run configuration; no provider registry or second SandboxManager is
needed.

## Sandbox provider

`BaseEnvironment` implementations own environment creation, capability
validation, `start`, `stop`, `exec`, file transfer, and provider resource cleanup.
They do not schedule Jobs, create Trials, score tasks, or implement a second
resume system.  Unsupported capabilities must be rejected during provider
construction or the existing capability checks.

The native test provider in
[`tests/unit/rsi/test_native_job.py`](../../tests/unit/rsi/test_native_job.py)
demonstrates that a custom provider can replace the standard provider without
changing the Task, Agent, Verifier, or Job configuration.

## OpenHarness agent

`OpenHarnessAgent` is an InstalledAgent adapter.  It validates and installs one
explicit wheel, writes the instruction and CLI configuration through the
Environment interface, runs the CLI in the Task working directory, and records
stdout, stderr, the completion marker, wheel hash, and exit status.  It does not
know whether the Environment is Docker, E2B, Modal, or a custom provider.

The adapter currently retains the `openharness-cli-v1` and DeepSeek profile
contract required by the existing OpenHarness wheel.  Removing that contract is
a future versioned CLI change, not a benchmark-specific workaround.

## Benchmark adapter

Benchmark code supplies standard Harbor Tasks and, when needed, a standard
Verifier or benchmark-owned test assets.  It does not select a provider or modify
Trial, Job, OpenHarness, or scoring behavior.

## Current violations and transitional code

| Location | Boundary violation | Phase-one disposition |
| --- | --- | --- |
| `src/harbor/extensions/rsi/runner.py:_prepare` | Copied every resolved Task into `.rsi/<request>/tasks`, creating a second Task materialization. | Disabled by default. `Execution.snapshot_tasks=true` is the explicit compatibility path. |
| `src/harbor/extensions/rsi/runner.py:run` | Maintains a run manifest and launcher process state beside Harbor's Job state. | Retained as provenance and subprocess supervision; it does not schedule Trials or score results. |
| `src/harbor/agents/installed/open_harness.py:OpenHarnessAgent` | The current CLI contract builds a model config and requires the existing DeepSeek-compatible wheel. | Kept for `openharness-cli-v1`; no provider or sandbox APIs are imported. |
| WSL-only `src/harbor/environments/docker/docker.py` remote branches and `docker/remote.py` | Remote staging is mixed into the local Docker implementation in the uncommitted WSL snapshot. | Not copied into the default branch. It remains an opt-in design to be extracted behind an import-path provider with explicit endpoint and staging configuration. |
| `src/harbor/trial/trial.py:run` and `_stop_agent_environment` | Final cleanup errors previously escaped the finalization boundary or replaced the primary error. | Cleanup/finalization failures are attached to the current Trial as `infrastructure_errors`. |

## Remote Docker rule

Remote Docker must be selected explicitly with an external provider configuration.
The generic Harbor code must not contain a host, SSH jump host, Docker context,
credential, or private WSL path.  A remote provider must reject unsupported bind
mount, Compose, network, ownership, or cleanup semantics instead of silently
changing the Task.  Its resource identity must be checked before deletion, and
controller loss must leave an inspectable cleanup record.

The WSL implementation is deliberately not made a default `DockerEnvironment`
mode in this phase.  The upstream local Docker path remains unchanged when
Remote Docker is disabled.
