# Proof: criteria, evidence, verdicts, invalidation

Proof is the part of ctower that makes "done" a checkable fact rather than an assertion. It has four moving
parts, and they are deliberately not interchangeable:

```text
criterion  ──frozen against──>  candidate digest
    │                                 │
    │ evidence names a criterion      │ bound to the same digest
    ▼                                 ▼
evidence  ──judged by──>  verdict (from an independent principal)
                                      │
                          candidate changes → invalidation
```

## The problem

A worker says a change passes. That statement is prose about a moving target. Three things go wrong:

- The claim is not bound to *which* version passed, so a later commit silently inherits the approval.
- The claim is not bound to *what* was checked, so "tested" can mean anything.
- The claim is approved by the same principal who made it.

ctower binds all three. Evidence names an exact candidate digest and cannot be approved by its own author.
The third binding — evidence filling a *declared typed slot* — is required by `SPEC.md` and is
[not implemented at this revision](#typed-evidence-slots).

## Frozen criteria

An acceptance criterion has a stable `key` (matching `^[a-z][a-z0-9._-]*$`), a description, and two
booleans:

- `candidate_dependent` — does this criterion's proof expire when the candidate changes?
- `requires_verdict` — does it need an independent human or agent verdict, or is evidence alone enough?

`ticket criteria freeze` pins the criteria set against `--candidate-digest` at a given
`--expected-version`. After freezing, criteria are not edited; a second freeze is refused as
`proof-criteria-already-frozen`. This is what the workflow's `criteria.frozen@1` predicate checks.

Freezing before evidence exists is the point. It stops the acceptance bar from being lowered to fit whatever
the worker happened to produce.

## Evidence

`ticket evidence add` records one evidence item. Every field is required:

| Field | Constraint |
|---|---|
| `evidence_id` | UUID, caller-supplied; a reused ID with different content is `proof-evidence-id-conflict` |
| `criterion_key` | Must name a frozen criterion, else `proof-criterion-unknown` |
| `candidate_digest` | `sha256:` + 64 hex; must be the current candidate, else `proof-candidate-digest-not-current` |
| `artifact_digest` | `sha256:` + 64 hex; must match the supplied content, else `proof-evidence-digest-mismatch` |
| `content` | 1–100 000 characters, read from `--content-file` |
| `expected_version` | Optimistic concurrency against the ticket |

The digest check is real: the acceptance suite feeds deliberately corrupt content and asserts the server
refuses with `proof-evidence-digest-mismatch` and writes nothing.

## Typed evidence slots

!!! warning "Specified, not implemented at this revision"
    This section describes a **required rule**, not current behaviour. It is canonical in `SPEC.md` as
    `INV-61`, `INV-62`, and `AC-EVD-07`. The evidence record that ships has no slot field: what runs today is
    the criterion/digest/verdict binding described above, and proof is required at the move into the last
    stage and at resolve and close, not at every stage. Read this section as the contract the implementation
    must meet.

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
caller-supplied `verdict_id`.

The author of the evidence cannot record its verdict. Trying is refused as `proof-self-review-refused` —
proven in `tests/acceptance/increment-1/test_four_stage_workflow.py`. A pinned gate policy may require more:
several independent perspectives, or sealed review where reviewers cannot see each other's reports until all
required verdicts are in.

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
    The rest of the invalidation rule is canonical in `SPEC.md` and has no runtime behaviour here:

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

Criteria freezing, criterion-bound evidence, protected verdicts, self-review refusal, and proof-gated
resolve/close are **implemented and exercised** against real PostgreSQL in the Increment-1 acceptance suite.
Candidate-digest invalidation is implemented in the Proof kernel and its persistence writer, and is covered
by module tests rather than by that suite, because no HTTP or CLI surface reaches it yet.

Where that gate sits is worth stating exactly: in the workflow that ships, current proof is what the move
into the final stage requires, and what resolving and closing the ticket require. The two earlier moves check
readiness and frozen criteria instead — see
[the three predicates](workflows.md#what-a-workflow-revision-looks-like).

The typed-slot structure described above is **canonical specification** at this revision: `SPEC.md` requires
it, and the runtime/schema implementation is explicitly out of scope of the commit that introduced it. Do
not read the slot vocabulary as a shipped API surface yet.

## Related

- [Workflow revision and execution policy](workflows.md) — where slots and gate policies are declared.
- [Ticket and lifecycle episode](tickets.md) — what resolution finally records.
- [Refusal reference](../agents/refusals.md) — every `proof-*` code and what to do about it.
