# Harbor-RSI CI audit and fixes

Audit date: 2026-10-13. Repository: [CoyeCHEN/harbor-rsi](https://github.com/CoyeCHEN/harbor-rsi). PR: [#10](https://github.com/CoyeCHEN/harbor-rsi/pull/10), branch `codex/fix-harbor-rsi-ci`; not merged.

Baseline main is **`34584831354e59c69059ca5fb5c2e569f8ee82b8`**, merged PR #9. The fully validated implementation/PR head at this final audit snapshot is **`39f62817a32ab9e5f2c7e1ce9fe2410ec268a8c3`**. All applicable GitHub checks completed successfully after the Windows image-preparation repair. This report is published in a following documentation-only commit; its exact current head and revalidation are visible in [PR #10 checks](https://github.com/CoyeCHEN/harbor-rsi/pull/10/checks). The immutable source SHA identifies the implementation actually tested without embedding a self-referential report commit SHA.

## Diagnosis from actual main logs

| CI Job | 当前状态 | 失败 Step | 根因 | 是否历史问题 | 修复位置 |
|---|---|---|---|---|---|
| Type Check | failed | Run type checker | 47 errors across E2B and legacy RSI; optional SDK is installed | Yes, independently reproduced on latest main | Precise types, override declarations, optional narrowing |
| Windows Tests | failed | Run all tests with coverage | Four collection errors importing Linux fcntl via supervisor fixtures | Yes | Platform skips before Linux-only imports; portable shared fixture module |
| Linux Tests | failed | Runtime integration tests | Two stale example.com content assertions fail; native network checks succeed | Yes | Example runtime test fixture artifact validator |
| Ruff / Format | Not triggered on main push; preceding PR success | None | PR-only trigger differs from main push | Existing workflow design | Align PR/main triggers, locked lint environment |
| Package Build | No ordinary gate | None | Only nightly contains a build | Existing workflow design | One non-publishing build job in Python Tests |
| Nightly | failed on preceding main | Publish to PyPI | PyPI 422 invalid-publisher; fork lacks matching trusted publisher | Yes | Explicit configured release opt-in; retain nightly build |

Evidence: main [Python Tests 38367615391](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38367615391), [Type Check 38367615377](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38367615377), preceding main [Python Tests 38258011366](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38258011366), [nightly 38263570352](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38263570352). Workflow files, pyproject and lock are unchanged between preceding main `eac7928fe9ee1540faaf52ef639aabfc9a793159` and audited main: the architecture merge did not change the CI environment.

Main Linux non-runtime tests succeeded in 4m19s; runtime finished with two failures / 59 passes / one skip in 739.23s. Logs continued advancing; this was not a deadlock. Windows failed during collection after dependency installation, before any test execution. Subsequent Windows runs also advanced and completed; cancelled superseded runs are kept distinct from failures. No timed-out job or non-terminating test has been observed. Pytest's 120-second faulthandler diagnostic now prints stacks for a genuinely stalled test without changing production deadlines.

Branch metadata reports `protected=false`, and GraphQL defaultBranchRef.branchProtectionRule is null. REST protection/ruleset endpoints return HTTP 403 with the supplied token, so those detailed policy endpoints cannot be conclusively audited. The report uses actual commit check runs; no branch protection or required-check setting was changed.

## All installed workflows

| Workflow | Trigger / relevance | Actual audit outcome |
|---|---|---|
| Adapter Review | Authorized /review-adapter comment, paid review | Not triggered; no runs |
| Validate CITATION.cff | CITATION/workflow paths | Not applicable; no runs |
| Check registry.json format | Registry PR paths | Not applicable; no runs |
| Claude Code Review | Manual paid review | Not triggered; no runs |
| Claude Code | Explicit @claude interaction | Not triggered; no runs |
| Deploy Docs Preview | Authorized /deploy comment | Not triggered; no runs |
| nightly | Schedule/manual, build then configured PyPI release | Historical publish failure; repaired policy not dispatched |
| PR Diff Links | PR target open/manual | PR #10 success, run 38370224701 |
| PR Labeler | PR target synchronization/manual | Success, run 38385366922 |
| Python Tests | PR/main push/manual | Success, run 38385372804 |
| Reviewer Mentions | Non-draft PR target events | PR #10 skipped because draft; not a test failure |
| Ruff | PR; now also main push/manual | Success, run 38385372807 |
| Sync Registry to Supabase | Registry main push/manual, external write | Not triggered; no runs |
| Type Check | PR/main push | Success, run 38385372852 |
| Update Parity Summary | Adapter parity result paths on main | Not triggered; no runs |

Existing modern actions (checkout v6, setup-uv v8.1.0, github-script v9) are retained. Older checkout references in path/comment/manual workflows were inventoried but not blindly upgraded without an observed failure. No duplicate check framework was added. External write/paid review workflows were not invoked. Fork nightly still builds the viewer/distributions; publishing requires a configured matching PyPI trusted publisher and `HARBOR_PYPI_PUBLISH=true` (canonical upstream behavior is retained). This is an explicit release policy, not continue-on-error or a test gate bypass. This audit does not publish to PyPI or claim the repaired scheduled workflow has already run on main.

## Type diagnosis and repairs

CI uses Python 3.12 for ty and Python 3.13 for tests (local 3.13.16; observed Windows Actions 3.13.15). Dependencies are synchronized with `uv sync --all-packages --all-extras --locked`; ty is 0.0.49 and E2B is 2.51.0. A detached baseline worktree reproduced all 47 diagnostics. No missing optional-dependency diagnosis occurs in this exact installation; E2B and Remote Docker remain optional runtime extras.

| Baseline module | Count | Classification and correction |
|---|---:|---|
| environments/e2b.py | 13 | A: resource kwargs dictionary inferred too broadly for SDK build signature; precise optional TypedDict |
| environments/e2b_resumable.py | 7 | A: optional sandbox/workdir; describe existing sandbox guards and narrow optional workdir |
| legacy/jobbench_launch.py | 2 | C: heterogeneous JSON agent configuration mapping needs explicit value type |
| legacy/original_pi.py | 12 | A/C: five overrides, registered subclass options, optional model guard |
| legacy/results.py | 1 | C: repeated get does not narrow; bind stats once before isinstance |
| legacy/webshop_campaign.py | 12 | C: eleven dictionary generics plus heterogeneous audit assignment |

Classification B has zero baseline missing-import diagnostics after locked extras installation. Classification D has no unexplained local/CI type difference after matching versions. Legacy compatibility/reporting helpers remain shipped and checked; none are excluded. Dynamic JSON mappings use `Any` only for their existing heterogeneous payload values. No ignore-all, new per-line diagnostic suppression, rule relaxation or dependency lock update was introduced.

The original ty include list omitted Remote Docker and ATIF export sources. Adding both expands the gate and exposes **36 additional diagnostics**: nine missing generic parameters, 18 override declarations, one inherited functools.cache signature mismatch, five invalid optional stdout arguments and three optional stdout split attributes. Precise JSON generics, override decorators and casts describe the transport's existing always-captured string streams. Matching the inherited cache decorator on a constant-false capability method leaves its capability result unchanged. All five workspace source roots plus the diagnostic collector are now checked.

Two narrowly scoped source repairs have offline before/after proof:

- E2B handoff accepts a Dockerfile with no WORKDIR. Previously Filesystem.list(str) was called with None; the new optional guard retains sandbox identity and every active-command directory check. Baseline regression fails with the unwanted None call; fixed regression passes. No sandbox is started by the regression.
- OriginalPi rejects absent/malformed model names with the same explicit ValueError contract as upstream Pi before executing environment commands. Both regression cases fail against baseline and pass after the guard; valid configured behavior is unchanged.

All other source changes are type declarations/casts or equivalent narrowing. No framework changes affect model planning, retries, deadlines, cancellation, native Verifier/scoring or persisted historical results. The separate example test fixture correction is detailed below.

### Exact baseline diagnostic locations

The following immutable baseline locations count repeated SDK diagnostics individually.

| Baseline location | Diagnostic rule(s) | Count |
|---|---|---:|
| `src/harbor/environments/e2b.py:205:13` | `invalid-argument-type` × 13 | 13 |
| `src/harbor/environments/e2b_resumable.py:111:34` | `unresolved-attribute` × 1 | 1 |
| `src/harbor/environments/e2b_resumable.py:120:34` | `invalid-argument-type` × 1 | 1 |
| `src/harbor/environments/e2b_resumable.py:231:37` | `unresolved-attribute` × 1 | 1 |
| `src/harbor/environments/e2b_resumable.py:251:37` | `unresolved-attribute` × 1 | 1 |
| `src/harbor/environments/e2b_resumable.py:257:41` | `unresolved-attribute` × 1 | 1 |
| `src/harbor/environments/e2b_resumable.py:271:29` | `unresolved-attribute` × 1 | 1 |
| `src/harbor/environments/e2b_resumable.py:274:29` | `unresolved-attribute` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/jobbench_launch.py:90:34` | `invalid-argument-type` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/jobbench_launch.py:90:41` | `unsupported-operator` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/original_pi.py:36:9` | `missing-override-decorator` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/original_pi.py:39:9` | `missing-override-decorator` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/original_pi.py:43:9` | `missing-override-decorator` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/original_pi.py:45:21` | `unresolved-attribute` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/original_pi.py:48:65` | `unresolved-attribute` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/original_pi.py:52:15` | `missing-override-decorator` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/original_pi.py:56:18` | `unresolved-attribute` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/original_pi.py:80:32` | `unresolved-attribute` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/original_pi.py:82:46` | `unresolved-attribute` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/original_pi.py:83:42` | `unresolved-attribute` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/original_pi.py:99:30` | `unresolved-attribute` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/original_pi.py:132:9` | `missing-override-decorator` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/results.py:80:33` | `unresolved-attribute` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/webshop_campaign.py:43:32` | `missing-type-argument` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/webshop_campaign.py:81:17` | `invalid-assignment` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/webshop_campaign.py:85:40` | `missing-type-argument` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/webshop_campaign.py:85:53` | `missing-type-argument` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/webshop_campaign.py:85:72` | `missing-type-argument` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/webshop_campaign.py:110:13` | `missing-type-argument` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/webshop_campaign.py:110:26` | `missing-type-argument` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/webshop_campaign.py:110:68` | `missing-type-argument` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/webshop_campaign.py:140:44` | `missing-type-argument` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/webshop_campaign.py:166:6` | `missing-type-argument` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/webshop_campaign.py:248:6` | `missing-type-argument` × 1 | 1 |
| `src/harbor/extensions/rsi/legacy/webshop_campaign.py:387:22` | `missing-type-argument` × 1 | 1 |

## Platform and test reliability

Linux-only supervisor/pidfd modules skip at collection before fcntl is imported. The original shell LocalEnvironment and portable FakeAgent move to one shared fixture helper. Portable Task/Job/config/Verifier/report/deadline/reward/failure tests remain enabled on Windows. Only actual Linux shell/process tests and the single POSIX killpg test are skipped on unsupported hosts; no whole supported suite is discarded.

Actual Windows run 38373327347 completed with **3 failed, 7791 passed, 131 skipped, 64 deselected in 572.78s**. Failures were fixture portability: absent killpg, an escaped YAML Windows-path string assertion, and a background test thread failing to write U+2028 under cp1252. Fix only the POSIX test condition; parse YAML and assert the same exact volume source; encode synthetic JSONL as UTF-8. Native handoff tests remain enabled. A subsequent real Windows run exposed the consumer using cp1252 for UTF-8 JSONL (7796 passes, one Unicode assertion failure). The test workflow explicitly selects PYTHONUTF8=1 on both platforms, matching the CLI artifact encoding without weakening Unicode assertions or changing benchmark adapters. Windows legacy-codepage artifact reading is not claimed to be validated. Unclosed asyncio pipe transport warnings were also observed, but did not stall or fail jobs; they are not suppressed or presented as a repaired production bug.

Linux now collects the rewardkit, langsmith and ATIF workspace suites that explicit `pytest tests/` previously omitted. Importlib collection resolves duplicate test_runner module names without renaming/excluding tests. Explicit pytest `pythonpath = ["."]` makes repository adapter fixture imports independent of collection order; independently selected hardening tests had two collection errors before this configuration and pass afterward. Wheel smoke tests still execute outside the checkout.

Rich line wrapping depends on temporary path length. Two tests now normalize whitespace before asserting the unchanged warning text. Actual CLI path classification is preserved. Test-only LiteLLM metadata uses the locked local map; one Grok attribution fixture declares a unique synthetic model and explicit rates instead of depending on a mutable remote pricing endpoint/cache. Production pricing behavior is unchanged.

OS jobs retain their 30-minute bound and fail-fast=false isolation. Locked install precedes no-sync commands. JUnit, slow test durations and faulthandler improve evidence. Diagnostic basetemp derives from Python's real system temp directory, and its parent is created explicitly. A ZIP collector walks without following symlinks/junctions, ignores non-regular files and includes explicit JUnit and Trial result/agent/verifier/artifact logs. One ZIP is uploaded, avoiding upload-artifact recursive glob ELOOP on deliberately cyclic TaskClient fixtures. Regression tests prove ordinary evidence retention and hostile-link avoidance.

### Repair iterations retained as evidence

| Implementation / run | Linux | Windows | Interpretation |
|---|---|---|---|
| 75e34290 / 38370225727 | 2612 tmp_path errors; 5271 passed | Cancelled by newer commit | Newly introduced missing basetemp parent; fixed, not a Harbor bug |
| 16fa7fe9 / 38371714639 | 8692 passed, one CLI path assertion failed | Cancelled at 57% progress; observed same assertion | runner.temp differs from Python temp root; workflow fixed, CLI unchanged |
| 64d1a745 / 38373327347 | 8692 passed, one Rich assertion failed | Completed: three portability failures | Assertions/fixtures fixed; neither deadlock nor timeout |
| 3612556d / 38376350567 | 8697 unit passes; 59 runtime passes, two stale-content failures, one skip | 7796 passed, one Unicode assertion failed | Confirmed stale HTML fixture and cp1252 consumer; corrected |
| f6efa59d / 38378860047 | 8701 unit passes; 61 runtime passes, one skip | 7801 ordinary passes; two Windows-container passes | All OS jobs succeeded |
| ef651934 / 38382191661 | 8701 unit passes; 61 runtime passes, one skip | 7801 ordinary passes; one container fail, one pass | Cold base-image build reached native 600s boundary |
| 39f62817 / 38385372804 | 8701 unit passes; 61 runtime passes, one skip | 7801 ordinary passes; two container passes | Pinned base preparation 365s; native container pytest 57.21s |

Earlier failure artifact uploads themselves hit ELOOP; the non-following ZIP collector replaces that faulty glob. Runtime tests were not executed in the unit-failing iterations; no runtime success is attributed to those runs. Ruff/ty/build passed on the same iterations.

## Native Linux runtime root cause

Run [38376350567](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38376350567) confirms **8697 passed, 95 skipped, 61 deselected** in the Linux non-runtime phase; runtime finishes **2 failed, 59 passed, 1 skipped in 641.63s**. The repaired evidence collector succeeds: 912 regular files, artifact **11801439705** (`test-diagnostics-ubuntu-26.04`). Windows also successfully uploads 356 files (artifact **11801719425**), avoiding the earlier ELOOP.

The actual failing Trials are `shared-allowlist__TQEaRjQ` (Docker) and `shared-allowlist__ZzAUirx` (Podman). Both native results have `exception_info=null`, empty infrastructure_errors, Verifier return_code=0 and reward=0. Both `verifier/test-stdout.txt` files contain only **saved page does not look like example.com**. Their example.html files contain a valid Example Domain title but no longer contain `iana.org/domains/example`; github-status is blocked, s3-status and noaa-s3-status are reachable. No verifier allowlist/apex/phase-isolation failure is logged. The downloaded page itself warns against relying on that service for testing/monitoring.

Responsibility is the illustrative runtime fixture's stale HTML-link assertion, not Harbor orchestration, Provider, network-policy implementation or native scoring. Align its artifact identity predicate with the neighboring static allowlist fixture (Example Domain content), retaining every positive/negative DNS/TLS/phase-switch probe and every runtime reward=1 assertion. Only `examples/tasks/network-policy-matrix/dynamic/shared-allowlist/tests/test.sh` changes; its task.toml, instruction, oracle solution and budgets stay intact. No formal benchmark task or history is modified.

An offline test executes the actual inline artifact validator against previous/current valid pages, an unrelated page and an empty response. Before: **one failure, three passes**, current response rejected. After: all four pass; unrelated/empty responses remain rejected. This is a test-fixture input compatibility repair with failure evidence from two independent native providers.

## Successful Linux runtime and long-test diagnostics

Implementation `f6efa59dd7001d1b6f59d45b09f4df029b802fcb` has a successful [Linux job 115233967402](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38378860047/job/115233967402): **8701 passed, 95 skipped, 61 deselected in 267.97s** for non-runtime and **61 passed, one skipped in 729.94s** for runtime. Both formerly failing shared-allowlist cases explicitly pass (Docker at 10:01:21 UTC, Podman at 10:05:56 UTC), retaining their native Reward=1 assertions.

The new 120-second faulthandler diagnostic produced two stack dumps during `test_regrade_saved_steps_after_source_shutdown[mean]` and `[final]`, not job timeouts. The active Python stack is asyncio `selectors.select` / `run_until_complete`, with an execnet pipe-reader thread; it does not identify a lower-level I/O failure. Both tests complete successfully (124.95s and 158.69s). Inspection of their test contract confirms three native Trials per case (source plus two separate-verifier regrades), an existing 600-second test budget, immutable-source hash checks and real container teardown. No unbounded wait or deadlock is established; the diagnostic threshold is retained rather than hidden or raised.

## Local verification

| Check | Actual result |
|---|---|
| Full configured ty, Python 3.12 | Pass, all five workspace roots plus collector; 83 baseline/expanded diagnostics corrected |
| Ruff / Format / git diff --check | Pass |
| Full offline Python 3.13 suite, four roots, actual system basetemp, coverage | 8702 passed, 54 skipped, 63 deselected, 190.75s |
| Hardening/Trial/Job/Provider/pidfd/Verifier/attestation/timeout set | 297 passed, 24 skipped, 11.76s |
| Windows-fixture/collector/legacy-guard/CLI regression subset on Linux | 101 passed, 8.48s; Windows verdict separately required |
| All five workspace sdists and wheels | Built |
| Clean Harbor + optional Remote Docker wheel installation | CLI --help and native Trial/Verifier/InstalledAgent/Provider imports pass outside checkout |
| Formal OpenHarness wheel + local loopback native contracts | Six passed, 10.63s |

The six CLI cases cover two fake environment transports × normal, model_error, timeout_after_write. Installed wheel Python files match archive bytes; wheel SHA256 is **09c874a34f985266548292ee17acc234f30cda4b850d0b492df2c55cd4656f1f**. Tests retain real native Job/Trial, prompt/config forwarding, ATIF files, completion/exit evidence, timeout cleanup, Verifier exit/reward and persisted result equality. No model/provider service is contacted: every HTTP request uses a loopback fixture. They remain opt-in on Actions where the frozen wheel is unavailable.

An initial optional CLI smoke environment named /tmp/harbor-* collided with Fake Provider sandbox-path rewriting; it failed before requests. Installing under /tmp/ci-openharness-smoke gives six passes without production changes.

Safety correction retained: the first local full-suite attempt inherited an exported E2B_API_KEY and selected two live provider tests. Both creation requests were rejected with HTTP 400 (timeout above the account one-hour limit); no sandbox was created. That interrupted run is not counted as offline success. Subsequent local full suites remove credentials and exclude the live-provider integration directory. Actions retains existing conditional SDK skips when credentials are absent. No paid model, formal 40-case run, shared Docker resource operation, pruning or original TrialResult mutation occurred.

## Changed files and architectural verification

- Workflows: pytest.yml, ty.yml, ruff-format.yml, nightly.yml; no additional duplicate workflow.
- Configuration: pyproject.toml only; uv.lock and default runtime extras unchanged.
- Type/source declarations: environments/e2b.py, e2b_resumable.py; legacy/jobbench_launch.py, original_pi.py, results.py, webshop_campaign.py; Remote Docker compose.py/environment.py; ATIF convert.py/export.py/ids.py/uploaders/mlflow_protobuf.py.
- Diagnostics: scripts/collect_ci_test_artifacts.py and two unit regressions.
- Fixtures/assertions: tests/conftest.py, Grok build, CLI secret/retry tests, RSI lifecycle helper, deadline/timeout/lifecycle/pidfd/native Job/external CLI/runner/webshop/workspace bridge tests, E2B handoff and legacy model regressions.
- This report and the network-policy example test fixture: correct its outdated external HTML link requirement. Formal benchmark task definitions, time/scoring rules and historical results are untouched.

Diff verification confirms **src/harbor/trial, src/harbor/verifier, OpenHarness installed adapter, uv.lock and artifacts/benchmark-reports/final-4x10 are untouched**. OpenHarness2 is untouched. Official upstream CI checkout was compared; reasonable locked tooling and native runtime suites were retained rather than replacing Harbor-RSI workflows wholesale.

1. Sandbox remains decoupled; Remote Docker is an independent optional provider.
2. No benchmark-specific Job/Trial/Agent branches or new runner/scheduler were added.
3. TaskClient → Job → Trial → Environment → InstalledAgent → Verifier → Result remains the native chain, with existing recovery/results intact.
4. Harbor orchestrates, OpenHarness owns the Agent loop, providers own environment operations.

No further architecture refactor is needed for this CI repair.

## Actual final GitHub validation

Exact validated source SHA: **39f62817a32ab9e5f2c7e1ce9fe2410ec268a8c3**. [Python Tests 38385372804](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38385372804), [Ruff 38385372807](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38385372807), [Type Check 38385372852](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38385372852) and [PR Labeler 38385366922](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38385366922) all succeed. Commit check-runs API confirms six completed-success checks. PR remains open, draft and mergeable. Main remains **34584831354e59c69059ca5fb5c2e569f8ee82b8**; this work does not merge or retrospectively relabel the failed main runs.

Final Linux job: **8701 passed, 95 skipped, 61 deselected in 269.21s** for ordinary tests and **61 passed, one skipped in 698.29s** for runtime. Both previously failing Docker/Podman cases pass with unchanged native Reward=1 assertions. Final Windows job: **7801 passed, 132 skipped, 64 deselected in 577.93s** for ordinary tests, then **2 passed, 3 skipped, 8012 deselected in 57.21s** for native containers. The pinned-image preparation step separately succeeds in **365s** (10:55:00 → 11:01:05 UTC). All task and job limits are retained.

The following documentation-only publication commit is independently checked before handoff; its implementation tree is identical except this report. Skipped/path/comment workflows are not counted as executed tests.

| 检查 | 修复前 | 修复后 | 证据 |
|---|---|---|---|
| Ruff | PR success; not triggered on main push | success; PR/main aligned | [Lint job](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38385372807/job/115255721492) |
| Format | PR success; same trigger gap | success | Same Ruff job, formatting step |
| Type Check | failed, 47 diagnostics | success; 83 corrected, expanded coverage | [Type job](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38385372852/job/115255721549) |
| Linux Tests | two runtime failures | success; 8701 + 61 passes | [Linux job](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38385372804/job/115255720982) |
| Windows Tests | four collection errors; later cold image timeout | success; 7801 + 2 passes | [Windows job](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38385372804/job/115255721553) |
| Package Build | no ordinary gate; nightly publisher failed | success; five distributions and isolated imports | [Build job](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38385372804/job/115255721364) |

No unresolved CI code failure remains in this validated implementation. REST policy-detail reads still require additional permissions; GraphQL confirms no main branch protection rule. PyPI release still requires separately configured fork trusted publishing and is not performed here. Public network runtime fixtures retain their real DNS/TLS probes and diagnostic artifacts. Final PR checks, including the report-only publication head, are verified separately before declaring completion; PR remains unmerged.

## Repeat-run Windows infrastructure preparation failure

[Run 38382191661](https://github.com/CoyeCHEN/harbor-rsi/actions/runs/38382191661) revalidates identical implementation code (only this report changed). Linux succeeds again: 8701 ordinary passes and 61 runtime passes / one skip. Windows ordinary tests succeed again: **7801 passed, 132 skipped, 64 deselected in 517.92s**. Container phase ends **one failed, one passed, three skipped in 683.84s**; this is a failed job, not a job timeout.

Failure artifact **11805206020** contains native Trial `hello-world-bat__MSqj737`: environment_setup **10:27:04.108904 → 10:37:04.236673 UTC**, error `EnvironmentStartTimeoutError: ...600.0 seconds`, failure_phase=environment_setup, agent_setup/agent_execution/verifier=null. Exception stack shows DockerEnvironment.start → docker compose build → _collect_buffered_output → process.communicate/StreamReader.read, cancelled by Trial's existing asyncio.wait_for. Cancellation proceeds, result is persisted and the subsequent start-env test passes. No Agent deadline or scoring bug is established.

The ephemeral runner's cold pinned Microsoft Server Core base now gets an explicit preparation step before native Windows tests. Read its exact image/digest from the existing fixture Dockerfile and run docker pull with visible progress and a **15-minute step bound**, within the unchanged **30-minute job bound**. The base is a required integration-test dependency, not benchmark data. Native task.toml/build_timeout_sec=600, force_build=True, oracle/verifier budgets and assertions remain intact. Image preparation failure fails the job explicitly; tests are neither skipped nor retried. This repairs CI provisioning rather than increasing task limits or adding framework lifecycle logic. Actual before-failure evidence is retained. After-proof is run 38385372804: image preparation succeeds in 365s, then both native Windows tests pass in 57.21s; no task limit, retry, skip or scoring change is used.
