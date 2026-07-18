# ctower dogfood-first implementation roadmap

> **Status:** Proposed implementation sequencing
>
> **Normative authority:** [`SPEC.md`](SPEC.md)
>
> **Decision history:** [`DECISIONS.md`](DECISIONS.md)
>
> **Last reviewed:** 2026-07-18

This document proposes how to build ctower as a sequence of vertical, usable increments.
It is deliberately non-normative: it does not approve scope, change architecture, create
live tickets, or supersede the bootstrap backlog in `SPEC.md`. If this roadmap conflicts
with `SPEC.md`, the SPEC wins. A proposed increment becomes committed work only after the
operator approves it and its scope is reflected in the canonical SPEC and durable ctower
tickets.

## 1. Sequencing principle

Do not build the whole control tower and only then try it. Each increment must transfer
one real responsibility from Mission Control to ctower and prove that responsibility under
restart and failure. The source-of-truth transfer is one-way: once ctower owns a concern,
the previous system becomes read-only for that concern.

```text
┌───────────────────────────────┐
│ Mission Control builds        │
│ the bootstrap                 │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│ ctower owns TICKETS           │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│ ctower owns AGENT RUNS        │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│ ctower owns QA + GATES        │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│ ctower COMMANDER drives work  │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│ ctower deploys CTOWER         │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│ Remote runners and other      │
│ business workflows            │
└───────────────────────────────┘
```

The first usable slice is not merely “ticket creation plus assignee.” It is:

```text
ticket creation
  + durable timeline
  + accountable custody
  + current executor assignment
  + explicit result/evidence
```

Assignment must not be modeled as one overloaded `assignee_id`:

- **Custodian:** the Commander or human role accountable for bringing the ticket to a
  terminal outcome.
- **Executor:** the agent or human currently performing the work; this can change.
- **Reviewer / QA:** independent gate participants added when verification exists.
- **Runner lease:** ephemeral execution ownership; never business accountability.

## 2. Increment contract

Every phase must finish with all of the following:

1. Automated contract, integration, and end-to-end checks appropriate to the increment.
2. At least one real ctower-development ticket completed through the new capability.
3. One relevant injected failure, not only a happy-path demonstration.
4. Restart, replay, or recovery evidence for every durable claim introduced by the phase.
5. A retrospective that records escaped defects and process friction.
6. Improvement findings converted into the next durable tickets.
7. The previous source of truth made read-only for the capability transferred to ctower.

An increment is incomplete when it only renders UI, produces a passing unit test, or
records an agent self-report. The proof is a user-visible outcome backed by authoritative
events and independent evidence.

## 3. Phase 0 — walking skeleton

**Purpose:** prove the smallest durable command path before product behavior exists.

Mission Control remains the source of truth and builds this phase.

### Build

- Establish the accepted Python and browser toolchains, locks, repository gates, and CI.
- Start local PostgreSQL and run forward migrations.
- Implement a one-use bootstrap path for one company and one project.
- Seed Operator, Commander, and Engineer principals.
- Expose one authenticated command endpoint and matching `ctowerctl` command.
- Persist a command, append its event, and publish its outbox record atomically.
- Enforce idempotency keys and compare-and-swap aggregate versions.
- Add health endpoints, structured logs, traces, and minimum service metrics.

### Explicitly defer

- Board UI.
- Workflow engine.
- Agent execution.
- Generic company administration.

### Exit proof

Submit one command, terminate and restart the API, replay the record, and observe exactly
one authoritative event. The health surface must become degraded when PostgreSQL or outbox
progress stops; it must not report false green.

## 4. Phase 1 — tracking minimum working product

**Purpose:** ctower tracks the work used to build ctower.

### Build

- Create, list, inspect, update, resolve, close, and cancel tickets.
- Record every accepted mutation in an append-only ticket timeline.
- Support comments and typed artifact/reference links.
- Keep lifecycle (`open`, `resolved`, `closed`, `cancelled`) separate from projections.
- Record Commander custody separately from executor assignment.
- Assign and reassign an executor while retaining complete assignment history.
- Block and unblock a ticket with a reason, owner, and next action.
- Support the minimal accepted priority vocabulary.
- Derive the six-lane Board projection rather than storing a second generic status truth.
- Provide thin Board and Ticket pages plus CLI parity for every mutation.
- Provide bounded search and filters needed for daily dogfooding.

Company, project, and initial principals are seeded in this phase. A general company CRUD
console is not required.

```text
┌─────────────────────────────────────────────────────┐
│ CT-12  Build local runner adapter              P1   │
├─────────────────────────────────────────────────────┤
│ Lifecycle: open       Board lane: In Progress       │
│ Custodian: Commander  Executor: Engineer-Codex      │
│ Blocker: none         Workflow stage: not attached  │
├─────────────────────────────────────────────────────┤
│ Timeline                                            │
│ 10:02 ticket.created                                │
│ 10:04 executor.assigned                             │
│ 10:17 comment.added                                 │
└─────────────────────────────────────────────────────┘
```

### Dogfood gate

- Create all Phase 2 work as ctower tickets.
- Complete at least five real ctower tickets.
- Reassign at least one ticket and preserve both owners in the timeline.
- Block and unblock at least one ticket with an actionable reason.
- Restart ctower during active tracking and lose no event, comment, or assignment.

### Source-of-truth cutover

ctower becomes the ticket source of truth for the ctower project. Agents may still be
started manually; their authoritative work request and result are linked to ctower tickets.

## 5. Phase 2 — local agent execution

**Purpose:** launch one real agent from a ctower ticket and observe its complete run.

### Build

- Immutable Agent and AgentProfile revisions.
- One local Codex harness adapter.
- A tmux-backed Supervisor Adapter for process durability and operator attachment.
- Durable job states: accepted, leased, running, and explicit terminal outcomes.
- A manual **Run agent** command on an assigned ticket.
- Structured progress, logs, checkpoints, and terminal result ingestion.
- Artifact, commit, pull-request, test, and evidence references.
- Operator steer, cancel, and bounded retry commands.
- A run view showing executor, harness, environment, lease, progress, and evidence.

Do not add Commander auto-routing, remote execution, or the full software-factory workflow
yet. The first automated task should be low-risk and independently verifiable, such as a
small `ctowerctl` query.

### Exit proof

Assign a ticket, launch the local agent, deliver a typed task contract, observe progress,
and receive a commit or pull request plus test evidence and an explicit terminal result.
The ticket must remain open until a separate acceptance action; an agent saying “done” is
not an accepted ticket outcome.

### Source-of-truth cutover

ctower owns agent dispatch and run history for ctower work. Out-of-band launches are
break-glass operations and must be reconciled back to a ticket.

## 6. Phase 3 — durable execution and recovery

**Purpose:** prove that execution survives process and infrastructure failure.

### Build

- Lease heartbeats, expiry, fencing tokens, and runner incarnations.
- Cursor acknowledgment and replay for streamed run events.
- Durable checkpoints and resume contracts.
- Wake requests through the outbox, never in-memory-only scheduling.
- Reconciliation of orphan jobs, processes, leases, and workspaces.
- API, worker, runner, and supervisor restart recovery.
- Cancellation fencing so stale work cannot commit a later result.
- A watchdog surface for stuck jobs, stalled outbox delivery, and unknown state.

```text
┌───────────────┐     kill process      ┌──────────────────────┐
│ Agent working │ ────────────────────► │ Lease stops renewing │
└───────────────┘                       └──────────┬───────────┘
                                                 │ expires
                                                 ▼
                                      ┌──────────────────────┐
                                      │ Stale runner fenced  │
                                      └──────────┬───────────┘
                                                 │
                                                 ▼
                                      ┌──────────────────────┐
                                      │ New run claims job   │
                                      │ and restores state   │
                                      └──────────────────────┘
```

### Exit proof

Kill tmux and ctower worker processes during a real ticket. Recover from the last durable
checkpoint without duplicating the accepted result. Prove that the fenced runner cannot
submit progress, effects, or completion after a replacement owns the lease.

### Source-of-truth cutover

All subsequent ctower engineering execution runs through ctower.

## 7. Phase 4 — minimal verification workflow

**Purpose:** enforce one small, real feedback loop before encoding the full factory.

```text
┌────────┐    ┌───────────┐    ┌────────┐    ┌──────┐
│  Plan  │ ─► │ Implement │ ─► │ Verify │ ─► │ Done │
└────────┘    └─────▲─────┘    └───┬────┘    └──────┘
                    │              │ FAIL
                    └──────────────┘
```

### Build

- A versioned four-stage workflow definition.
- Validated transition commands and explicit failure routes.
- Ticket acceptance criteria and stage input/output contracts.
- Immutable artifact versions, evidence digests, and provenance.
- Independent QA or Review assignment; authors cannot approve their own work.
- A maximum of two repair cycles before escalation.
- Gate verdicts with findings and structured failure reasons.
- Evidence invalidation when relevant inputs change.

### Exit proof

Introduce an intentionally broken change. Verification must fail it, route the ticket back
to the executor, and retain the failed evidence. After repair, fresh QA and independent
review must pass before the ticket can enter Done.

### Source-of-truth cutover

ctower becomes authoritative for verification state and gate outcomes.

## 8. Phase 5 — Commander automation

**Purpose:** the smartest reasoning seat drives tickets to completion while bounded policy
enforces safety and independent evidence.

### Build

- Request intake and automatic Commander custody.
- Planning, decomposition, routing, and capability-based executor selection.
- Durable Commander wake and reasoning runs.
- Automatic executor assignment and legal workflow transitions.
- Risk classification and review-depth selection.
- A **Needs You** queue for genuine human judgment gates.
- Bounded retry, repair, and escalation behavior.
- Minimal immutable Persona and Skill revisions.
- Commander replacement without losing ticket or reasoning history.

```text
┌──────────────┐
│ User request │
└──────┬───────┘
       ▼
┌──────────────────────────┐
│ Commander plans + routes │
└──────┬───────────────────┘
       ▼
┌──────────────┐   findings   ┌──────────────┐
│ Implementation│ ◄────────── │ QA / Review  │
└──────┬───────┘              └──────▲───────┘
       └──────────────────────────────┘
                    pass
                      │
                      ▼
               ┌─────────────┐
               │ Merge-ready │
               └─────────────┘
```

### Exit proof

Give the Commander a real ctower feature request. It must decompose, route, recover from a
failed verification round, and reach merge-ready with no status-chasing. The target is at
most one genuine operator judgment gate, not a human approval at every transition.

## 9. Phase 6 — always-on ctower

**Purpose:** move the control plane from a developer session to durable private operation.

### Build

- Private VPS deployment with systemd-managed API, worker, reconciler, and runner.
- PostgreSQL backups plus a regularly exercised isolated restore.
- Versioned routines, cron triggers, scheduler leases, and exactly-once materialization.
- Watchdog watermarks for routines, heartbeats, outbox, reconciliation, and execution.
- Health states including explicit **STATE UNKNOWN** when proof is absent.
- Minimal Fleet, cost, usage, and failure surfaces.
- Reboot, upgrade, restore, and rollback runbooks.

### Exit proof

Reboot the VPS during active work, restore an isolated backup, prove one scheduled routine
materializes exactly once across restart, and operate continuously for at least seven days
without an unreconciled loss.

## 10. Phase 7 — full software factory

**Purpose:** expand the proven four-stage loop into the complete versioned factory.

```text
Think → Plan → Design → Implement → QA → Review
      → Docs → Release-ready → QA → Retro
```

### Build

- Office-hours and planning skills.
- Engineering and CEO plan-review gates where policy requires them.
- Design artifacts, design review, design QA, and screenshot evidence.
- Risk overlays for low, normal, high, and critical review depth.
- Independent and double-blind review where risk requires it.
- Documentation and release-readiness gates.
- Cross-stage evidence invalidation and bounded failure loops.
- Retrospectives that create durable process-improvement tickets.
- Richer workflow, ticket, evidence, and live-run UI.

### Exit proof

Run one real ctower UI or operations feature through every stage. Do not choose more
orchestration machinery as the test feature; the factory must deliver user value.

## 11. Phase 8 — self-release

**Purpose:** ctower releases ctower through controlled, auditable effects.

### Build

- Isolated release helper and Effect Broker.
- Just-in-time deployment grants and narrowly scoped credentials.
- Immutable staging and production release records.
- Deployment receipts, environment identity, and build provenance.
- Browser-driven staging and production QA.
- Automated rollback, incident creation, and release reconciliation.

```text
┌─────────────────────────────────────────────────────────────┐
│ ctower ticket                                               │
│   → ctower agent changes ctower                             │
│   → ctower QA and Review approve                            │
│   → ctower deploys itself to staging                        │
│   → ctower verifies staging                                 │
│   → ctower deploys itself to production                     │
│   → ctower verifies production                              │
│   → ctower records the retro and closes the ticket          │
└─────────────────────────────────────────────────────────────┘
```

A small build-identity endpoint, such as `/v1/meta/build`, is a suitable first self-release
because its expected production result is exact and cheap to verify.

### Exit proof

Complete the golden flow above with real staging and production URLs, signed receipts,
screenshots, rollback readiness, and a durable retrospective.

## 12. Phase 9 — remote execution

**Purpose:** run the same agent contract in separate remote environments without changing
ticket, workflow, or verification semantics.

### Build

- A second harness or target adapter proving replaceability.
- A Crabbox-compatible execution provider.
- Ephemeral sandboxes and reusable immutable custom images.
- Workspace provisioning, placement policy, and capacity admission.
- Just-in-time secret references and revocable grants.
- Remote checkpoint, log, artifact, and evidence streaming.
- Cleanup, expiry, reconciliation, and cost attribution.

### Exit proof

Run the same workflow once locally and once remotely. The kernel must observe the same
typed run and evidence contracts; only provider-specific worker details may differ.

## 13. Phase 10 — platform extensibility

**Purpose:** prove ctower is a general durable work platform after its kernel has survived
self-hosting.

### Build

- Versioned CompanyBundle administration and reconciliation.
- Agent, profile, persona, skill, and policy management.
- Capability-granted Extension Host boundaries.
- Ingress and effect adapters with explicit grants and receipts.
- Workflow and execution-policy authoring/versioning surfaces.
- An accounting workflow pack with separation of duties and approval policy.
- Routines, analytics, and domain-specific views built from projections.

```text
Capture → Classify → Reconcile → Exception Review
        → Approve → Post → Close → Retro
```

### Exit proof

Run the accounting workflow without changing the kernel state machine or granting a plugin
record-tier access. This demonstrates extensibility through contracts rather than a generic
in-process plugin system.

## 14. Deliberately not early

The following are valuable but should not precede the self-hosting ladder:

- Full company and org-chart administration UI.
- The entire ten-stage factory before the four-stage verification loop works.
- A skill or plugin marketplace.
- Remote sandboxes and custom-image management.
- Broad analytics and cost dashboards.
- A visual workflow editor.
- Production credentials or autonomous deployment authority.
- Complete Mission Control or Paperclip migration.
- Multiple business workflows.
- Public SaaS, multi-region, or high-availability topology.

## 15. Recommended first approval boundary

Approve only Phases 0 and 1 as the first delivery boundary. Before implementation:

1. Resolve the accepted priority vocabulary and six Board lanes in the canonical SPEC.
2. Keep Board lane a derived projection, not a second mutable status field.
3. Activate only the stable bootstrap ticket IDs needed for the walking skeleton and
   tracking minimum working product.
4. Create later-phase work as backlog tickets only when ctower itself can hold them.

The practical target is simple: **use ctower to track the work that adds its first agent
runner, then use ctower to run the work that adds its first verification loop.**
