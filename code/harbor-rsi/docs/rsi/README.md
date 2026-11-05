# Harbor-RSI production guide

Harbor-RSI extends Harbor v0.23.0 with an OpenHarness installed-agent adapter,
Remote Docker provider and an explicit environment gate. The supported formal
entry is `harbor rsi campaign`. Native Harbor owns task resolution, the queue,
Trial execution, timeouts, official verification and result collection.

```text
JobConfig + reviewed environment contracts
  → prepare → validate → freeze
  → native Job.run → Trial → Agent → official Verifier → persistent results
```

The old `rsi run`, request schema and legacy experiment launchers have been
removed. Historical wheels, manifests and results remain evidence; this version
does not import or translate their formats. Upstream `harbor run` remains an
upstream low-level command and does not confer Campaign readiness.

## Install a pinned release

Use Linux, Python 3.12 or later, Docker with Compose, and a persistent directory
on the execution host. Install the explicit release wheels in a new environment:

```bash
python3.12 -m venv /srv/eval/runtime
/srv/eval/runtime/bin/python -m pip install \
  /srv/artifacts/harbor-0.23.0+rsi.5-py3-none-any.whl \
  /srv/artifacts/harbor_remote_docker-0.1.1-py3-none-any.whl
```

Verify each downloaded wheel against its release SHA256 manifest first. Install
from the local wheel path so `direct_url.json` records its origin SHA. Campaign
freeze rejects missing wheel provenance. A registry version or a source checkout
alone does not prove the installed runtime identity.

For development, use the repository's locked environment. For release builds:

```bash
python scripts/build_rsi_artifact.py --kind harbor --source . \
  --commit <exact-commit> --output /srv/artifacts/new-release
```

The builder archives the committed tree and embeds its commit identity. The
OpenHarness wheel is a separate, explicitly SHA-bound input. Evaluation imports
only its CLI contract, never the Harness source repository.

## Prepare one task first

Use a normal [Harbor JobConfig](../../examples/configs), with explicit tasks or
a pinned dataset. `agents` and `n_attempts` are native Harbor fields. Start with
one task, one model, one attempt. A NOP job uses `agents: [{"name": "nop"}]`;
it runs the unmodified official verifier and a legitimate zero is acceptable.

For OpenHarness, the agent configuration includes:

```json
{
  "name": "open-harness",
  "model_name": "openai/your-model",
  "env": {"OPENAI_API_KEY": "${OPENAI_API_KEY}"},
  "kwargs": {
    "wheel_path": "/srv/artifacts/open_harness_ai.whl",
    "wheel_sha256": "<actual-64-character-sha256>",
    "profile": "native-cli-v1",
    "record_trajectory": true,
    "config": "/srv/eval/frozen-harness-config.json",
    "install_env": {
      "PIP_NO_INDEX": "1",
      "PIP_FIND_LINKS": "/opt/public-cli-wheels"
    }
  }
}
```

Custom model endpoints require a complete native model descriptor. Keep model
credentials in the process environment and use variable references in the job.
Set Session/Recorder paths under `/logs/agent` in the native Harness config.
The adapter passes native configuration through; protocol changes must be
explicit and receive a new campaign identity.

Prepare the wheelhouse for the **actual CLI Python/ABI**, pin versions and record
file hashes. Mount only public installation assets, read-only, using the provider's
normal Compose input boundary. Managed Python requires its own frozen archive.
`install_env` applies only during installation and is restored before agent work;
do not put `PIP_NO_INDEX` in the entire agent environment. Verifier dependencies
are separate, trusted-side assets. Never mount solutions or hidden tests for the
agent. See [contracts and cache preparation](../../benchmarks/readiness/README.md).

```bash
harbor rsi campaign prepare --config /srv/eval/job.json \
  --contracts /srv/eval/contracts.json --output /srv/eval/prepared
harbor rsi campaign validate --prepared /srv/eval/prepared/prepared.json \
  --output /srv/eval/validation
harbor rsi campaign freeze --validation /srv/eval/validation/validation.json \
  --output /srv/eval/ready.lock.json --valid-for-sec 3600
flock --exclusive --nonblock --no-fork /srv/eval/dispatch.lock \
  harbor rsi campaign run --lock /srv/eval/ready.lock.json
harbor rsi campaign status --lock /srv/eval/ready.lock.json
```

Use `--profiles` at prepare only when individual tasks need an explicit effective
EnvironmentConfig, VerifierConfig or agent environment. No server address belongs
in product code. Keep the controller on the Docker host, writes and logs on that
host's persistent disk, and model requests directed to the model service. Remote
observation may copy small status artifacts; it must not scan or relay live task
outputs through another machine. A service manager or tmux keeps the native CLI
alive after SSH disconnect; do not create another evaluation controller.

A task profile can also set `agent_timeout_sec` to an explicit positive, finite
deadline. It sets native `AgentConfig.override_timeout_sec` for that task only;
the official Task, Verifier deadline and resource declarations remain intact.
For a research minimum, compute `max(original_task_timeout, research_minimum)`
in the reviewed deployment profile rather than shortening a longer Task through
a uniform job override. Unknown profile fields are rejected.

## Batch execution and recovery boundary

After the real single-task canary, increase native `n_concurrent_trials` and use
multiple `agents` and `n_attempts: 3`. Preparation/validation is deduplicated only
for identical task, agent and effective environment; attempts retain distinct
pre-registered Trial names. Different model configurations never borrow each
other's unchecked readiness. No extra queue or automatic retry is installed.

All prepare/validation/output directories must be new. Freeze binds source files,
cache manifests, task content, execution configuration, wheel/code identities,
Docker Engine and actual images. Drift or expiration blocks dispatch. A run has
an exclusive dispatch marker and refuses an existing Job directory, including a
failed one. Missing `result.json` is **not** evidence that a Trial never started.

Native Harbor resume can remove incomplete directories. This release exposes a
strict **configuration planner**, not automatic process adoption:

```bash
harbor rsi campaign recover --lock /srv/eval/ready.lock.json \
  --output /srv/eval/new-unstarted-plan
```

The planner requires the exact current schema/runtime identity and proof that
the original local dispatcher has exited. It refuses another host, inaccessible
process evidence, incomplete Trial directories, invalid Results or unconfirmed
cleanup. Every Trial that already has a terminal Result is retained, including
legitimate zeros, ones and failures; it never retries them automatically.

Only pre-registered Trials whose directories were never created are selected.
Remaining tasks are grouped into finite native JobConfig rectangles by their
full agent configuration and remaining attempt count. Each output job has a new
identity, exact source-slot mapping and source SHA ledger. Pass each generated
config/profiles/contracts through the same Prepare → Validate → Freeze → Run;
no old Ready timestamp or frozen lock is promoted to new readiness. Keep the
single deployment lock and bound the sum of concurrency if starting more than
one job. The command never starts a Job or model itself.

Do not use upstream resume to adopt a live or ambiguous Trial. Preserve its
container, Recorder, logs and original identity for explicit investigation.
A process being active is not proof of recovery, and missing Reward is not a
reason to select another attempt.

## Results and scoring

The job directory contains native `config.json`, `lock.json`, `result.json` and
one directory per Trial with original agent/verifier logs and result. `campaign
status` reads these files without invoking Docker, a model or a verifier. It
reports task/model/attempt identity, finished and scored counts, raw reward,
Agent errors, infrastructure errors and missing evidence separately. An active
process, CLI exit zero or a Finish call never substitutes for official scoring.

Campaign uses Harbor's public lifecycle hooks to append a small observation journal. Status distinguishes agent phase, environment/setup and verification; missing or malformed event evidence yields UNKNOWN. An Agent phase is not itself proof of a generation request: use Recorder and Serving evidence for actual model-call counts. Hooks do not select work, retry tasks or maintain a second execution state machine.

Recorder qualification is a separate audit. A valid official reward is retained
even when Agent closure or cleanup fails; it must not be promoted to a complete
successful training trajectory. UNKNOWN remains UNKNOWN. Diagnostic, recovery
and formal runs have different directories and fixed denominators.

See [architecture](ARCHITECTURE.md), [PR review](PR_REVIEW.md),
[upstream provenance](../../UPSTREAM.md) and the release validation record for
actual tests and remaining limits. No fixture or single-task smoke proves a
whole benchmark ready.
