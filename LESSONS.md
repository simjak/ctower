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
