# Environment Support

RSI v1 accepts Linux, single-step tasks with no simulated user. Provider support
is initially DeepSeek using `DEEPSEEK_API_KEY`. The agent runs as the task's
declared user; installation does not grant it access to verifier-only assets.

| Backend | Use | Validation boundary |
| --- | --- | --- |
| `e2b-one-hour` | Short tasks, sandbox lifetime capped at 3600 seconds | Agent + setup + verifier + collection margin must fit |
| `e2b-resumable` | Explicit auto-pause/reconnect extension | Reconnect uses the same sandbox; never replays a command to simulate recovery |
| `e2b` | Official E2B backend | Requires an account supporting the requested lifetime |
| `docker` | Official local backend | Image availability and daemon access remain required |

Template creation can occur before the sandbox exists. In-sandbox healthcheck
and setup consume lifetime; leave sufficient collection margin beyond task
budgets. A reconnect never extends the agent task deadline. Long runs and
alternate backends require their own real acceptance evidence.

`harbor.environments.e2b_qemu_recovery:QemuRecoveryE2BEnvironment` is an optional
native-Harbor extension for the historical QEMU tasks. Its aliases refer to
prebuilt Ubuntu templates in the original account. Set
`TB_QEMU_ALPINE_TEMPLATE` / `TB_QEMU_STARTUP_TEMPLATE` to your own verified
templates and use `benchmarks/terminal_bench_2_1/scripts/probe_qemu.py` before
dispatch. Missing aliases fail rather than rebuilding the old image under the
new name. This is not automatically enabled by the RSI backend selector.

On cancel, RSI forwards SIGINT to its native Harbor subprocess and waits up to
90 seconds, then escalates to SIGTERM (15 seconds), then SIGKILL. Local process
exit does not prove remote cleanup. Cancelled summaries conservatively mark
`cleanup_unconfirmed=true`; inspect the native trial logs and provider state.
