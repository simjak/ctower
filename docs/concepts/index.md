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
| What does `durability_pending` mean, and when is a write really accepted? | [Durability and acceptance](durability.md) |

## The shared vocabulary

### Company and project

A **Company** is an isolation and governance boundary. It owns members, roles, secrets references,
capability policy, projects, agents, workflows, and audit history. A **Project** groups related goals and
tickets without becoming a separate source of truth.

### Ticket, status, and stage

A **Ticket** is the permanent case file for an outcome. It carries intent, acceptance criteria, priority,
ownership history, dependencies, artifacts, evidence, workflow state, decisions, attempts, effects, and the
append-only event trail.

Two independent dimensions prevent overloaded status labels:

| Dimension | Answers | Example values |
|---|---|---|
| **Status** | What is the ticket's operational Kanban condition? | backlog, todo, in progress, in review, blocked, done |
| **Stage** | Which step of its selected workflow is being evaluated? | think, plan, design, implement, QA, release, retro |

A ticket can be blocked during any stage. Changing an assignee does not reset its identity, history, proof,
or consumed attempt counters. Details: [Ticket and lifecycle episode](tickets.md).

### Workflow and execution policy

A versioned **Workflow** answers:

- Which stages exist and in what order?
- Which transitions are legal?
- Which evidence advances a stage?
- Where do failures, repairs, escalations, and cancellations route?

A versioned **Execution Policy** answers:

- Which persona, capability, model, harness, and environment may execute or review?
- Which gates and independent perspectives are mandatory?
- How many review rounds, repair attempts, and candidate generations are allowed?
- Which costs, timeouts, security rules, and escalation routes apply?

Workflows define the process graph; execution policies define how a particular run is governed. Both are
versioned inputs to a ticket run, not mutable prose instructions. Details:
[Workflow revision and execution policy](workflows.md).

### Commander, agent, persona, and harness

The **Commander** is the stable accountable principal that owns orchestration until verified closure. Its
reasoning process or model may be replaced, but its custody rehydrates from durable state.

An **Agent** is a governed worker identity. A **Persona** describes responsibility and review perspective. A
**Harness** is the execution environment—such as a local process, terminal multiplexer, or future remote
sandbox. Harness liveness never determines ticket truth.

### Evidence, gates, and artifacts

An **Artifact** is an immutable or content-addressed output such as a plan, patch, test report, screenshot,
or release bundle. **Evidence** is a typed claim that links an artifact or observation to a criterion and an
exact candidate digest.

A **Gate** evaluates current evidence under policy. Passing evidence for an older candidate cannot approve a
new digest. Review accounting, repair accounting, and total execution cost remain distinct append-only facts.
Details: [Proof: criteria, evidence, verdicts](proof.md).

### Desired state, observed state, and effects

The control plane records **desired state**—what should run, transition, or happen—and separately reconciles
**observed state** from workers and external systems. It never treats a dispatched command as proof that an
external effect occurred.

An **Effect** is a protected external mutation such as merging a change, publishing a release, sending a
message, or updating an accounting system. Effects require authorization, idempotency, receipts, and
reconciliation when the outcome is unknown. Effect brokering is specified; no effect provider is
implemented at this revision.

### Heartbeats, wakes, routines, and schedules

- A **Heartbeat** reports liveness and progress; it does not confer authority or advance a ticket by itself.
- A **Wake** asks the control plane to reconsider desired versus observed state.
- A **Routine** is a versioned recurring work definition that materializes auditable tickets or runs.
- A **Schedule** or cron expression determines when a routine should be considered.

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
