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

1. **`activity_class`** distinguishes `work` from `verification`. That distinction is what lets independence
   rules apply to the right stages without naming them.
2. **Every transition names a predicate.** A move whose predicate is unsatisfied is refused as
   `workflow-predicate-unsatisfied`, and the refusal body lists the `unmet_facts`. A move that the graph does
   not declare at all is refused as `workflow-transition-not-declared`.

Read those three predicates literally, because they are not the same strength:

| Transition | Predicate | What has to be true |
|---|---|---|
| `capture` → `frame` | `entry.ready@1` | The ticket has been admitted and carries no unresolved blocker that affects the board. No evidence is involved |
| `frame` → `verify` | `criteria.frozen@1` | Acceptance criteria have been frozen against a candidate digest. Still no evidence |
| `verify` → `close` | `proof.current@1` | Every frozen criterion holds evidence that has not been invalidated — bound to the current candidate digest where the criterion is candidate-dependent — plus a passing verdict wherever the criterion requires one, and a verdict can never come from the author of the evidence it judges |

Resolving and closing the ticket re-check `proof.current@1` and refuse with `proof-incomplete` if it no
longer holds. So in this workflow, proof guards the last move and the ticket's end — not each of the four
stages. A workflow in which *every* stage carries its own evidence requirement is what the
[typed evidence slots](proof.md#typed-evidence-slots) rule specifies, and that rule is not implemented.

Compare the sixteen-stage `engineering.software-factory` pack in the same directory. Same schema, same
engine, entirely different process. Its status is `draft`: publication requires typed transitions,
contracts, failure routes, invalidation, skip predicates, and conformance evidence.

## Pinning: what "start" actually does

`ticket workflow start` takes four reference/digest pairs and binds them to the run:

```text
--workflow-ref / --workflow-digest
--execution-policy-ref / --execution-policy-digest
--gate-policy-ref / --gate-policy-digest
--evidence-policy-ref / --evidence-policy-digest
```

Each ref matches `^[a-z][a-z0-9._-]*@[1-9][0-9]*$` — a key and a revision, like
`ctower.trust-spine-four-stage@1`. Each digest matches `^sha256:[0-9a-f]{64}$`.

Once pinned, the run evaluates against *those exact bytes* for its whole life. Republishing a workflow
does not silently change a ticket already in flight. A digest that does not match the pinned revision is
refused as `workflow-pin-mismatch`, which the CLI surfaces as exit `69`.

The digest is the canonical digest of the workflow graph, not the digest of the file on disk. Computing it
from the raw pack file produces a pin mismatch.

An authorized migration between revisions must name source and destination revisions, the stage mapping,
compatibility proof, invalidations, and rollback. Otherwise in-flight work stays pinned where it is.

## Run state and stage state are separate

The workflow run has its own states — `pending`, `running`, `waiting`, `succeeded`, `failed`, `cancelled` —
and each stage instance has its own: `blocked`, `ready`, `active`, `waiting_gate`, `succeeded`, `failed`,
`skipped`, `cancelled`.

A stage failure does not imply the workflow failed, and neither implies the ticket was cancelled. A failed
stage returns to `ready` only through an authorized typed repair route, which creates a new declared attempt
rather than editing the old one.

## The four configurable bounds

An execution policy declares finite bounds and a no-progress rule. The platform supplies no universal tier
table; concrete values belong to the pinned pack.

- `required_perspectives` — which independent checks must pass on one current candidate digest. A
  perspective can be any capability, not only "code review", and each one is attributable to whoever
  performed it.
- `max_nonpassing_rounds` — how many review rounds may end without every required perspective passing.
- `max_repairs_per_lineage` — how many times one line of repair work may be re-cut. A *lineage* is one chain
  of attempts descending from the same failure, as the server groups them, so this bounds "keep fixing the
  same thing".
- `max_candidate_generations` — how many versions of the work may exist in total: the first one plus every
  governed change to it, across all repair chains, so branching cannot produce an endless loop.

Separately, `total_executions` counts every check that was started, whatever its outcome. The server owns
that count, no client may write it, and it is not a limit.

A round passes when every required perspective holds a current passing verdict, with no blockers, on the
exact digest. Repeating an identical pass adds nothing.

A missing perspective, an attempt chain the server cannot place, stale evidence, an exhausted bound, or a
policy state it cannot establish all fail closed and raise exactly one escalation, not a stream of them.

## What is implemented at this revision

The generic evaluator subset that interprets `ctower.trust-spine-four-stage@1` is implemented and exercised
against real PostgreSQL: start, declared transitions, predicates, criteria freezing, evidence, verdicts,
invalidation, and server-side resolve/close.

Runner dispatch, remote execution, images, effects, and executable extensions are `not_exercised` in the
packs and are **not** implemented. Publishing new workflow packs through a supported path is not available
either; the packs in `packs/` are staged fixtures.

## Related

- [Proof](proof.md) — what the `criteria.frozen@1` and `proof.current@1` predicates are checking.
- [Ticket and lifecycle episode](tickets.md) — what the workflow is moving.
- [CLI reference](../reference/cli.md#workflow) — the exact workflow commands.
