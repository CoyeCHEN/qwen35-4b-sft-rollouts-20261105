# ALFWorld Harbor dataset

ALFWorld packaged as a Harbor dataset, so the benchmark-independent
`harbor.agents.installed.open_harness:OpenHarnessAgent` runs it by changing
`--dataset` only. No ALFWorld-specific code exists in the agent; everything
below lives in the dataset and the task environment.

```
Harbor
  ├── ALFWorld dataset (one task = one episode)
  └── OpenHarnessAgent → open-harness CLI → play.py → daemon → AlfredTWEnv
```

## 1. Why valid_unseen, and why 134

The canonical split is `valid_unseen`, which upstream `AlfredTWEnv` enumerates
under `train_eval="eval_out_of_distribution"`. That enumeration yields 134
supported games from 341 candidate trials — upstream itself filters the rest,
and the build refuses to proceed at any other count.

`valid_unseen` is the split ReAct and Reflexion report, and the one LLM-agent
ALFWorld results are usually quoted on. `valid_seen` is deliberately not built
and not mixed in; `build_dataset.py` verifies every selected game lives under
the configured `eval_ood_data_path`.

## 2. Benchmark protocol

Generative action setting. Each task is exactly one episode:

```
container start → load one game → env.reset() once → agent acts → success /
termination / 50-step limit → verifier
```

The agent sees ordinary ALFWorld textual observations and nothing else. Scoring
is upstream's own success signal, `info["won"]`.

## 3. Why admissible_commands is not shown

`info["admissible_commands"]` is never returned to the agent. This is a
**protocol choice aligning with ReAct/Reflexion-style generative evaluation, not
an ALFWorld requirement** — ALFWorld exposes the list, and choice-based
evaluations such as AgentBench use it. Withholding it is what makes the setting
generative: the model must produce the action text itself.

The daemon requests `admissible_commands` from TextWorld because upstream's
expert wrapper needs it, but the agent-facing relay only ever returns
`observation`, `episode_over` and `steps_remaining`.

## 4. Why no BLEU / nearest-admissible correction

Whatever the model emits is passed to ALFWorld verbatim. There is no BLEU
matching, edit-distance repair, fuzzy correction or normalisation to a legal
action anywhere in `play.py` or the daemon. An illegal action gets TextWorld's
native response (typically `Nothing happens.`) and consumes one step, exactly as
upstream would. Correcting actions would inflate success rates and make results
incomparable with generative baselines.

## 5. Where the 50-step budget comes from

`alfworld_base_config.yaml` has `general.training_method: dagger`, so upstream
`AlfredTWEnv.init_env` reads `dagger.training.max_nb_steps_per_episode` (50) and
passes it to `textworld.gym.register_games(max_episode_steps=...)`. **TextWorld
enforces the limit.** The build only forwards that same number; the daemon keeps
a step count for reporting and for refusing post-termination calls, but never
truncates on its own. Changing the number in the config changes the budget
everywhere, with no code change.

## 6. Daemon architecture

ALFWorld state lives in a Python object, while a shell agent gets a fresh
process per command. So the episode is held by a persistent daemon:

```
play.py (thin, stateless client)
   │ JSON over Unix socket
   ├── /run/alfworld/agent.sock   ← agent-reachable relay: observe, act, ping
   └── /run/alfworld/private.sock ← root-only: status (used by the verifier)
```

Two sockets rather than one permission check: the agent-facing socket has no
code path to privileged operations at all. `observe` is free; `act` forwards one
`env.step`.

The daemon is started by the Harbor healthcheck and is idempotent in the
required direction: if it is running and ready, the healthcheck succeeds and
touches nothing; if it is running but unhealthy it **fails** rather than
restarting. It never kills a live daemon, because that would silently rewind a
part-finished episode to step 0. A broken daemon surfaces as an infrastructure
failure, not as `reward = 0`.

## 7. Agent / hidden-data boundary

Unlike a ReAct evaluator, which only exposes `observation → action`, Open
Harness has a shell. Without a boundary the agent could simply read the game
files. **This isolation is a benchmark-integrity adaptation for shell-capable
agents, not part of the original ALFWorld protocol.**

| | |
|---|---|
| daemon | root |
| `/opt/alfworld-private/` (game, daemon, config, log) | root-only, `0700` |
| `/run/alfworld/private.sock` | root-only |
| agent | `alfagent` (uid 2000), no sudo |

`traj_data.json` — which carries the human walkthrough — is never copied into
the image at all; only `game.tw-pddl` is, inside the private directory. Hidden
configuration is read from a root-only file, so no sensitive path appears in
daemon argv where `ps` or `/proc` would expose it.

Verified in a live E2B sandbox as `alfagent` with the daemon running: reading the
game file, the private directory, daemon source, config and log all fail with
permission denied; `find` for `*.tw-pddl` and `traj_data*` returns nothing;
connecting to the private socket raises `PermissionError`; `sudo -n` requires a
password; and `/proc` cmdline scanning reveals no game path. `play.py observe`
still works.

## 8. Score

Per task, `info["won"]` at the end of the episode: success → 1, failure → 0. The
verifier runs as root, asks the private socket for the final state and writes
that reward. Final metric:

```
success_rate = successful_tasks / 134
```

No LLM judge, trajectory comparison, walkthrough matching or file heuristic is
involved. The agent has no API that reveals `won`.

## 9. What the Oracle is for

`solution/solve.sh` replays ALFWorld's handcoded expert walkthrough through the
normal `play.py act` interface. It exists to prove a task is solvable and that
packaging, daemon, client and verifier agree — **it is not part of the
benchmark protocol or grading criterion.** The verifier scores final state, so
any other successful path scores 1 too. The official `game.tw-pddl` files
already contain `"solvable": true`; the full benchmark must use those files
directly and must not require the handcoded expert to rediscover a route.

Upstream's handcoded expert calls the global `random` module without seeding it,
so consecutive runs yield different walkthroughs and some exceed 50 steps.
`scripts/expert_plan.py` therefore seeds `random` and tries seeds in a fixed
order until one wins within budget, recording the winning seed in
`manifest.json` (`oracle_expert_seed`) and in the generated `solve.sh`. The
expert's policy is untouched; only its RNG is pinned, which is what makes the
dataset reproducible.

How many seeds a game needs varies widely. Most win on seed 0; the hardest in
`valid_unseen`
(`pick_heat_then_place_in_recep-Mug-None-Cabinet-10/trial_T20190909_021200_669381`)
first wins on seed 25 and uses 48 of its 50 steps. The search cap is 100. Note
what this implies: upstream's handcoded expert is not a reliable 50-step solver
on this split, so a build failure here means "the expert could not find a short
enough route", not necessarily "the task is unsolvable".

## 10. Canonical vs optional

Canonical (what this dataset builds): `valid_unseen`, generative actions, no
admissible list, no action correction, 50 steps, upstream `won`.

Not implemented, deliberately: `show_admissible_commands=true`, ReAct few-shot
prompting, and `valid_seen`. None are required here, and each would either
change the protocol or bake experiment-specific prompting into the canonical
dataset. Adding the first would mean a new daemon response field plus a task
flag; the code has no hook for it today.

## 11. Build the dataset

Needs the ALFWorld runtime (`alfworld==0.4.2`, `textworld`) and the extracted
`json_2.1.1` data. That runtime is not the repo's eval venv; use a Python that
has ALFWorld installed.

```bash
export ALFWORLD_DATA=/path/to/alfworld-data
python benchmarks/alfworld/build_dataset.py \
    --output benchmarks/alfworld/datasets/valid_unseen \
    --no-oracle
```

This is the canonical full-dataset build. The builder enumerates the upstream
134 `valid_unseen` games, verifies each official game file is marked
`solvable: true`, and copies only `game.tw-pddl` into the root-only private
directory. It never copies `traj_data.json`. `--no-oracle` avoids an unnecessary
and unreliable handcoded-expert search; `--limit N` / `--task-type TYPE` are for
partial smoke datasets and skip the 134-task check. Output is gitignored.

Static checks over a built dataset, runnable from the eval venv:

```bash
ALFWORLD_DATASET=/absolute/path/to/generated-dataset \
uv run --group rsi-test pytest tests/unit/rsi/test_alfworld_dataset.py
```

Real daemon, CLI and verifier integration is checked through the RSI smoke
request described in [the handoff guide](../../docs/rsi/README.md).

## 12. Single-task smoke

For an optional oracle smoke, build a separate small dataset so the canonical
full dataset remains oracle-free:

```bash
python benchmarks/alfworld/build_dataset.py \
  --output benchmarks/alfworld/datasets/oracle-smoke \
  --task-type pick_two_obj_and_place --limit 1
```

Run that generated task with `-a oracle`; it should score 1 and proves the
packaging:

```bash
export E2B_API_KEY="$e2bapi"
harbor run -p benchmarks/alfworld/datasets/oracle-smoke/<task-name> \
  -a oracle \
  -e harbor.environments.e2b_one_hour:OneHourE2BEnvironment \
  --n-concurrent 1 --yes --jobs-dir benchmarks/alfworld/results/smoke
```

Then the real agent (`-a nop` in place of the agent flags gives the negative
control, which must score 0):

```bash
export DEEPSEEK_API_KEY=...
harbor run -p benchmarks/alfworld/datasets/valid_unseen/<task-name> \
  --agent harbor.agents.installed.open_harness:OpenHarnessAgent \
  --agent-kwarg "wheel_path=$PWD/dist/open_harness_ai-0.1.0-py3-none-any.whl" \
  --model deepseek/deepseek-flash \
  -e harbor.environments.e2b_one_hour:OneHourE2BEnvironment \
  --agent-env 'DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}' \
  --n-concurrent 1 --yes --jobs-dir benchmarks/alfworld/results/smoke
```

Build the wheel in the Harness producer repository or with
`scripts/build_rsi_artifact.py --kind harness --source ... --commit ... --output ...`.
The
canonical adapter is `harbor.agents.installed.open_harness:OpenHarnessAgent`; pass the
wheel through `--agent-kwarg wheel_path=...`.

## 13. Full 134-task evaluation

```bash
export E2B_API_KEY="$e2bapi"
export DEEPSEEK_API_KEY=...
harbor run -p benchmarks/alfworld/datasets/valid_unseen \
  --agent harbor.agents.installed.open_harness:OpenHarnessAgent \
  --agent-kwarg "wheel_path=$PWD/dist/open_harness_ai-0.1.0-py3-none-any.whl" \
  --model deepseek/deepseek-flash \
  -e harbor.environments.e2b_resumable:ResumableE2BEnvironment \
  --agent-env 'DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}' \
  --n-concurrent 8 --yes --jobs-dir benchmarks/alfworld/results/full
```

Harbor treats the directory as an adhoc dataset of all 134 tasks. Raise
`--n-concurrent` only as far as the E2B account's sandbox limit allows. Read the
mean reward as the success rate, and check `Exceptions` separately: an
infrastructure failure is not a zero-scoring episode.

Keys come from environment variables only, never from tasks, Dockerfiles,
manifests or command arguments. Results directories are gitignored; do not
commit jobs output, trajectories or model responses.
