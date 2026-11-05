# Terminal-Bench 2.1

Use the installed `open-harness` agent with the official Harbor dataset
`terminal-bench/terminal-bench-2-1`. RSI users should use the JSON entry point
in [the handoff guide](../../docs/rsi/README.md), which records wheel identity,
freezes task content and checks result completeness.

`scripts/run_smoke.sh` and `scripts/run_full.sh` are native Harbor launchers
for manual operation. Set an explicit `OPEN_HARNESS_WHEEL`; they never build
Harness. These launchers do not provide the RSI result contract.

The YAML presets require supplying the wheel with `--agent-kwarg wheel_path=...`.
Smoke uses the one-hour E2B extension. Full and recovery presets use the
resumable extension because some official task deadlines exceed one hour.
Template aliases for QEMU recovery are account-specific and must be built and
probed before use; see [environment notes](../../docs/rsi/environments.md).

`RESULTS.md` records historical runs from the source OpenHarness repository,
with their original paths and agent protocol. It is not evidence for this
Harbor revision. Current validation is recorded separately in `docs/rsi`.
