# ClawGym-Bench Harbor adapter

This adapter generates one standard Harbor task per record from the pinned
ClawGym-Bench revision `c8cbd1d0df033af24fc14064d40d6964ca8f611f`.

The agent image contains only the original prompt and non-verifier input files.
The upstream `reward/test.py`, rubric rules, and score parser are built into the
separate verifier image. The agent workspace is transferred through the declared
Harbor artifact and is graded after the agent phase.

Generate a local task set without provider access:

```bash
python adapters/clawgym/run_adapter.py \
  --dataset-path /path/to/ClawGym-Bench/data/benchmark_data.jsonl \
  --output-dir "$HOME/.cache/harbor-rsi/datasets/clawgym-full"
```

The rubric judge is intentionally not run by the offline contract tests. Tasks
with `rules` preserve those rules in verifier-only data and require a separately
configured official judge endpoint before a scored hybrid run.

Omit `--limit` to generate all 200 tasks. The CLI validates the official JSONL
SHA-256 before conversion. At this frozen revision the actual records contain
154 code-only and 46 hybrid tasks; the upstream README's 156/44 description
differs from the data. The adapter follows the records' `rules`, without
reclassifying them to match the README. Task selection also supports stable IDs.

Checker imports determine verifier-only dependency declarations. PyYAML is
installed for the official YAML checker; agent inputs and checker code remain
unchanged. `hook_code` is retained in evidence so a nonzero checker exit cannot
be reported as complete merely because it printed a numeric reward.

At runtime the separate verifier reads `CLAWGYM_JUDGE_BASE_URL`,
`CLAWGYM_JUDGE_API_KEY`, `CLAWGYM_JUDGE_MODEL`, and optionally
`CLAWGYM_JUDGE_TIMEOUT_SEC`. The API key is consumed only as verifier
environment state. The default judge model `deepseek-flash` is the selected RSI
experiment configuration, not an upstream ClawGym default. The pinned judge
request retains temperature 0.6 and max_tokens 8192.

A task with rubric rules and no configured judge retains the official
available-component fallback: a valid code score is written as the raw reward.
`official_result.json` also records `score_completeness = "incomplete"`.
This extra acceptance gate does not alter the official scoring formula, and
an incomplete result must not be reported as a complete Hybrid score. Harbor's
raw aggregate alone does not enforce this reporting gate.

`dataset.toml` contains Harbor `[[tasks]]` references with the exact digest
computed by Harbor's `Packager.compute_content_hash`; it can therefore be
published or consumed by the normal Dataset Registry workflow.
