# Concepts

ctower separates durable authority from replaceable execution. These terms form the shared language used by
the specification, contracts, CLI, and audit trail. Where a term appears in an API payload or a CLI flag,
this section uses the real spelling.

Start with the page that matches your question:

| Question | Page |
|---|---|
| What is a ticket, and what stays true when the worker changes? | [Ticket and lifecycle episode](tickets.md) |
| Who decides which stage comes next, and who may run it? | [Workflow revision and execution policy](workflows.md) |
| What makes "done" checkable rather than asserted? | [Proof: criteria, evidence, verdicts](proof.md) |
| Why does the Board show what it shows? | [Board lanes](board.md) |
| How is delivery progress reported without overclaiming? | [Project Delivery projection](project-delivery.md) |
| Why does a write say "committed here, acknowledgement pending", and when is it really accepted? | [Durability and acceptance](durability.md) |

## The shared vocabulary

!!! note "This section defines terms; it does not claim they are built"
    Below is the vocabulary `SPEC.md`, the contracts, and the CLI share. Several of these terms name
    designed behaviour that has no runtime here, and each one says so where it appears. For what is
    actually implemented, the linked pages carry an implementation-status section, and
    [Delivery state](../project-status.md) is the unsoftened list.

### Company and project

A **Company** is an isolation and governance boundary. It owns members, roles, secrets references,
capability policy, projects, agents, workflows, and audit history. A **Project** groups related goals and
tickets without becoming a separate source of truth.

### Ticket, status, and stage

A **Ticket** is the permanent case file for an outcome. At this revision it carries intent, acceptance
criteria, priority, ownership history, relations, evidence and verdicts, the pinned workflow run's current
stage, and the append-only hash-chained event trail. Decisions, attempts, and effects are part of the
specified case file and have no runtime here.

Two independent dimensions prevent overloaded status labels:

| Dimension | Answers | Example values |
|---|---|---|
| **Status** | What is the ticket's operational Kanban condition? | The six derived [Board lanes](board.md): `backlog`, `ready`, `in_progress`, `in_review`, `blocked`, `complete` |
| **Stage** | Which step of its selected workflow is being evaluated? | Whatever the pinned pack declares — `capture`, `frame`, `verify`, `close` in the four-stage fixture that ships |

A ticket can be blocked during any stage. Changing an assignee does not reset its identity, history, or
proof — and it cannot reset consumed attempt counters, because none exist yet. Details:
[Ticket and lifecycle episode](tickets.md).

### Workflow and execution policy

A versioned **Workflow** answers which stages exist, in what order, and which transitions are legal. The
shipped evaluator reads exactly that much: it refuses any move the graph does not declare, and refuses a
declared move whose named predicate is unmet. Which evidence advances a stage, and where failures, repairs,
escalations, and cancellations route, are specified in the workflow schema and have no runtime here.

A versioned **Execution Policy** is specified to answer which persona, capability, model, harness, and
environment may execute or review; which gates and independent perspectives are mandatory; how many review
rounds, repair attempts, and candidate generations are allowed; and which costs, timeouts, security rules,
and escalation routes apply. **None of that is evaluated at this revision.** The execution policy is pinned
to the run by reference and digest and is never read again.

Workflows define the process graph; execution policies define how a particular run is governed. Both are
versioned inputs to a ticket run, not mutable prose instructions. Details:
[Workflow revision and execution policy](workflows.md).

### Commander, agent, persona, and harness

The **Commander** is the stable accountable principal that owns orchestration until verified closure.
`commander` is one of the two principal kinds eligible to hold custody, and custody is stored as an
assignment interval outside any worker, so replacing the reasoning process does not move it. Rehydrating a
replacement Commander from that durable state is specified; no rehydration command or payload exists here.

An **Agent** is a governed worker identity. A **Persona** describes responsibility and review perspective. A
**Harness** is the execution environment—such as a local process, terminal multiplexer, or future remote
sandbox. Harness liveness never determines ticket truth. Agent profiles can be declared through
CompanyBundle; nothing runs one.

### Evidence, gates, and artifacts

An **Artifact** is an immutable or content-addressed output such as a plan, patch, test report, screenshot,
or release bundle. **Evidence** is a typed claim that links an artifact or observation to a criterion and an
exact candidate digest.

A **Gate** evaluates current evidence under policy. Passing evidence for an older candidate cannot approve a
new digest — that much is enforced. Review accounting, repair accounting, and total execution cost are
specified to remain distinct append-only facts, and none of those counters exists at this revision. Details:
[Proof: criteria, evidence, verdicts](proof.md).

### Desired state, observed state, and effects

The control plane records **desired state**—what should run, transition, or happen—and separately reconciles
**observed state** from workers and external systems. It never treats a dispatched command as proof that an
external effect occurred.

An **Effect** is a protected external mutation such as merging a change, publishing a release, sending a
message, or updating an accounting system. Effects require authorization, idempotency, receipts, and
reconciliation when the outcome is unknown. Effect brokering is specified; no effect provider is
implemented at this revision.

### Heartbeats, wakes, routines, and schedules

- A **Routine** is a versioned recurring work definition that materializes auditable runs. Routine
  revisions, triggers, and occurrences are stored, and the scheduler drives a fixed set of operations.
- A **Schedule** or cron expression determines when a routine should be considered. *Implemented for that
  fixed set.*
- A **Heartbeat** reports liveness and progress; it does not confer authority or advance a ticket by
  itself. *Specified; no heartbeat exists at this revision.*
- A **Wake** asks the control plane to reconsider desired versus observed state. *Specified; no wake exists
  at this revision.*

These concepts are deliberately separate so a missed heartbeat, delayed cron, or duplicate wake cannot
silently rewrite task history.

## Normative sources

These pages explain; they never define. For binding definitions and invariants use the
[system specification](https://github.com/simjak/ctower/blob/main/SPEC.md); for component and infrastructure
relationships use the
[architecture atlas](https://github.com/simjak/ctower/blob/main/ARCHITECTURE.md). Where an explanation here
disagrees with a contract in
[`contracts/`](https://github.com/simjak/ctower/tree/main/contracts), the contract wins and this page is a
defect.
