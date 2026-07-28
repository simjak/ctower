# Workflow revision and execution policy

The most important thing to understand about ctower's workflow engine: **the software factory is data, not
a feature.**

There is no built-in "engineering process". There is a generic evaluator that reads an immutable stage graph
out of a versioned pack and refuses any move that graph does not declare. `engineering.software-factory` is
one such pack. So is the four-stage fixture the tests run. Neither is privileged by the engine.

`packs/README.md` says it plainly: *"`engineering.software-factory` is one Workflow package evaluated by the
generic Workflow Module. There is no separate Factory service or state machine."*

## The problem this solves

Hard-coded process is the reason most task tools become a straitjacket. Once "in review" is a code path
rather than a row, every team that works differently has to fight the tool, and every process change is a
deployment.

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

- `required_perspectives` — the complete set of independently attributable verdict perspectives required on
  one current candidate digest. A perspective may bind any capability; it does not mean "code review".
- `max_nonpassing_rounds` — caps review rounds where not all required perspectives pass.
- `max_repairs_per_lineage` — caps mutations per server-normalized failure lineage.
- `max_candidate_generations` — caps the initial candidate plus governed mutations across all lineages, so
  lineage fan-out cannot create an unbounded loop.

Separately, `total_executions` is an immutable server-owned count of every started perspective execution,
whatever its outcome. It is never client-authored and never a limit.

A round passes when all required perspectives hold current passing verdicts with zero blockers on the exact
digest. Repeating an identical pass does not accumulate toward anything.

Missing perspective, ambiguous lineage, stale evidence, an exhausted bound, or unknown policy state fails
closed and raises exactly one deduplicated escalation.

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
