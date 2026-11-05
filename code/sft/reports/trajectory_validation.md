# Real Trajectory Validation

Raw evidence is retained outside Git at
`/home/cky/workspace/RSI/runtime-evidence/deepseek-20261013/trajectory`.
The immutable source files are `manifest.json`, `events.jsonl`, and 180
content-addressed artifact files. SHA-256 values are:

```text
manifest.json  72e9c3a66583c1f1835a19fff30adabf8b107972421d083c72985ff8adafe0f2
events.jsonl   f57ad5e58f53762e818858d6744a70f081122a4daac47ca34c1534da8715ce51
```

Recorder schema is `open-harness-rollout-v2`. The journal has one run, four
`call_start`/`call_payload`/`call_end` groups, three tool start/prepared/raw/end
groups, and one run end. The adapter resolved and verified every artifact hash,
sequence number, call ID, tool execution ID, and call/tool pairing.

The canonical file is
`/home/cky/workspace/RSI/runtime-evidence/deepseek-20261013/canonical.jsonl`.
It has trajectory ID `7f45f882-1eb3-41f8-bea2-bc4cd2fd43cb`, status
`completed`, four calls, three Bash calls, and three observations. Each call
retains the exact request context from that model request. The contexts contain
1, 3, 5, and 7 messages respectively; they were not reconstructed by
concatenating complete histories. The request payload was recorded for all four
calls, so fidelity is `provider_payload` in the canonical rows.

Tool IDs, names, JSON arguments, and raw execution records are present. The
model-visible observation is separately preserved in the next request's `tool`
message; the raw recorder result remains in `tool_observations`. The adapter
parses JSON argument strings into objects for the student chat template and
rejects malformed arguments rather than inventing them. The target TMax format
does not encode OpenAI call IDs in rendered XML, so IDs remain canonical metadata
and validation keys while the rendered student protocol is the audited implicit
single Bash-call protocol.

There is no `task_id`, `trial_id`, or verifier result in this direct local run.
Reward is therefore `missing`, not zero. This local Recorder-v2 run remains the
authoritative full-context sample for the adapter and tokenizer checks.

A separate, non-TB Harbor/E2B smoke was subsequently run with the same audited
Open-Harness commit packaged as wheel `open_harness_ai-0.3.0` (SHA-256
`05bcd684f8c37beaa280927248dbb239f79807fe33e43cfb47b3d8e2c7851b83`). Its
evidence is under:

```text
/home/cky/workspace/RSI/runtime-evidence/deepseek-20261013/harbor-job/
```

The Harbor job ID is `84d3c3bb-82c4-4952-9952-a278d199835c`; the Trial UUID is
`b67b50db-82cd-4fdb-87e7-8661c3e1dcc9`, task is
`harbor/extra-instruction-path`, and the task checksum is
`0aa8f1c7f40bbefa8bab6b3d2731595f31a10491588e2d2bb9647cb93e98b607`. The
official verifier wrote `1` to `verifier/reward.txt`, and Harbor recorded
`verifier_result.rewards.reward=1.0`. The result has no infrastructure or agent
exception, and the downloaded ATIF trajectory contains two model calls, one
Write tool call, one tool observation, and a normal completion.

The Harbor OpenHarnessAgent currently invokes the CLI without
`--trajectory-dir`, so this Trial has no Recorder-v2 `manifest.json`/
`events.jsonl`. ATIF preserves the user message, assistant outputs, tool call,
and observation, but it does not preserve the exact provider request payload,
system prompt, or tool definitions. It is therefore `context_only` evidence:
the Reward association is valid, but the ATIF file is not accepted as an SFT
sample by the current tokenizer gate. The machine-readable reward join and
hashes are in
`/home/cky/workspace/RSI/runtime-evidence/deepseek-20261013/harbor-reward-association.json`.
