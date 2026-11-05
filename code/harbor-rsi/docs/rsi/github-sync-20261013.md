# Harbor-RSI / OpenHarness2 GitHub integration audit

Audit date: 2026-10-13. No paid model calls or formal benchmark reruns.

## Repository state and integration

| Repository | Default / audited remote SHA | Integration |
|---|---|---|
| `CoyeCHEN/harbor-rsi` | `main`, `eac7928fe9ee1540faaf52ef639aabfc9a793159` | `codex/github-sync-harbor-hardening-20261013`, native Git merge `306636112ac2204ff60bb96eddf67ee725d33c74` of the complete hardening history onto current main |
| `NiuHechang/open-harness2` | `main`, `f033d7255b34d4aa7958d0fb3bfcb03970aaccc9` | `codex/sync-local-runtime-compat-20261013`, reviewed port `9e911bd715dbef9b4d0248aad5786ebfaaf1e7d4` |

The Token authenticates as `CoyeCHEN`; repository APIs report push/pull access
to both targets. SSH fetch/clone works separately. API branch metadata reports
both default branches as unprotected. Rulesets queries return 403 for this
Token; Harbor's protection-details endpoint also returns 403, OpenHarness's
returns 404. These responses limit visibility, not proof that every repository
policy is absent. Credentials are read only from the process environment.

Harbor's remote main does not contain `e0f89d39` or `4078add1`. Their common
ancestor is `a6f2b04dd9e98bed86d8484a2d49f220396c409c`; main has two merge
commits outside the hardening ancestry, and hardening has seven new commits.
The integration merge preserves both histories without cherry-picking or
rewriting any commit:

1. `6e209f75`: installed-agent / independent-provider lifecycle reliability.
2. `1848bae3`: frozen runtime attestation before native Job dispatch.
3. `75ff336e`: dependency inventory identity.
4. `6fe34a67`: pidfd syscall fallback with process identity preserved.
5. `e0f89d39`: audited final 4×10 campaign freeze.
6. `06ffdbb9`: H1–H9 deadline, cancellation, artifact and result fixes.
7. `4078add1`: native cancellation-chain evidence.

The merge is conflict-free and its entire tree equals `4078add1` before adding
this audit and an opt-in interface test. No default-branch source capability is
discarded. The primary worktree remains on the existing hardening branch;
its two pre-existing untracked YAML files are untouched. Integration uses the
regular worktree `/home/cky/harbor-rsi-github-sync`.

At audit time, open Harbor PR #8 (`integration/evolution-runtime-20261012`,
`afead27b2e3a1745c64bd11b8e806d1ae5027fcc`) is an independent Evolution
integration with conflicts against main. It is neither a dependency nor a
duplicate of this PR. Its code and branch are left intact; it is not silently
merged into the validated runtime or claimed to have been resolved here.

## OpenHarness source audit

`NiuHechang/main`, `RUCAIBox/main`, and all 336 tracked files in the cached
`f033d725` upstream archive agree. No upstream-main commits need synchronization.
The requested NiuHechang address is a transferred-repository alias: authenticated
metadata resolves to **`RUCAIBox/open-harness2`**, and SSH push explicitly reports
that move. These are the same repository, not two separate forks with coincident
commits. The feature branch reaches the same canonical repository through the
requested alias; PR API writes use its canonical path (alias POST returns 307).
The supplied local directory has no `.git`; it is an older 0.1.0 source copy.
Among 66 product Python files, 63 match ancestor `e742932556df78f39a7ef8f76dd381931f1d31df`.
The three differences are actual local fixes, and all 66 files match the frozen
campaign wheel. Source-copy Git ancestry/dirty state cannot be invented.

The target is 0.3.0 / API v3 with `foundation` + `rsi_modules`, Python >=3.11,
and an additional `open-harness-traces` entry. The formal campaign used 0.1.0,
SHA-256 `09c874a34f985266548292ee17acc234f30cda4b850d0b492df2c55cd4656f1f`.
Both expose `open-harness = cli:main`. A newer checkout does not change the
historical wheel identity or establish that the campaign used API v3.

Only the three local product fixes are ported, without copying the old tree:

| Local fix | Target module | Basis |
|---|---|---|
| Old `fd` option compatibility | `5-modules/capabilities/tools/find.py` | Unsupported `--no-require-git` retries once with explicit root ignore rules; unrelated failures are not retried. |
| Short-session automatic compaction | `5-modules/memory/baseline.py` | No safe cut returns no checkpoint for automatic reasons. Manual compaction and genuine summary failures remain strict; turn-based compaction and bounded overflow handling remain intact. |
| Transport disconnect classification | `foundation/ai/utils/errors.py` | Transient disconnect/read errors use existing bounded retry; credential/quota/context rules retain priority. |

There is no Git merge conflict because the local copy has no branch history.
The semantic ownership conflict is resolved in the current memory module,
without replacing its session/controller with the older implementation.
No agent-loop, CLI, prompt, tools policy, model configuration or context
retention strategy is rewritten. No Harbor orchestration enters OpenHarness.
Legacy evaluation helpers stay with the existing ownership migration rather
than being copied back into the product. Details and regressions are recorded
in OpenHarness's `docs/runtime-compatibility-sync-20261013.md`.

## Fixed-artifact validation

Harbor/Provider wheels were built from the integration merge. Their production
source equals `4078add1`; this synchronization adds only documentation and an
opt-in offline contract test. Independent wheel installs resolve `harbor` and
`harbor_remote_docker` beneath `/tmp/rsi-sync-harbor-wheel-venv/site-packages`
(with the interpreter's `lib/python3.12` prefix), not editable source paths.
That test venv borrows already-installed third-party dependencies via a `.pth`
entry; the package under test and Provider are installed from the new wheels.
No dependency declarations or lockfiles are changed.

Initial Harbor build SHA-256:
`57c69c74b0875c4be1da9a0fed47efba4da6453ec4f972ab25d4824f11e48367`.
Provider build SHA-256:
`a0ee207f59523992be89755b31031ecf2a51aacc5d5149aeafa9ccb10c938f45`.
These are new validation artifacts, not replacements for frozen r1/r2 wheels.

| Check | Result / limit |
|---|---|
| Prior Harbor critical suite from integration source | **294 passed, 18 skipped**; optional ALFWorld dependency absent |
| Same suite from installed Harbor/Provider wheels | **294 passed, 24 skipped**; the six new explicit-artifact tests skip until their wheel/CLI are supplied |
| Additional Job status, access, plan, resource and model contracts | **67 passed** |
| OpenHarness standard suite before port | 331 passed, 3 skipped due to missing `fd` |
| New regressions before port | 5 failed; original test cleanup also emitted unclosed-session errors on failed assertions |
| OpenHarness after port, with `[test,mcp]`, `rg`, local `fd` | **340 passed, 0 skipped** |
| Existing OpenHarness loopback wheel smoke, outside source imports | Pass for both separately installed 0.1.0 and candidate 0.3.0 |
| New native Job + actual wheel CLI contracts | **6 passed per wheel version** |
| Harbor Ruff check/format and diff | Pass |
| Harbor targeted `ty` for modified core, diagnostics scripts, transport and new test | Pass |
| Harbor full `ty` | Same 50 diagnostics in eight unmodified legacy/optional-provider files; full type gate is not claimed green |
| OpenHarness critical Ruff rules / compileall / diff | Pass; no repository Ruff-format/type gate configured |
| Frozen final-4x10 files against `e0f89d39` | Byte-identical; **40 cases / 42 attempts**, original failures and recovery identities retained |

No full Harbor suite, live Docker/SSH sandbox run or paid benchmark is claimed
by this audit. Provider behavior is covered by the existing offline tests.
CI may exercise broader tests and is assessed separately after PR creation.

The new test `tests/unit/rsi/test_external_cli_contract.py` consumes an explicit
wheel plus its separately installed CLI. It verifies the installed Python files
against that wheel, then uses a loopback SSE model fixture and **native Job**.
Across mounted and downloadable Provider fixtures it checks normal exit,
HTTP 400/nonzero exit, and timeout after writing a correct artifact. It verifies:

- Original UTF-8 prompt-file contents and actual task cwd.
- Model descriptor, high thinking and 65536 max-token argument propagation.
- Separate full stdout JSONL/stderr, completion-marker exit code, ATIF and
  persisted native TrialResult.
- Actual native verifier execution and exit code.
- Timeout + reward=1 together, successful process cleanup, no infrastructure
  error, and equivalent behavior across Provider capabilities.

Reproduce after building/installing the chosen OpenHarness wheel into a venv:

```bash
HARBOR_TEST_OPENHARNESS_WHEEL=/absolute/path/to/open_harness_ai.whl \
HARBOR_TEST_OPENHARNESS_CLI=/absolute/path/to/venv/bin/open-harness \
uv run --no-sync pytest tests/unit/rsi/test_external_cli_contract.py -q
```

The installation step is supplied explicitly by this opt-in test fixture;
the real adapter's installation, no-system-Python path and bootstrap behavior
remain covered by the existing installed-agent tests. This does not add a new
Job runner or mock the native verifier.

## Architecture acceptance

1. **Sandbox decoupled:** Remote Docker remains an independent optional package;
   native `BaseEnvironment` capabilities drive both tested transfer paths.
2. **New benchmarks do not require arbitrary Harbor/OpenHarness edits:** no
   task-specific core branches, answers, budget or scoring changes are added.
3. **Official Harbor chain retained:** TaskClient → Job → Trial → Environment →
   BaseInstalledAgent → Verifier → Result and native recovery remain authoritative.
   The merge retains no forced second snapshot, pidfd identity checks,
   cancellation acknowledgement, sibling isolation and H1–H9 evidence handling.
4. **Responsibilities retained:** Harbor orchestrates, OpenHarness executes the
   agent, and the Provider implements the environment. The historical timeout
   report remains applicable; legal rewards never erase AgentTimeoutError.

This synchronization requires no additional Harbor core refactor. It does not
assert that the pending independent Evolution PR, unreadable rulesets or future
CI results are already resolved.
