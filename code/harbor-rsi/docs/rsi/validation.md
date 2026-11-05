# Validation Record

Date: 2026-09-24. This record separates development evidence from release
acceptance. No full-benchmark score is claimed.

## Final Release Evidence

- Release Harbor wheel built from commit `99143c1d7c0265587d26c1f1a76057fb133fd80d`,
  SHA256 `6b241bdc8b71ade37a1277df5c52c56959866506d9ce7ad11f162c2aba53e15e`.
- The isolated noneditable runtime was reinstalled from that wheel. Runtime
  identity reports Harbor commit `99143c1d`, `source_dirty=false`, and the
  locked E2B SDK 2.51.0.
- Final TB2.1 request `tb21-final-9957210`: OpenHarness commit `9957210`,
  wheel SHA256 `2f6d546d...1953e`, 1/1 scored, reward 1, completed.
- Final TB2.1 request `tb21-final-8b50eb9`: OpenHarness commit `8b50eb9`,
  wheel SHA256 `209e8c7f...9d022`, same task and configuration, 1/1 scored,
  reward 1, completed.
- Final ALFWorld request `alfworld-final-99143c1d`: same release Harbor and
  Harness as above, 1/1 scored, reward 0, completed with return code 0. This is
  a normal benchmark zero, not an infrastructure failure; the result includes
  the verifier reward and no exception.

## Development Evidence

- A noneditable Harbor 0.23.0+rsi.1 wheel was installed in an isolated Python
  3.12.14 environment and invoked from `/tmp` with PYTHONPATH removed.
- TB2.1 `terminal-bench/openssl-selfsigned-cert`, request
  `tb21-openssl-9957210-01`: one finished/scored task, reward 1, no exception.
- ALFWorld `alfworld-look_at_obj_in_light-alarmclock-none-desklamp-308-9ca5ee7a`,
  request `alfworld-9957210-01`: one finished/scored task, reward 1, no exception.
- Both used the same OpenHarness adapter, Harness commit
  `9957210811473f3e5f7d158646000e8977afeaa7`, native-cli-v1, DeepSeek Flash,
  max_tokens 8192, E2B one-hour backend, concurrency 1.
- ALFWorld was regenerated from official json_2.1.1 data using ALFWorld 0.4.2:
  134 valid_unseen tasks, all six task types, no oracle material in agent assets.
- WebShop and JobBench adapter wheels were built and installed into a fresh
  Python 3.12 environment; WebShop's packaged task-template resource was
  readable after installation. This validates packaging only, not their cloud
  environments or benchmark scores.

These runs used development wheels before final dependency locking and commit
embedding. They establish execution evidence, not the final release identity.
Release evidence must identify the exact committed source and locked runtime.

## Check Scope

The focused suite covers artifact identity, native/legacy configuration,
instruction fidelity, remote marker transport, CLI errors, result integrity,
zero/partial/timeout scoring, duplicate dispatch, task snapshots, SIGTERM
forwarding, real local process supervision, benchmark builders, E2B reconnect
without replay, and official Trial/agent regression tests.

Full-repository Ruff checks and formatting pass. Full `ty check` in the focused
runtime reports missing optional provider packages and associated upstream
diagnostics; this is not a full type-check pass. New runtime modules are checked
separately. The default upstream dev group installs unrelated cloud and ML
stacks and is not required to run RSI evaluation.

## Open Acceptance Items

The two artifact-switching smokes and release ALFWorld smoke are complete.
Independent benchmark-builder installation is complete for the packaged
adapter wheels. The private repository `CoyeCHEN/harbor-rsi` was created and
commit `2de4856b25871b4cb7caf1aa94eebacf28d2375b` was pushed to `main`.
Collaborator invitation requires the senior developer's confirmed GitHub
username and role.

JobBench/WebShop real evaluations, full TB2.1/ALFWorld, Docker model evaluation,
QEMU recovery templates, and long auto-pause recovery are not claimed tested
by the two development smoke runs.
