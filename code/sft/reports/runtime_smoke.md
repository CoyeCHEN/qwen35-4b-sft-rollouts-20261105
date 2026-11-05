# DeepSeek Runtime Smoke

Date: 2026-10-13 (Asia/Shanghai)

The real API check used `GET https://api.deepseek.com/models` with the inherited
environment credential. It returned `deepseek-flash` and `deepseek-v4-pro`.
The run therefore used model ID `deepseek-flash`, the provider's OpenAI-compatible
`/chat/completions` endpoint, `stream=true`, and structured function tool calls.
The response stream contained `reasoning_content` on the first two calls and
OpenAI `tool_calls` deltas with `finish_reason=tool_calls`.

The task was an independent local development task, not a TB2.0/TB2.1 task:
the model had to read `target.txt`, append one line, and read it again. It ran
with the Recorder-enabled Open-Harness2 audit worktree at commit
`03e65d03e0575fc77b40628bf58b8d375a94fca2`, package version `open-harness-ai`
`0.3.0`, and the existing Harbor virtualenv. The command was:

```text
open-harness --print --mode json --model deepseek-flash --thinking low
  --tools bash,read --no-session --no-compaction
  --cwd /home/cky/workspace/RSI/runtime-evidence/deepseek-20261013/work
  --trajectory-dir /home/cky/workspace/RSI/runtime-evidence/deepseek-20261013/trajectory
  -p '<deterministic file verification prompt>'
```

The run completed with exit code 0 in 6.40 seconds. It made four model calls:
three `toolUse` calls followed by one `stop`, and three Bash executions. The
tool outputs were real file observations; the final file contained exactly:

```text
before
verified-by-tool
```

Recorded per-call totals were 599, 708, 766 and 881 tokens (2,954 total); the
provider reported 1,536 cached prompt tokens across calls two through four. The
exact per-call usage and provider costs are in `events.jsonl`.
No API key or authorization header appeared in the manifest or CLI stderr.

This direct run is a successful model/agent/Recorder smoke. It has no Harbor
Trial, so its reward is missing and the trajectory is not eligible as a positive
SFT sample by itself. A separate Harbor/E2B smoke on the independent
`harbor/extra-instruction-path` task later produced Reward `1.0`; that run's
ATIF output is recorded separately because the Harbor OpenHarnessAgent did not
enable Recorder v2 and therefore did not retain exact provider request payloads.
