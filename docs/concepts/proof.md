# Proof: criteria, evidence, verdicts, invalidation

Proof is the part of ctower that makes "done" a checkable fact rather than an assertion. It has four moving
parts, and they are deliberately not interchangeable:

```text
criterion  ──frozen against──>  candidate digest
    │                                 │
    │ evidence names a criterion      │ bound to the same digest
    ▼                                 ▼
evidence  ──judged by──>  verdict (never from the candidate's author)
                                      │
                          candidate changes → invalidation
```

## The problem

A worker says a change passes. That statement is prose about a moving target. Three things go wrong:

- The claim is not bound to *which* version passed, so a later commit silently inherits the approval.
- The claim is not bound to *what* was checked, so "tested" can mean anything.
- The claim is approved by the same principal who made it.

ctower binds the first of those, and part of the third. Evidence names an exact candidate digest, and the
principal who froze the criteria against that digest cannot record a verdict on it.

The remaining two are weaker than the list implies, and both are stated exactly below. *What* was checked is
bound only by a criterion key, not by a declared typed slot ([not implemented](#typed-evidence-slots)). And
*who may approve* is bound only against the candidate's author, not against the principal who produced the
evidence ([not enforced](#verdicts-and-independence)).

## Frozen criteria

An acceptance criterion has a stable `key` (matching `^[a-z][a-z0-9._-]*$`), a description, and two
booleans:

- `candidate_dependent` — does this criterion's proof expire when the candidate changes?
- `requires_verdict` — does it need a protected verdict on top of its evidence, or is evidence alone enough?

`ticket criteria freeze` pins the criteria set against a candidate digest at a given `--expected-version`.
The caller can supply an explicit `--candidate-digest` or literal `--candidate-content`; the CLI hashes
literal content as exact UTF-8 bytes. When exactly one executable Workflow is installed,
`--criteria-file` may be omitted and the CLI sends the criteria from that exact gate policy. The receipt
names the candidate digest that was recorded. After freezing, criteria are not edited; a second freeze is
refused as `proof-criteria-already-frozen`. This is what the workflow's `criteria.frozen@1` predicate
checks.

Freezing before evidence exists is the point. It stops the acceptance bar from being lowered to fit whatever
the worker happened to produce.

Freezing also decides who counts as the candidate's author. The HTTP route records the freezing principal as
the bundle's `candidate_author_id`, and two later commands are checked against it: only that principal may
declare a new candidate digest (`proof-candidate-author-mismatch`), and only that principal is refused from
recording a verdict (`proof-self-review-refused`).

## Evidence

`ticket evidence add` records one evidence item. The stored evidence remains fully bound:

| Field | Constraint |
|---|---|
| `evidence_id` | UUID, caller-supplied; a reused ID with different content is `proof-evidence-id-conflict` |
| `criterion_key` | Must name a frozen criterion, else `proof-criterion-unknown`; the CLI defaults the sole installed criterion |
| `candidate_digest` | `sha256:` + 64 hex; an omitted request value resolves only to the frozen current candidate, while a stale explicit value is `proof-candidate-digest-not-current` |
| `artifact_digest` | `sha256:` + 64 hex; the CLI computes an omitted value from exact UTF-8 content, while a wrong explicit value is `proof-evidence-digest-mismatch` |
| `content` | 1–100 000 characters, supplied by `--content` or read from `--content-file` |
| `expected_version` | Optimistic concurrency against the ticket |

The receipt names both the resolved current candidate and the exact artifact digest. The digest check is
real: the acceptance suite feeds deliberately corrupt content with an explicit wrong digest and asserts the
server refuses with `proof-evidence-digest-mismatch` and writes nothing.

## Typed evidence slots

!!! warning "Specified, not implemented at this revision"
    This section describes a **required rule**, not current behaviour. The evidence record that ships has no
    slot field: what runs today is the criterion/digest/verdict binding described above, and proof is required
    at the move into the last stage and at resolve and close, not at every stage. Read this section as the
    contract the implementation must meet.

Every stage that can reach `succeeded` — or an evidence-backed `skipped` — declares an ordered, nonempty
set of **required evidence slots**. A slot is a named child contract of the stage definition, not a new
aggregate and not a checklist. Each slot pins:

- a stable stage-local `slot_key` and one recognized `evidence_kind`;
- one frozen stage-scoped criterion version whose pass condition the slot helps prove;
- the required artifact or external identity fields and digest bindings;
- source, command, environment, producer-run, verifier capability and independence, trust, freshness and
  expiry, and dependency/invalidation requirements;
- whether the slot may supply stage sign-off, and the assignment kind required to do so.

The v1 evidence-kind vocabulary — prose alone never fills any of them:

| Kind | Minimum re-checkable reference |
|---|---|
| `ci-job` | CI system/repository, immutable job or run ID, conclusion, source/candidate digest, command or workflow revision, observed time |
| `image-digest` | Registry/repository identity, immutable image digest, platform, provenance/attestation reference |
| `screenshot` | Content-addressed image artifact, captured subject/route, environment, candidate/deployment digest, capture time |
| `tag` | Repository/registry, exact tag, dereferenced immutable digest, authoritative creation observation |
| `url+digest` | Exact URL/target, observed response or artifact digest, environment identity, probe/command, observed time |
| `artifact-digest` | Typed artifact identity, content digest, producer/source revision, durable object reference |
| `transcript` | Content-addressed transcript or recording with command/scenario, bounded cursor/time range, environment, subject digest |

An unknown kind fails workflow publication or evidence attachment. "E2E passed" may be *rationale* attached
to evidence; it is never the slot value.

### Slot state is derived, never patched

```text
matching current Evidence exists and contract passes  -> filled
missing / type mismatch / invalid / expired / revoked -> unfilled
source or validity cannot be established              -> unfilled (STATE_UNKNOWN)
```

The transition transaction evaluates the complete pinned slot set under the same digest snapshot as the exit
contract and the gates. Any unfilled slot produces an exact **zero-mutation** refusal naming the slot, its
kind, the owning assignment or capability, and the reason.

`failed`, `timed_out`, and `cancelled` attempts may terminate without completed slots, because they make no
success claim. They can never be projected as passed. An evidence-backed skip still has to fill its declared
skip-proof slot; a stage cannot be erased by omission.

### Slots and gates are independent

Filling every slot does not pass a required gate. A passing verdict does not fill a slot. A gate may consume
the same evidence items, but both slot completeness and valid gate instances are separately required.

### Sign-off names exactly one accountable party

The stage-success event references the digest of the complete satisfying slot set, one satisfying evidence
item chosen by the pinned signing contract, and the assignment that evidence item was recorded under.
`Evidence.verifier_principal` is the signer, and it must be the principal who held that assignment at the
time. Because the assignment already says who was acting and in what role, there is no second "who signed"
field that could drift out of sync with it. Anonymous, unmatched, expired-assignment, or prose-only sign-off
is refused.

## Verdicts and independence

`ticket gate verdict` records a `pass` or `fail` decision against a criterion and a candidate digest, with a
caller-supplied `verdict_id`. The CLI can default the sole installed criterion, and an omitted candidate
digest resolves only to the frozen current candidate. The receipt names the candidate digest used.

**The enforced rule is candidate-author independence.** `ticket criteria freeze` records the freezing
principal as the candidate's author, and recording a verdict is refused when the caller *is* that principal:

| Check when a verdict is recorded | Refusal |
|---|---|
| The caller is not the candidate's author | `proof-self-review-refused` |
| The caller holds protected operator authority | `proof-protected-authority-required` |
| The verdict names the current candidate digest | `proof-candidate-digest-not-current` |
| Current evidence exists for that criterion and digest | `proof-current-evidence-missing` |

All four checks live in `Proof._record_verdict`
(`packages/ctower-kernel/src/ctower_kernel/proof/interface.py`), and the first is proven in
`tests/acceptance/increment-1/test_four_stage_workflow.py`. Note *where* the independence check lives: it
runs when the verdict is written. The `proof.current@1` predicate re-reads the recorded verdicts but does
not re-evaluate who recorded them.

!!! warning "Not enforced at this revision: evidence-producer independence"
    Evidence stores the principal who recorded it as `producer_id`, but nothing compares that producer with
    the reviewer. A principal who is *not* the candidate's author can record evidence and then record a
    passing verdict on that same evidence, and the ticket's proof reads as current.

    The accepted design requires the stronger rule: no principal or effective agent identity that authored
    an input artifact may issue a satisfying verdict for it — together with the declared perspective
    independence (`independent_of`) that a pinned gate policy is meant to carry. Delivering that is part of
    the same specified stage-signing work as [typed evidence slots](#typed-evidence-slots). Until it lands,
    do not rely on ctower to keep a producer away from their own evidence.

The pinned gate policy does not widen any of this. It is parsed for the criteria set, and it must declare
`reviewer_kind: operator` and `self_review: forbidden` or it is rejected outright — those two values are
asserted, not configured. The richer gate topology in the accepted design, such as several required
perspectives or sealed review where reviewers cannot see each other's reports until all required verdicts
are in, is specified and has no runtime behaviour at this revision.

## Invalidation

This is the property that makes the rest worth having.

What runs at this revision is candidate-digest invalidation. Declaring a new candidate digest — which only
the principal who froze the criteria may do — adds every evidence item and every verdict recorded
against a `candidate_dependent` criterion to that ticket's invalidated set, and appends one
`candidate-digest-changed` row per affected ID. Proof recorded against criteria that are not
`candidate_dependent` is untouched. Nothing is deleted or rewritten: invalidation is an append, and the
superseded records stay readable as history.

Passing evidence for an older candidate can never approve a newer digest. That is the whole point of
`candidate_dependent`.

Two limits are worth stating exactly. The invalidated set names evidence and verdict IDs — not slots, gates,
or stage completion, none of which exist as runtime concepts here. And changing the candidate is a Proof
kernel command covered by module tests; it has no HTTP operation and no CLI command at this revision, so no
caller outside the kernel can trigger invalidation yet.

!!! warning "Specified, not implemented at this revision"
    The rest of the accepted invalidation rule has no runtime behaviour here:

    - dependency change, evidence expiry, and revocation as further invalidation sources;
    - marking exactly the affected typed slots unfilled and invalidating the gates that depended on them;
    - a prior stage-success event that **remains immutable history** while current completion validity is
      gone, so readiness, effects, resolution, and every projection treat that stage's completion proof as
      invalid;
    - repair routed through a **new declared attempt** producing fresh evidence rather than patching the old
      success.

    The Proof interface exposes freeze-criteria, record-evidence, record-verdict, and change-candidate, and
    has no slot, dependency, expiry, or revocation command.

## How projections must render slots

This is the rest of the specified slot rule, and it is not built either. When slots exist, every Board,
Ticket, and Project Delivery view that shows a stage or completion claim must include `filled / required`
slot coverage and never drop a declared slot from the denominator. A slot whose state cannot be established
must render as `unfilled (STATE_UNKNOWN)` — never as a pass, never hidden, never "absent so fine".

## Implementation status

Criteria freezing, criterion-bound evidence, operator-only verdicts, candidate-author self-review refusal,
and proof-gated resolve/close are **implemented and exercised** against real PostgreSQL in the Increment-1
acceptance suite. Candidate-digest invalidation is implemented in the Proof kernel and its persistence
writer, and is covered by module tests rather than by that suite, because no HTTP or CLI surface reaches it
yet. Evidence-producer independence and gate topology are **not** implemented — see
[Verdicts and independence](#verdicts-and-independence).

Where that gate sits is worth stating exactly: in the workflow that ships, current proof is what the move
into the final stage requires, and what resolving and closing the ticket require. The two earlier moves check
readiness and frozen criteria instead — see
[the three predicates](workflows.md#what-a-workflow-revision-looks-like).

The typed-slot structure described above is **accepted design** at this revision. The runtime/schema
implementation is explicitly out of scope of the change that introduced it. Do
not read the slot vocabulary as a shipped API surface yet.

## Related

- [Workflow revision and execution policy](workflows.md) — where slots and gate policies are declared.
- [Ticket and lifecycle episode](tickets.md) — what resolution finally records.
- [Refusal reference](../agents/refusals.md) — every `proof-*` code and what to do about it.
