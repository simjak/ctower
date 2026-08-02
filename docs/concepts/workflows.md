# Workflow revision and execution policy

The most important thing to understand about ctower's workflow engine: **the software factory is data, not
a feature.**

There is no built-in "engineering process". There is a generic evaluator that reads an immutable stage graph
out of a versioned pack and refuses any move that graph does not declare. `engineering.software-factory` is
one such pack. So is the four-stage fixture the tests run. Neither is privileged by the engine.

`packs/README.md` says it plainly: *"`engineering.software-factory` is one Workflow package evaluated by the
generic Workflow Module. There is no separate Factory service or state machine."*

## The problem this solves

When a process is hard-coded, "in review" is a code path rather than a row: a team that works differently
has to work around the tool, and every change to the process is a deployment.

Splitting the graph from the engine means a workflow revision is reviewable, diffable, versioned, and
pinned — and two tickets can run different processes at the same time without branching the codebase.

## Three separate documents

| Document | Answers | Schema |
|---|---|---|
| **Workflow** | Which stages exist, which transitions are legal, which predicate guards each one, where failures route | `contracts/workflow/workflow.schema.json` |
| **Execution policy** | Which persona, capability, model, harness, and environment may execute or review; how many rounds, repairs, and candidate generations are allowed | `contracts/execution/execution-policy.schema.json` |
| **Gate policy** | Which independent verdict perspectives are required, and how proof topology is structured | `contracts/execution/gate-policy.schema.json` |

An **evidence policy** (`contracts/execution/evidence-policy.schema.json`) declares the evidence contract.
All four are pinned together when a run starts.

The table says what each document *answers*, not what the engine reads. At this revision the engine reads
the workflow graph and part of the gate and evidence policies; the execution policy is pinned and never
interpreted. [What is implemented at this revision](#what-is-implemented-at-this-revision) draws that line
exactly.

## What a workflow revision looks like

The four-stage fixture, from `packs/workflows/ctower.trust-spine-four-stage/v1.yaml`:

```json
{
  "schema": "ctower.workflow/v1",
  "key": "ctower.trust-spine-four-stage",
  "revision": 1,
  "initial_stage": "capture",
  "stages": [
    {"key": "capture", "activity_class": "work"},
    {"key": "frame",   "activity_class": "work"},
    {"key": "verify",  "activity_class": "verification"},
    {"key": "close",   "activity_class": "work"}
  ],
  "transitions": [
    {"from": "capture", "to": "frame",  "predicate_ref": "entry.ready@1"},
    {"from": "frame",   "to": "verify", "predicate_ref": "criteria.frozen@1"},
    {"from": "verify",  "to": "close",  "predicate_ref": "proof.current@1"}
  ]
}
```

Two things to notice:

1. **`activity_class`** distinguishes `work` from `verification`. What that buys today is a Board that never
   has to learn your stage vocabulary: a run sitting on any `verification` stage lands in the `in_review`
   lane. Keying independence rules to it, rather than to stage names, is specified and not built.
2. **Every transition names a predicate.** A move whose predicate is unsatisfied is refused as
   `workflow-predicate-unsatisfied`, and the refusal body lists the `unmet_facts`. A move that the graph does
   not declare at all is refused as `workflow-transition-not-declared`.

Read those three predicates literally, because they are not the same strength:

| Transition | Predicate | What has to be true |
|---|---|---|
| `capture` → `frame` | `entry.ready@1` | The ticket has been admitted and carries no unresolved blocker that affects the board. No evidence is involved |
| `frame` → `verify` | `criteria.frozen@1` | Acceptance criteria have been frozen against a candidate digest. Still no evidence |
| `verify` → `close` | `proof.current@1` | Every frozen criterion holds evidence that has not been invalidated — bound to the current candidate digest where the criterion is candidate-dependent — plus a passing verdict wherever the criterion requires one |

`proof.current@1` reads recorded facts only. Independence is not part of it: the candidate's author is
refused at the moment a verdict is *written*, and the predicate does not re-evaluate who wrote it. Which
independence is enforced, and which is not, is stated exactly under
[Verdicts and independence](proof.md#verdicts-and-independence).

Resolving and closing the ticket re-check `proof.current@1` and refuse with `proof-incomplete` if it no
longer holds. So in this workflow, proof guards the last move and the ticket's end — not each of the four
stages. A workflow in which *every* stage carries its own evidence requirement is what the
[typed evidence slots](proof.md#typed-evidence-slots) rule specifies, and that rule is not implemented.

Compare the sixteen-stage `engineering.software-factory` pack in the same directory. Same schema, same
engine, entirely different process. Its status is `draft`: publication requires typed transitions,
contracts, failure routes, invalidation, skip predicates, and conformance evidence.

## Pinning: what "start" actually does

`ticket workflow list` derives the installed, executable revisions and their digests from the local pack
tree. `ticket workflow start` takes four reference/digest pairs and binds them to the run:

```text
--workflow-ref / --workflow-digest
--execution-policy-ref / --execution-policy-digest
--gate-policy-ref / --gate-policy-digest
--evidence-policy-ref / --evidence-policy-digest
```

Each ref matches `^[a-z][a-z0-9._-]*@[1-9][0-9]*$` — a key and a revision, like
`ctower.trust-spine-four-stage@1`. Each digest matches `^sha256:[0-9a-f]{64}$`.

When discovery finds exactly one revision, `start` may omit all eight flags; the CLI expands the default
into the same exact request before encrypted spool enqueue. It never sends an unpinned start. Explicit
flags remain authoritative, must be supplied as a complete set, and retain the same mismatch refusal.

Once pinned, the run evaluates against *those exact bytes* for its whole life. Republishing a workflow
does not silently change a ticket already in flight. A digest that does not match the pinned revision is
refused as `workflow-pin-mismatch`, which the CLI surfaces as exit `69`.

The digest is the canonical digest of the workflow graph, not the digest of the file on disk. Computing it
from the raw pack file produces a pin mismatch.

There is no way to move an in-flight run to another workflow revision at this revision: no operation, CLI
command, or kernel command performs one, so a run stays on the bytes it started with. `SPEC.md` specifies
what such a migration would have to name — source and destination revisions, the stage mapping,
compatibility proof, invalidations, and rollback — and none of it is built.

## What a run actually stores

A started run is one row per ticket in `workflow_runs`
(`packages/ctower-kernel/migrations/0004_proof_workflow.sql`). It holds the pinned workflow key and
revision, the four pinned policy refs and digests, `initial_stage`, `current_stage`, the current stage's
`activity_class`, and an aggregate `version`. Each accepted move appends one immutable row to
`workflow_transition_facts` naming the source stage, destination stage, the predicate that allowed it, the
acting principal, and the client command ID.

That is the whole runtime model. A run has a current stage; it does not have a state.

!!! warning "Specified, not implemented at this revision"
    Everything in this subsection is canonical in `SPEC.md` and has no runtime object, column, or command
    here. There is no stage-instance, attempt, repair, escalation, or bound-consumption table at this
    revision, and nothing evaluates an execution policy beyond matching its pinned digest.

    **Run and stage state machines.** The workflow run is specified to have its own states — `pending`,
    `running`, `waiting`, `succeeded`, `failed`, `cancelled` — and each stage instance its own: `blocked`,
    `ready`, `active`, `waiting_gate`, `succeeded`, `failed`, `skipped`, `cancelled`. A stage failure is not
    to imply the workflow failed, and neither is to imply the ticket was cancelled. A failed stage returns
    to `ready` only through an authorized typed repair route, creating a new declared attempt rather than
    editing the old one.

    **The four configurable bounds.** An execution policy declares finite bounds and a no-progress rule. The
    platform supplies no universal tier table; concrete values belong to the pinned pack.

    - `required_perspectives` — which independent checks must pass on one current candidate digest. A
      perspective can be any capability, not only "code review", and each one is attributable to whoever
      performed it.
    - `max_nonpassing_rounds` — how many review rounds may end without every required perspective passing.
    - `max_repairs_per_lineage` — how many times one line of repair work may be re-cut. A *lineage* is one
      chain of attempts descending from the same failure, as the server groups them, so this bounds "keep
      fixing the same thing".
    - `max_candidate_generations` — how many versions of the work may exist in total: the first one plus
      every governed change to it, across all repair chains, so branching cannot produce an endless loop.

    Separately, `total_executions` is to count every check that was started, whatever its outcome, owned by
    the server, unwritable by a client, and not a limit.

    A round is to pass when every required perspective holds a current passing verdict, with no blockers, on
    the exact digest, and repeating an identical pass is to add nothing. A missing perspective, an attempt
    chain the server cannot place, stale evidence, an exhausted bound, or a policy state it cannot establish
    are all to fail closed and raise exactly one escalation rather than a stream of them.

## What is implemented at this revision

The generic evaluator subset that interprets `ctower.trust-spine-four-stage@1` is implemented and exercised
against real PostgreSQL: start, declared transitions, predicates, criteria freezing, evidence, verdicts, and
server-side resolve/close. `proof.current@1` reads the invalidated evidence and verdict sets, but nothing in
that suite changes a candidate to populate them — see [Invalidation](proof.md#invalidation).

Runner dispatch, remote execution, images, effects, and executable extensions are `not_exercised` in the
packs and are **not** implemented. Publishing new workflow packs through a supported path is not available
either; the packs in `packs/` are staged fixtures.

The execution policy is pinned and digest-checked, never interpreted. The gate policy is read only for the
criteria set and for two protections it must declare (`reviewer_kind: operator`, `self_review: forbidden`)
or be rejected. Nothing reads a bound, a perspective set, a repair route, or an escalation route.

## Related

- [Proof](proof.md) — what the `criteria.frozen@1` and `proof.current@1` predicates are checking.
- [Ticket and lifecycle episode](tickets.md) — what the workflow is moving.
- [CLI reference](../reference/cli.md#workflow-and-proof) — the exact workflow commands.
