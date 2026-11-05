# Pull request disposition

This records the review and actual PR disposition for the native-Campaign
release as of the Source5 checkpoint, commit
`2ad876b5490715d1fcc3bc7d3e17f4a7451636ca`. PR #15 was merged into main as
`ff622f3da4de3d0c753ad947200c0a5a3b9cf7fe`; PR #16 was closed after partial
adoption and superseded by PR #17. This does not claim PR #17 itself is merged.
The local integration started at `14da0266d587c124740d1ee6315d7804f8df2194`.
The fixed official Harbor merge base is
`1e5c5c6db929a10a140d05e606882c671ae20729` (`v0.23.0`).

## Decisions

| Pull request | Pinned reviewed head | Decision | Release disposition |
| --- | --- | --- | --- |
| [#15](https://github.com/CoyeCHEN/harbor-rsi/pull/15), search dependencies | `464b5023d82963d40d9e70163c34c342767f19b7` | MERGED | Merged as `ff622f3da4de3d0c753ad947200c0a5a3b9cf7fe`; keep the installation-boundary repair and do not apply it twice. |
| [#16](https://github.com/CoyeCHEN/harbor-rsi/pull/16), remote TMax study | `62d5d99b0817795c8718c7a56ffc31bd18a17663` | PARTIAL, CLOSED | The generic lifecycle/provider repairs below were integrated with focused tests; the full experimental control chain was excluded. Superseded by PR #17. |

### PR #15

The change prepares the search dependencies advertised by the installed
OpenHarness CLI. It uses the existing system-package mechanism, supports an
explicit SHA-pinned host-prepared `fd`, verifies the copied bytes, and probes
the required command-line capability. Missing packages or obsolete `fd` flags
fail installation instead of leaving advertised tools broken.

The `fd`/`fdfind` binary-name mapping is an installation concern, not a fallback
Provider or a benchmark-specific path. No Task name, official Verifier, model
loop, or scheduler rule is introduced. The reviewed search method is identical
to the integration baseline; 43 focused search/adapter contract CPU tests
passed during independent review.

### PR #16: accepted generic parts

1. **Trial final cleanup acknowledgement.** Retain one native Provider stop
   Task, wait through repeated caller cancellation, preserve failures, and
   finalize Result/END only after the stop attempt is acknowledged. The source
   review reproduced the old failure with real asyncio Tasks: the caller
   returned and marked the environment stopped while the Provider was still
   waiting. The integrated repair records failed cleanup as infrastructure
   evidence and does not mark it successfully stopped. This is separate from
   the pre-Verifier agent-process termination barrier.
2. **RemoteDocker transfer and cleanup diagnostics.** Run trusted transfer
   destination checks, directory setup, and tar commands from `/`, preserving
   Task execution cwd and official verification semantics. Record identity,
   duration, acknowledgement, and UNKNOWN outcomes around existing cleanup
   phases. Keep the existing timeout, ownership checks, removal order, and
   final absence confirmation.

The Trial follow-up is commit
`c7ae8d5fea3e810088fe3649513035b9bccfa8ec`. Provider integration is commit
`863957e0abb785e7140e7a46a3a1994fe1a3cc4d`, packaged independently as
`harbor-remote-docker==0.1.1`. It also includes the separately demonstrated
local filesystem offload/cancellation repair: archive packing, hashing,
extraction, and publication cannot starve the event loop or outlive deletion
of their temporary files. This additional repair is not attributed to PR #16.

The Provider wheel SHA-256 is
`042cf4024a870a18557d403b7353db5b5cf6592f25ba3f27534e02bac782d21e`.
Its installed runtime members matched the package and source bytes; 50 focused
Provider CPU tests, scoped Ruff/format, and Provider source type checks passed.
These identify the packaging/CPU checks; the subsequent live Stage B and
OpenHarness `.6` canary evidence below is recorded separately by actual version.

### PR #16: excluded parts

The PR contains 63 changed files, including 34 experimental TMax example files
with 7,555 added lines. That study composes native Jobs but also carries its own
Controller, claims, resource leases, tunnels, model-service startup, recovery,
and study-specific audit/statistics chain. It is not needed for the production
Campaign entry and is not imported into it.

Native model configuration passthrough already has stricter identity checks in
the integration baseline; replacing it with the older PR implementation would
discard those checks. The release keeps the current adapter behavior and does
not restore an old protocol compatibility path. Unrelated `post_start`
admission changes are also excluded from the Provider repair.

Historical study sources and artifacts remain evidence with their original
identities. Excluding them from the new production entry does not authorize
deleting frozen experiments or changing their Results. Full migrated
TMax/vLLM GPU acceptance was explicitly UNVERIFIED in the reviewed PR and is
not inferred from its CPU or transport fixtures.

## Validation interpretation

The independent PR review ran 11 pinned-source CPU tests for cleanup, native
configuration, and the pre-dispatch audit boundary, in addition to the 43
search/adapter tests. Larger counts and cross-system/live-provider runs in PR
descriptions remain historical author evidence; they were not rerun as part of
that review. Earlier billing/spending-limit annotations prevented some checks
from starting; those historical checks remain **NOT_RUN**. Later Windows
failures were actual test failures and were fixed by separating portable
contracts from Linux-only shell and POSIX durability tests. At PR #17 source
`2ad876b5490715d1fcc3bc7d3e17f4a7451636ca`, all six checks completed with
`success`: Ubuntu tests, Windows tests, lint/format, type checking, package
build, and labeler. This source-specific CI result does not retroactively
change older check outcomes or establish benchmark success.

Stage A actual native acceptance used Harbor `0.23.0+rsi.4` and the existing
Provider wheel: NOP Reward `0`, M0 Reward `1`, and M0 Recorder auditing passed.
It retains those original source identities. Stage B subsequently reached six
native terminal Results using the Harbor `bbab4f9f7f97b0c3606077f71a61429d439c33ed`
candidate and Provider `0.1.1`: M0 had two normal successes in three attempts;
all three NEW-M1 Epoch3 outcomes are infrastructure UNKNOWN, not model zeros.
The diagnostic is finished, but its model-comparison scoring coverage is
partial. No original Result or Reward was rewritten.

A separate OpenHarness `.6` canary then produced one complete normal M0
success and one complete normal NEW-M1 Epoch3 zero. Both passed Recorder and
exact-input-count versus Serving-input audits. That canary used Harbor
`d28ec97ad9e15f9266aac0c173068bd0cf3afeac`, not Source5. Current Source5
synthetic32 execution has three native Jobs with Agent-start evidence and no
completed model results yet; common30 is not READY. The planned synthetic32
and six-model common30 evaluations are not declared complete. Source5 QEMU
and SAM NOP checks were legal official zeros with confirmed cleanup; the
32/32 NOP check used the earlier `2cb8783cf5dd92be6d80770081b4f14ea8e9bbbd`
source. See [ARCHITECTURE.md](ARCHITECTURE.md) for exact wheel identities,
component boundaries and publishable sanitized-summary hashes.

Runtime orchestration evidence, including R51–H54, stays outside this published
source in `runtime-evidence`. The native Campaign entry replaces its production
invocation path. Raw prompts, Recorders, private deployment settings, and
historical result files are not included in this document or changed by these
PR decisions.
