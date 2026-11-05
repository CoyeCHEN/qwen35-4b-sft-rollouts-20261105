# Zero-intrusion capture audit

Date: 2026-10-13 (Asia/Shanghai)

This audit keeps `open-harness2`, `harbor-rsi`, and `openharness-rl` read-only. No
new Trial or model call was started because the available zero-change paths do
not produce both a complete provider-payload trace and a Harbor reward in one
execution.

## Versions actually inspected

The three top-level directories are source copies without `.git` metadata. The
commit-addressable, clean audit worktrees are under
`audits/openharness2-20261013/repos/`:

| Component | Evidence used | Revision |
|---|---|---|
| Open-Harness2 | `repos/open-harness2` and the editable install used by Harbor | `03e65d03e0575fc77b40628bf58b8d375a94fca2`, package `open-harness-ai 0.3.0` |
| openharness-rl | `repos/openharness-rl` | `5ed11a3fe5d9fed68475ff7ed4fd4a17d5b76252` |
| harbor-rsi | `repos/harbor-rsi`; runtime venv | `34584831354e59c69059ca5fb5c2e569f8ee82b8`, package `harbor 0.23.0+rsi.1` |

`harbor-rsi/.venv/bin/open-harness --version` reports `0.3.0`. Its
`direct_url.json` points to the audited Open-Harness worktree, and the verified
wheel used by the earlier Harbor run has SHA-256
`05bcd684f8c37beaa280927248dbb239f79807fe33e43cfb47b3d8e2c7851b83`.
The separate top-level `open-harness2` copy is an older `open-harness-ai 0.1.0`
tree without Recorder v2 and was not used as runtime evidence.

All three audit worktrees were clean. No source in those repositories was
modified during this audit. `openharness-sft` is an uncommitted local repository;
the only addition in this pass is this report.

## RLBridge result

### It is not a transparent DeepSeek proxy in its current form

RLBridge does expose an evaluation mode and an external endpoint option:

* `rlbridge/main.py:88-95` defines `--eval` and `--eval-llm-base-url`.
* `rlbridge/main.py:597-610` starts a Collector in evaluation mode and points it
  at the supplied endpoint.
* `rlbridge/collector.py:1366-1401` creates the per-rollout proxy routes and
  drives the recipe agent.

That endpoint is still required to implement the RLBridge model-server contract.
Before every generation, `rlbridge/collector.py:1662-1693` calls
`Rollout.prepare_request`. For SGLang, `rlbridge/rollout.py:2882-2911` builds a
`TokenizeRequest` and posts it to `<endpoint>/v1/tokenize`; the evaluation path
uses `_tokenize_for_eval` at `:2877-2879`. The result is decoded and reused to
construct token-level Turns (`:2919-2940`). DeepSeek's documented and previously
verified interface here is `/models` and `/chat/completions`; no compatible
`/v1/tokenize` endpoint is part of the tested API. Therefore an OpenAI-compatible
Chat Completions URL alone is insufficient.

The Collector also performs backend-specific parsing and local-tokenizer work:
`rlbridge/rollout.py:3001-3091` loads a model tokenizer and reasoning/tool parser,
and `rlbridge/collector.py:1794-1889` reconstructs streamed semantic events and
records tokenized Turns. It is designed for the local SGLang/vLLM rollout engine,
not for arbitrary external providers. There is no pure pass-through recorder
mode that skips tokenization, parser setup, or the RL rollout state.

### What RLBridge persists

The recorder is in `rlbridge/agent.py:23-157`. It writes `{uid}.log` and
`{uid}.json` under `rollout_logs_pending`, then archives them by model version
(`:151-157`). The JSON includes decoded prompt/response text, tool calls,
request-group and parent-turn metadata (`:73-107`); the Collector stores the
request body in `state.last_agent_request` (`rlbridge/collector.py:1683-1687`).

This is sufficient for RL's internal `TrajectoryTree`, whose generated-token
mask and log-prob fields are assembled in `rlbridge/collector.py:261-318` and
`:521-530`. It is not a stable, lossless SFT interchange format:

* the persisted JSON has one `messages` snapshot plus decoded per-turn text;
  it does not serialize the exact request payload for every call;
* the JSON dump does not contain the reward. Reward is written to the adjacent
  human-readable `.log` by `dump_log`, and the rollout id is the collector's
  `task-{task_index}_sample-{sample_index}_agent-0` form
  (`rlbridge/collector.py:1943-1954`), not a Harbor Trial UUID;
* mapping that id to a Harbor Trial would require a recipe-level join artifact;
  no such Trial UUID mapping is implemented in this revision.

The existing `openharness-sft` RLBridge adapter correctly refuses to fabricate
later contexts: it marks the first snapshot `context_only` and later turns
`incomplete` when `actual_prompt_messages` are absent
(`adapters/rlbridge.py:54-77`). Consequently, an RLBridge JSON dump cannot pass
the current TMax SFT context-fidelity gate without a real exporter or a
different capture format.

## Harbor/Open-Harness zero-change path

The current Harbor Agent installs a pinned wheel and invokes the CLI in
`src/harbor/agents/installed/open_harness.py:422-433`. The complete argv is
`open-harness --cwd ... --print --mode json --config ... --prompt-file ...`.
There is no `--trajectory-dir` argument, no generic extra-argv option, and no
agent option that maps to one. `OpenHarnessOptions` at `:25-47` only exposes the
wheel, model descriptor, retry, token, tool, and thinking settings.

The Agent does preserve stdout/stderr and converts the JSONL stdout to ATIF in
`:466-476`. ATIF contains user/assistant/tool/observation events, but not the
exact provider request payload, system prompt, or tool definitions. The current
SFT adapter therefore marks this data `context_only` and rejects it for TMax
tokenization; this is a fidelity limitation, not a parser failure.

Open-Harness itself has a valid opt-in Recorder interface. Its session creates a
Recorder from `config.recording.directory` in
`5-modules/controller/sessions/session.py:36-39`, and the CLI exposes
`--trajectory-dir` in the installed command. The Harbor invocation simply does
not pass that existing flag. There is no supported environment variable or
task-level setting that turns it on for the current Agent without changing the
Agent command construction.

## Existing runtime evidence

These files are retained outside Git under
`/home/cky/workspace/RSI/runtime-evidence/deepseek-20261013/`:

1. **Recorder-only run:** `trajectory/manifest.json` and `trajectory/events.jsonl`
   (hashes `72e9c3a6...fe0f2` and `f57ad5e5...5ce51`). It has four DeepSeek
   calls, three real Bash executions, three observations, and complete provider
   payloads. It has no Harbor `task_id`, `trial_id`, or verifier result, so its
   reward status is `missing`.
2. **Harbor run:** Trial `b67b50db-82cd-4fdb-87e7-8661c3e1dcc9`, task
   `harbor/extra-instruction-path`, job
   `84d3c3bb-82c4-4952-9952-a278d199835c`, reward `1.0`. The result and reward
   file are joined in `harbor-reward-association.json`; the task checksum is
   `0aa8f1c7...8b607`. This run has an ATIF trajectory with one Write call and
   one observation, but no Recorder-v2 manifest/events and no exact provider
   payload. It is valid reward evidence and invalid as a complete SFT sample.

The two runs have different execution identities and are deliberately not
joined by task name or time. They do not establish a single positive SFT
trajectory.

## Decision

**No usable zero-intrusion capture path exists in the inspected revisions.**

* RLBridge cannot transparently proxy DeepSeek because its external evaluation
  endpoint must answer `/v1/tokenize` and satisfy its tokenizer/parser contract.
* Harbor's existing Open-Harness Agent cannot enable Recorder v2 through its
  current options, so the only saved artifact is context-only ATIF.
* The existing reward and trace artifacts have no shared stable identity that
  would make heuristic joining acceptable.

No smoke test was run in this pass. Running another Harbor Trial through the
unchanged Agent would reproduce the known ATIF-only result and would not close
the data-fidelity gap.

## SFT gate and upstream boundary

The `openharness-sft` adapter and TMax 2B mask implementation remain usable:
`adapters/openharness_v2.py:254-290` joins call/tool records and rewards when a
Recorder directory and Trial metadata are supplied, and
`sft/tokenization.py:81-133` rejects context-only calls, duplicate history, and
silent truncation. The real TMax 2B tokenizer check on the independent Recorder
run passed, but it has no reward and is not a positive training example.

The single smallest future interface change is an opt-in Harbor Agent setting
that chooses a Recorder directory inside the already-collected agent logs and
adds the existing `--trajectory-dir` flag to the CLI argv, while preserving the
Trial UUID/task metadata beside the downloaded Recorder bundle. That change is
outside this pass and must be reviewed in `harbor-rsi`; it is not implemented
here. Until it exists (or an equivalent existing upstream option is supplied),
do not generate a positive SFT dataset or start SFT from the Harbor run.

## Diff check

* `open-harness2`: no changes in the clean audit worktree.
* `openharness-rl`: no changes in the clean audit worktree.
* `harbor-rsi`: no changes in the clean audit worktree.
* `openharness-sft`: this report only; no upstream code, Collector, Recorder,
  Agent Loop, Harbor lifecycle, or Trainer was modified.
