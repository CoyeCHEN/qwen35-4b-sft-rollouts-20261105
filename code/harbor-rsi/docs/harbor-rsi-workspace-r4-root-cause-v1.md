# WorkspaceBench Lite r4 Root-Cause Audit

Date: 2026-10-12

Status: `partial`; Workspace follow-up dispatch is stopped and no paid model call
was made during this audit or the verifier preflight.

## Scope and identities

- Harbor working tree: `/home/cky/harbor-rsi-final`, baseline `a6f2b04d`,
  branch `codex/agent-runtime-compatibility`.
- r4 job: `/home/cky/.local/state/harbor-rsi/phase4-workspace-first-final-r4`.
- r4 trial: `workspacebench-lite-3__nJxn397`.
- r4 task checksum: `fe70850b1318a16fe1dd893f311a12c052cad164b37d20c76f5d93bb4ba99b3d`.
- r4 Remote Docker identity: `c37e90ee177548ffb8215b26dd9585e8`.
- r4 Remote Docker project: `phase4f4-c37e90ee177548ffb8215b26dd9585e8`.
- r4 OpenHarness wheel SHA-256:
  `09c874a34f985266548292ee17acc234f30cda4b850d0b492df2c55cd4656f1f`.
- Provider wheel built after the final audit patch:
  `9cb6f95d93616584409fdeca4c9fb11457cc16f42b638fd306eec63b7531bbac`.

The two temporary Phase 4 configuration files in `docs/.phase4-*.yaml` contain
personal deployment paths and remain untracked; they are not part of this report
or a release artifact.

## r4 outcome

The original r4 result is preserved unchanged:

- Agent completion marker: `exit_code=0`.
- Agent stderr: empty.
- Agent stdout: 6,260,911 bytes.
- Trajectory: 214,970 bytes.
- Model usage recorded by Harbor: 526,402 input tokens, 16,801 output tokens
  (488,320 cached input tokens).
- Agent execution: 262.153 seconds.
- Verifier phase: 5.218 seconds.
- Whole trial: 411.399 seconds.
- Harbor `failure_phase`: `verification`.
- `verifier_result`: `null`.
- Final exception: `RewardFileNotFoundError`.
- No reward is credited for r4.

The raw result is at
`/home/cky/.local/state/harbor-rsi/phase4-workspace-first-final-r4/phase4-workspace-first-final-r4/workspacebench-lite-3__nJxn397/result.json`.

## Execution trace and first confirmed failure

Harbor did enter the normal shared verifier path. The traceback in `exception.txt`
ends at `harbor.verifier.Verifier.verify()`. The old Provider wheel recorded the
`/tests` transfer, but did not record successful exec calls, so the r4 artifact
does not by itself prove that the test script reached its first line. The
Provider evidence records the following sequence:

1. The agent completed and its large artifacts were downloaded.
2. During subsequent artifact inspection, the Provider probed the configured task
   workdir `/logs/workspace-native/OpenHarness--DeepSeek-Flash--phase3/3/workdir`.
3. That directory had already been removed by the native Workspace runner. The
   Provider recorded `task_workdir_unavailable` and correctly omitted `-w` for
   that one command.
4. On later calls the old `_task_workdir_unavailable` state was not respected.
   The Provider again passed the deleted workdir to `docker exec -w`.
5. The `test -d /logs/workspace-native` type probe therefore returned non-zero.
   Harbor's generic `ArtifactHandler` treated the source as a file, called
   `service_download_file`, and Remote Docker raised:
   `Expected one regular file in transfer`.

This is the first confirmed framework failure. It is visible in the r4 artifact
manifest as both `/logs/artifacts` and `/logs/workspace-native` download failures,
and in the r4 trial log as the bounded Remote Docker transfer exception. It is a
Remote Docker state bug, not a Workspace-specific rule and not an Agent exit.

The r4 Provider wheel did not yet record every successful exec command, so the
inner native verifier command's exit code and stderr were not retained. Therefore
the evidence does **not** prove whether `verify_single_case()` reached the Judge,
whether the real Judge returned an invalid response, or whether the reward was
written and then lost. Those are intentionally marked unknown rather than
inferred from the missing reward.

The r4 Provider evidence is preserved at
`.../workspacebench-lite-3__nJxn397/remote-docker-c37e90ee177548ffb8215b26dd9585e8.jsonl`.
Its final `cleaned` event proves identity-scoped cleanup completed; it does not
prove that the missing reward existed.

## Minimal generic fix

`packages/remote-docker/src/harbor_remote_docker/environment.py` now treats a
previously missing task workdir as permanently unavailable for the lifetime of
that Provider. Every later command whose requested cwd equals that workdir omits
`-w` and executes with the container default directory. This keeps artifact,
verifier, and cleanup calls usable after a task runner removes its private cwd.

The same method now emits bounded `exec_completed` evidence containing a
command SHA-256, effective cwd, exit code, bounded stdout/stderr tails, byte
counts, and duration. It deliberately does not log the complete command;
environment values are still passed through the existing temporary env-file
path and are not logged. Sensitive values in captured output are redacted.

Regression test:
`test_missing_task_workdir_is_not_reused_after_first_probe_failure` injects a
failed first workdir probe and verifies that the next command has no `-w` flag.

## Verifier-only recovery assessment

The r4 final agent workspace was not recoverable as an official score:

- The original Agent artifact manifest shows failed downloads for
  `/logs/workspace-native` and `/logs/artifacts`.
- The final r4 trial directory contains no complete native `agent.json` or
  preserved Workspace workdir.
- The native Judge requires the complete case metadata/output state and an API
  response. Reconstructing those inputs from the r4 host artifacts would change
  the evidence and would not be an r4 score.

Accordingly, no Verifier-only recovery was credited to r4.

## No-model verifier preflight

An independent identity was used with the original Workspace task, original
`tests/test.sh`, the Remote Docker Provider, and Harbor's normal `Verifier`.
The old successful native Agent artifact was used only as a fixed test fixture.
The Judge endpoint was a local deterministic HTTP stub returning a complete,
all-false rubric response; it did not call DeepSeek or any other model.

Evidence: `/tmp/phase4-workspace-verifier-preflight3-20261012`.

- Provider identity: `9bfecdf3286c4776a57092092ca3c455`.
- `test.sh` was uploaded to the opt-in `/tests` volume and executed.
- Stub probe returned HTTP 200.
- Test command exit code: 0.
- Harbor downloaded `/logs/verifier`.
- Reward file content: `0.0\n`.
- Harbor parsed `{"rewards": {"reward": 0.0}}`.
- Provider cleanup: passed.

This is a Gate 2 contract result only. The deterministic Judge response is not an
official Workspace score and must not be combined with the 29 prior benchmark
scores. The two earlier preflight attempts failed only because the temporary
Judge stub was not kept alive; those failures are recorded outside the code and
are not product failures.

## Contract gates

| Gate | Result | Evidence |
|---|---|---|
| 1. Environment, transfer, command setup | Passed | Existing Phase 4 no-model probes and r4 Agent setup; `/tests` upload in preflight3 |
| 2. Verifier, Judge protocol, reward write/recovery | Passed with deterministic stub | Preflight3, reward `0.0`, Harbor parse and cleanup |
| 3. Real OpenHarness end-to-end | Not rerun | r4 Agent completed, but its official score was not produced |
| 4. Remaining fixed cases | Blocked by instruction | Workspace r5 and nine remaining cases were not dispatched |

## Performance observations

The dominant r4 cost was the Agent, not Docker or Verifier:

- Agent setup: about 30.0 seconds.
- Agent execution: 262.153 seconds and 526,402 input tokens.
- Artifact transfer/collection: roughly 99 seconds. The Provider evidence has
  seven uploads totaling 6,768,640 bytes and three downloads totaling
  6,287,360 bytes; the largest download is the 6,266,880-byte stdout artifact
  and the largest upload is the 6,492,160-byte Workspace artifact. Harbor's
  trial log contains five lifecycle/agent commands and two failed artifact
  downloads before verification.
- Verifier phase: 5.218 seconds before the missing reward exception.

The Agent emitted 17 turn boundaries and 52 tool-call records in its JSONL log.
The audit does not change model budgets, prompts, task resources, verifier code, or
security settings. Large Workspace prompt/context traffic is a possible future
performance investigation, but it is not a cause of the r4 missing reward.

## Responsibility and next action

- **Confirmed root cause:** Remote Docker Provider's stale cwd state caused a
  generic artifact type probe failure and hid later command evidence.
- **Confirmed downstream symptom:** Harbor raised `RewardFileNotFoundError`
  instead of producing a `VerifierResult`; this is correctly not converted to
  reward zero.
- **Not established:** real Judge response, native `agent.json` state at r4
  verifier time, or whether r4's reward was ever written remotely.
- **Validation:** 69 focused unit/contract tests pass, including the native Harbor
  Job/Verifier fixtures and the new stale-workdir regression. Ruff and
  `git diff --check` pass.

Workspace follow-up remains stopped. The next permissible action is a fresh,
explicitly approved real-model smoke only after reviewing this preflight and
confirming that the updated Provider wheel is the runtime identity. No r5 or
remaining Workspace cases were started by this audit.
