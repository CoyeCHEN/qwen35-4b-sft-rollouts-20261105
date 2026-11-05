# Sources and Maintenance

- Official Harbor: https://github.com/harbor-framework/harbor
- Baseline tag: `v0.23.0`
- Baseline commit: `1e5c5c6db929a10a140d05e606882c671ae20729`
- Annotated tag object: `3c305dc5611e3600afc3c818735a82322f0264f8`
- Original `src/harbor/trial/trial.py` SHA256:
  `757f34424e35ea6e924484bff9ae75464e94acd5dec3d769bc65a9518ada79a8`
- Historical evaluation-code source: `NiuHechang/open-harness2@9957210811473f3e5f7d158646000e8977afeaa7`, `eval/`.

The upstream history and Apache-2.0 license are retained. This repository is
an independently hosted team distribution of Harbor. Its version is
`0.23.0+rsi.5`; installing an official wheel with the same base version does
not install these extensions.

The E2B extra pins SDK 2.51.0, used by the real transport checks. The original
lock used 2.25.0 and did not include the connectrpc transport imported by the
migrated reconnection helper. Other dependencies remain locked by `uv.lock`.

## Team Changes

| Source or purpose | Destination | Behavior |
| --- | --- | --- |
| OpenHarness adapter | `src/harbor/agents/installed/open_harness.py` | SHA-pinned wheel, native-only CLI contract, prompt file, raw streams, managed completion and Recorder-safe collection |
| Agent phase patch | `src/harbor/trial/agent_lifecycle.py`, `process_supervisor.py`, `trial.py` | Native capability gate, deadline includes supervisor prepare, cleanup barrier before verifier |
| E2B helpers | `src/harbor/environments/e2b_*.py` | Explicit subclasses; no site-packages patch or global exec monkeypatch |
| TB QEMU recovery | `src/harbor/environments/e2b_qemu_recovery.py` | Optional, account-specific templates; separately validated |
| Trajectory conversion | `src/harbor/extensions/rsi/trajectory.py` | Convert preserved OpenHarness JSON events to ATIF |
| Native Campaigns and reports | `src/harbor/extensions/rsi/readiness.py`, `report.py`, `recovery.py` | Prepare/validate/freeze inputs, run native Jobs, observe results, and plan only never-created Trials as new configurations |
| RSI integration | `src/harbor/extensions/rsi/`, `cli/rsi.py` | Native Campaign CLI, fixed task-agent-attempt identities, result completeness, JSON contracts |
| Benchmark preparation | `benchmarks/` | Data builders, task templates, original verifiers; isolated optional dependencies, including the pinned Terminal-Bench-Science 0.1 preset |

The adapter accepts only `native-cli-v1`: it follows the supplied Harness
wheel's defaults apart from explicit settings and transport configuration.
The former legacy profile and RSI request/runner/legacy execution paths have
been removed from production. Their historical scores and frozen artifacts
retain their original protocol identities and are not comparable by default.

Native Harbor owns Job expansion, queueing and Trial execution. RSI Campaign
readiness adds input/deployment verification and a single native dispatch;
read-only recovery planning neither resumes an unknown live command nor
replays a completed attempt. See [architecture](docs/rsi/ARCHITECTURE.md) and
[PR disposition](docs/rsi/PR_REVIEW.md) for the reviewed core boundary and
version-specific runtime evidence.

No code is imported from an adjacent OpenHarness checkout at evaluation time.
Wheel production belongs to RSI. `scripts/build_rsi_artifact.py` is an optional
producer utility; it archives an exact Git tree into a temporary directory and
does not edit the producer checkout. The runner verifies bytes, not authorship.

## Updating Upstream

Use an isolated branch or worktree, review the core diff against the pinned
baseline, and rerun the lifecycle, agent, packaging and actual smoke checks.
Preserve original results and their code identities. Never repair installation
by patching an unrelated environment's `site-packages`.
