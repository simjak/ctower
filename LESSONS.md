# Durable lessons

This file is append-only. Each dated entry turns observed project work into a rule and names the
artifact that makes the rule durable. `UNENCODED` means the rule still depends on memory or intent.

## 2026-08-08 — nightly dream `019fdf19-3900-7a98-8a3f-cd0c7378a6e9`

Record window: after `2026-08-07T02:00:00Z` through `2026-08-08T07:09:19+02:00`, project `ctower`
only.

### Closure evidence starts at the shipped revision

What happened → #338 was closed against a served feature-branch build, then reopened when the
merged artifact could not yet support the claim. It closed again only after PR #360 landed and QA
repeated the responsive proof against the merged revision.

Durable rule → A branch, worktree, or candidate render can qualify a change for review, but it
cannot prove that the repository's shipped state contains the behavior. Resolution and closure use
evidence whose served revision is the merged revision under claim.

Encoding → The reopen-and-reprove history is preserved on [#338](https://github.com/simjak/ctower/issues/338),
and the named closure discipline is recorded in Mission Control's
`board/ctower-migration-status.md:1785-1786,1823-1824` and
`state/crew-log.jsonl:6753-6755`.

### Caller descriptions are not authority

What happened → Review of #347 found that the first dispatch gate accepted caller-provided model
family labels. The repair copied the author fact from immutable emission state, resolved the
reviewer through the authenticated principal, and proved a forged-label refusal.

Durable rule → External and process payloads may describe an observation, never mint the authority
used to admit it. Resolve identity and policy facts from the owning substrate before mutation.

Encoding → [PR #362](https://github.com/simjak/ctower/pull/362),
[`_review_dispatch_sql.py`](packages/ctower-kernel/src/ctower_kernel/workflow/_review_dispatch_sql.py),
and Mission Control `state/crew-log.jsonl:6767-6780` carry the code, negative proof, and independent
approval.

### Project scope is a persisted grant, not a convenient label

What happened → The first #368 implementation exposed project dream effects at tenant scope and
allowed the consume path to reach checks before establishing project authority. Review held it; the
cure resolves the stored effect scope and the principal's persisted grants before any write, while
fleet effects remain operator-only.

Durable rule → Every scoped read and mutation derives scope from Record-owned identity and refuses
foreign scope before availability, policy, or state details can leak.

Encoding → [PR #374](https://github.com/simjak/ctower/pull/374),
[`_dream_dispatch_sql.py`](packages/ctower-kernel/src/ctower_kernel/runtime/_dream_dispatch_sql.py),
[`test_dream_dispatch_effect.py`](tests/acceptance/increment-1/test_dream_dispatch_effect.py), and
Mission Control
`coordination/2026-08-08_0554--review-374-delta--cures.status.md:7-33` preserve the cure and its
cross-project zero-write proof.

### A public operation and its canonical references are one candidate

What happened → Review independently held PRs #363, #367, and #374 because their public operations
were implemented before the canonical CLI and HTTP references described them. Each landed only
after the references and generated surfaces agreed with the implementation.

Durable rule → A public surface is incomplete until the same candidate carries its authored
contract, generated clients, CLI and HTTP references, and verification. Documentation is landing
evidence, not post-merge cleanup.

Encoding → [SPEC.md INV-74](SPEC.md#inv-74), [PR #363](https://github.com/simjak/ctower/pull/363),
[PR #367](https://github.com/simjak/ctower/pull/367), [PR #374](https://github.com/simjak/ctower/pull/374),
and Mission Control `state/crew-log.jsonl:6808-6832,6845-6870,6877-6888` record all three holds and
cures.

### UNENCODED — a remedy must be runnable after the explaining session is gone

What happened → A remedy described a temporary wrapper instead of delivering it at a durable path;
another project rebuilt the wrong target and the shared spool became blocked. The instance was
repaired, but the two durable prevention tickets remain open.

Durable rule → A remedy is not delivered until its executable artifact, invocation, regression
proof, and blast-radius probe are all durable and independently repeatable.

Encoding → **UNENCODED.** [#357](https://github.com/simjak/ctower/issues/357) and
[#358](https://github.com/simjak/ctower/issues/358) are still open. Owner: ctower Commander. Due:
encode the rule in the executable-remedy gate by `2026-08-08 12:00 Europe/Berlin`. Source: Mission
Control `state/escapes.jsonl:53` and `state/crew-log.jsonl:6730-6743`.

## 2026-08-10 — nightly dream `019fe43f-9500-7d4a-a387-5b35db8dceff`

Record window: after `2026-08-08T07:09:19+02:00` through replay dispatch
`2026-08-10T03:33:57Z`, project `ctower` only.

### A standing integration includes its production composition

What happened → Independent review found both the GitLab ingestion loop and the notification mirror
complete in isolation but unreachable from their real process entry points; the same rounds also found an
unleased slow poll and a single-shot outbound mutation. Durable rule → Acceptance for a standing
integration includes the actual composition root, fenced ownership, classified bounded retry, and an
end-to-end test through the real caller; a tested seam with no production caller is dark code. Encoding →
[PR #377](https://github.com/simjak/ctower/pull/377),
[PR #383](https://github.com/simjak/ctower/pull/383),
[`control_worker.py`](apps/ctower-api/src/ctower_api/control_worker.py), and Mission Control
`coordination/2026-08-08_1115--review-377-terra--gl-ingestion.status.md` plus
`coordination/2026-08-08_1627--review-383-terra--dual-rail-bridge.status.md` preserve the failures and
their production-path proofs.

### Incomplete knowledge stays incomplete through the last rendering

What happened → Portfolio review caught failed board reads becoming confirmed empty escalation and
unlinked-message counts, while send-box review caught a non-accepted durability answer becoming a
confirmed sent row. Durable rule → A projection must carry source completeness and acceptance state to
the final operator-visible branch; unavailable is not empty, and pending is not accepted. Encoding →
[PR #385](https://github.com/simjak/ctower/pull/385),
[PR #390](https://github.com/simjak/ctower/pull/390), [D45](DECISIONS.md),
[`portfolioProjection.ts`](apps/ctower-ui/src/read/portfolioProjection.ts), and
[`inboxSend.ts`](apps/ctower-ui/src/mutate/inboxSend.ts) encode the distinct unknown, pending, and
accepted paths; Mission Control review statuses `2026-08-08_2115--review-385-terra--portfolio-view.status.md`
and `2026-08-09_0530--review-390-terra--chat-sendbox.status.md` are the source.

### An extraction leaves one production path

What happened → The connector extraction first restored frozen GitLab traces through production
compatibility facades, which created a second execution path; a later round moved the historical import
shape into test-only shims and left production on the provider-neutral seam alone. Durable rule → A
behavior-preserving extraction must prove both the frozen behavior and the absence of a duplicate production
route; test adaptation may preserve old evidence, but production compatibility layers may not. Encoding →
[PR #387](https://github.com/simjak/ctower/pull/387), [D43](DECISIONS.md),
and Mission Control `coordination/2026-08-09_0209--review-387-delta2--defacade.status.md` record the
single-path result.

### An immutable ceremony needs a proven forward correction

What happened → Review held the first dream-lane binding surface because one mistaken principal-keyed
selection would have been permanent; the cure made rows immutable per principal and lane and proved a new
versioned lane from wrong bind through successful consumption. Durable rule → Before an operator is told to
perform a one-way action, the same candidate must document and exercise the exact forward-correction path.
Encoding → [PR #394](https://github.com/simjak/ctower/pull/394),
[`0058_recoverable_dream_lane_binding.sql`](packages/ctower-kernel/migrations/0058_recoverable_dream_lane_binding.sql),
and Mission Control `coordination/2026-08-09_1245--review-394-delta--recoverable-binding.status.md`
carry the recovery proof.

### Reusing a domain operation does not erase a channel boundary

What happened → The Request proposal initially grouped a future Slack/Hermes adapter with existing seat
channels under a no-new-boundary claim, repeating the connector proposal's earlier GitHub classification
error. Durable rule → Every new transport declares its own authenticated identity, credential custody,
egress, revocation, and refusal evidence even when it calls an already-authorized domain operation.
Encoding → [PR #398](https://github.com/simjak/ctower/pull/398),
[`operator-requests.md`](docs/specs/operator-requests.md), and the eight named controls in
[PR #396](https://github.com/simjak/ctower/pull/396) keep existing-seat v1 separate from both later
boundaries; source: Mission Control
`coordination/2026-08-09_1654--review-398-terra--requests-spec.status.md`.

### Governance scope includes its deterministic proof artifacts

What happened → Phase 0 prohibited generated-file changes while the same canonical SPEC adoption required
a generated manifest digest and an acceptance-denominator update, making the candidate contradict itself.
Durable rule → A governance-only scope must distinguish product implementation from deterministic
traceability output and explicitly admit every machine-owned artifact required to verify that governance
change. Encoding → [D47](DECISIONS.md),
[PR #406](https://github.com/simjak/ctower/pull/406), and Mission Control
`coordination/2026-08-10_0309--review-406-delta--phase0-cure.status.md` preserve the narrow supersession.

### First-use definitions are part of newcomer acceptance

What happened → The first fresh-eyes pass on the new concept set could follow the shipped paths but still
found core nouns used before they were explained; the repair defined each noun at first use and passed a
second cold read. Durable rule → Documentation for a first starter is not complete merely because every
claim is true: each domain term must be understandable at the point where a new reader first encounters it.
Encoding → [PR #405](https://github.com/simjak/ctower/pull/405) and Mission Control
`coordination/2026-08-10_0310--review-405-fresheyes2--gloss-cure.status.md` encode the cold-reader gate.

### UNENCODED — Request acceptance still needs executable custody

What happened → The operator's request-memory failure produced an accepted Request contract with
server-issued references, independent durable acknowledgement, read-back, and a one-way old-writer fence,
but this record window ends before any product implementation lands. Durable rule → A Request exists only
after the server owns its identity and custody and can return an honest accepted-or-pending result; a file
row or best-effort write is not the system of record. Encoding → **UNENCODED in running behavior.** D46 and
[PR #406](https://github.com/simjak/ctower/pull/406) authorize the contract; open
[#400](https://github.com/simjak/ctower/issues/400) owns the executable control. Owners: ctower Commander
and Engineer. Due: land or report the exact remaining gate by `2026-08-10 12:00 Europe/Berlin`. Source:
Mission Control `board/ctower-migration-status.md:2487-2525`.

### UNENCODED — recurring output creation must be collision-safe

What happened → The unassisted nightly emission succeeded, then its consumer stopped loudly because a
branch from an earlier run still occupied the reusable output name. Durable rule → A recurring consumer
must derive collision-safe output identity, prove any stale branch or worktree is already landed before
cleanup, preserve loud failure, and replay the same pending effects successfully. Encoding → **UNENCODED at
the record cutoff.** The repair had a spawned lifecycle row but no landed completion status. Owners: ctower
Commander and Engineer. Due: land prevention, cleanup proof, and replay evidence by
`2026-08-10 12:00 Europe/Berlin`. Source: Mission Control
`board/ctower-migration-status.md:2527` and `state/crew-log.jsonl:6833`.

### UNENCODED — executable-remedy enforcement remains open

What happened → The prior dream assigned the durable remedy rule to #357 and #358, but both tickets remain
open without a landed gate in this window. Durable rule → A negative-path remedy closes only when a durable
executable, invocation, regression, and blast-radius proof are all independently repeatable. Encoding →
**UNENCODED.** [#357](https://github.com/simjak/ctower/issues/357) and
[#358](https://github.com/simjak/ctower/issues/358) remain the owning tickets. Owner: ctower Commander.
Due: land or re-scope the executable gate by `2026-08-10 12:00 Europe/Berlin`. Source: current GitHub
read-back and the prior lesson's Mission Control citations.
