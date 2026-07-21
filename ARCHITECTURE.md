# ctower architecture atlas

| Field | Value |
|---|---|
| Status | Compact derived operator and implementer map |
| Normative authority | [`SPEC.md`](SPEC.md), version 1.8 |
| Decision history | [`DECISIONS.md`](DECISIONS.md) |
| Last reviewed | 2026-07-21 |

This is the sole terminal-safe derived architecture atlas. It explains the canonical specification; it
does not add requirements, authorize work, or define exact schemas, operations, DDL, package values, or
deployment manifests. If this file and `SPEC.md` disagree, `SPEC.md` wins and this file is stale.

Implementation labels are strict:

- **Current walking slice** means the development-only bootstrap, CP2 task/Board, and CP-1 Proof/Workflow
  fixture path implemented in this repository. It is synthetic local evidence, not a deployed or
  durability-accepted product.
- **I1** and **I2** otherwise remain committed target increments, not claims that the full behavior exists.
- **Deferred** means invariants may be recorded, but the runtime, product surface, and public Seam do not
  exist in I1/I2.

## Authority and system context

The ticket is the human join point. Postgres, immutable object metadata, and acknowledged off-host copies
hold authority. Models, sessions, processes, tmux panes, runners, and providers are replaceable capacity.

```text
  operator / admin                   signed source
  web + ctowerctl                         |
          | authenticated commands       |
          +---------------+---------------+
                          v
  +---------------- PRIVATE TRUSTED CONTROL PLANE ----------------+
  | Access + Record          authenticated append, CAS, dedupe     |
  | Catalog + Work           revisions, ticket, custody, task axes |
  | Proof + Attention        criteria, evidence, gates, Needs You  |
  | Workflow + Runtime       graph decisions, jobs, leases, replay |
  | Effects + Projections    grants/receipts, five read surfaces   |
  +-----------+-------------------+--------------------+-----------+
              |                   |                    |
              v                   v                    v
       +-------------+     +-------------+      +-------------+
       | Postgres 17 |     | digest      |      | vault/KMS   |
       | facts/outbox|     | object bytes|      | references  |
       +------+------+     +------+------+      +-------------+
              |                   |
              +---------+---------+
                        v off-host durable ACK / backup / anchors
                +------------------+
                | independent store|
                +------------------+

       committed jobs                 protected effect intent
              |                                |
              v                                v
  +-------------------------+       +-----------------------------+
  | replaceable worker plane|       | root/effect integration     |
  | runner -> CommandGuard  |       | verify grant + provenance   |
  |       -> process / tmux |       | apply -> receipt -> reconcile|
  +-------------------------+       +-----------------------------+
```

Only control-plane Modules can authorize canonical mutations. A runner can return observations,
artifacts, attestations, and requested transitions; none becomes ticket, Workflow, Proof, or delivery
truth until the owning Module validates and appends it. External systems remain authoritative for their
own effects, while ctower retains grants, receipts, and reconciliation findings.

## Deployment topology by increment

Logical Modules are not deployment units. Exact units live in `deploy/`; this atlas names only the
topology fixed by the SPEC.

The implemented development tracer currently has this narrower shape:

```text
generated Python client -> FastAPI Adapter -> Access / Work -----> Record -> Postgres 17 fixture
                                         \-> Proof ---------------> Record
                                         \-> Workflow ------------> Record
                                         \-> Projections ---------> disposable Board rows/cursor
                                              ^ injected Work-readiness + Proof-current capabilities
                                              | (no Workflow -> Work/Proof imports)
                                           composition root
```

It covers one-use first-tenant bootstrap; tenant-scoped tickets; protected custody; priority, assignment,
lifecycle/admission, blocker, and relation facts; explicit immutable Workflow/policy pins; criteria,
evidence, and verdict proof; interpreted four-stage transitions; proof-gated resolve/close; linked cursor
audit; and a rebuildable six-lane Board with loud watermarks. Record owns idempotent append, hash-chained
events, links, positions, and transactional outbox writes. Work, Proof, and Workflow own their authority
above Record; Projections replaces only disposable rows/cursors through a distinct role. Every successful
write remains `durability_pending`; there is no outbox/projection worker, off-host acknowledgement,
backup/restore proof, web surface, or production deployment.

### I1: co-located trust spine

```text
  private TLS edge
         |
         v
  +------------------------- private VPS --------------------------+
  |                                                               |
  |  +----------------------+   +-------------------------------+  |
  |  | ctower-api           |   | one application control worker|  |
  |  | command/query + auth |   | outbox, projection, scheduler |  |
  |  +----------+-----------+   | health and recovery loops     |  |
  |             |               +---------------+---------------+  |
  |             +-------------------------------+                  |
  |                    same verified control artifact              |
  |                              |                                 |
  |  +-------------+  +----------v---------+  +----------------+  |
  |  | Postgres 17 |  | digest object store|  | OTel collector |  |
  |  +-------------+  +--------------------+  +----------------+  |
  |              vault/KMS references + off-host ACK/backups       |
  +---------------------------------------------------------------+
```

I1 has no agent stage dispatch, autonomous Commander loop, runner daemon, or production effect grant.
The API composition and one control worker share one kernel artifact; Access, Record, Catalog, Work,
Proof, Attention, the limited generic Workflow evaluator, and Projections remain logical responsibilities
behind Module Interfaces. Service-per-noun units such as a separate reconciler are not implied.

### I2/target: separately deployable contract clients

```text
  web / ctowerctl
         |
         v
  +------------------------- private VPS --------------------------+
  | ctower-api deployment      control-worker deployment           |
  |          \                 /                                   |
  |           +-- exact same verified control artifact --+         |
  |                                                      |         |
  | Postgres + objects + vault refs + off-host durability |         |
  |                                                      |         |
  | ctower-runner -- local process Adapter                |         |
  |               \- local tmux Adapter                  |         |
  |                                                               |
  | ctower-release-supervisor.service  [root-owned, separate]      |
  |              | allowlisted install/switch/restart/rollback     |
  |              +--> ctower-staging.service                       |
  |              \--> ctower.service                               |
  +---------------------------------------------------------------+
```

`ctower-runner` is a protocol client with no record-tier credential. The root release supervisor stays
alive while ctower upgrades itself, independently verifies artifact bytes, signatures/attestations,
subjects, and trusted builder/workflow identity, and writes a hash-chained receipt journal. The one live
`systemd-vps/v1` integration plus its fault-injection implementation is an internal Effects boundary, not
a generalized provider Seam. Before any local Harness or Supervisor Adapter launches, invokes, or submits
an arbitrary harness command, it must enforce Runtime's current CommandGuard decision over the normalized
plan and targets.

## Deep Modules and dependency direction

```text
 authored contracts ---> generated models/clients ---> app composition roots
        |                                                    |
        +---------------------> kernel Module Interfaces <----+

 runner app ---> runner SDK ---> generated runner contracts
 systemd-vps Adapter ----------> Effects port + generated effect contracts

forbidden:
   kernel -> app, web, CLI, runner, or provider implementation
   web/CLI/runner/provider/extension -> record-tier connection
   generated output -> policy or server implementation
```

The implemented kernel dependency edges are acyclic: `Work|Proof|Workflow -> Record -> Telemetry`.
Record imports none of those owners, and Workflow imports neither Work nor Proof. The repository policy
validates edge allowlists and the entire ownership graph for cycles; composition satisfies Workflow's
structural Work-readiness and current-proof ports.

| Deep Module | Authority hidden behind its Interface |
|---|---|
| Access / Record | Authentication, authorization, idempotency-before-CAS, streams, hash chain, outbox, durability result |
| Catalog | One `VersionedComponent` lifecycle, compatibility, provenance, exact pins, future-only active pointers |
| Work | Permanent tickets, lifecycle episodes, custody, relations, priorities, blockers, typed Board intents |
| Proof | Criteria, artifacts, evidence DAG, independence, gate instances/verdicts, invalidation |
| Attention | Exact policy-qualified human actions and Needs You projection inputs |
| Workflow | Arbitrary pinned graph readiness, legal edges, policy selection, routes, bounds, terminal decisions |
| Runtime | Accepted jobs, leases, fencing, cursors, ACKs, checkpoints, versioned CommandGuard decisions, local execution composition |
| Effects | Grants, releases, provider observations, receipts, incidents, rollback, reconciliation |
| Projections | Rebuildable Home, Board, Ticket, Fleet, Analytics, watermarks, KPIs |

There is no `Factory`, `TaskManager`, status service, generic provider manager, or microservice per table.
The software factory is data interpreted by Workflow. Public Interfaces stay small; private validators,
folds, SQL, and Adapter mechanics remain local to the owning Module.

## Workflow and Execution Policy compose at runtime

```text
  immutable Workflow revision             compatible Execution Policy revision
  +----------------------------------+     +------------------------------------+
  | stages + activity metadata       |     | participants/capabilities          |
  | legal edges + parallelism        |     | mandatory stage gates              |
  | typed failure routes             |     | required review perspectives       |
  | gate locations                   |     | finite nonpass/repair/generation    |
  | terminal conditions              |     | timeouts, placement, escalation     |
  +----------------+-----------------+     +------------------+-----------------+
                   \                                      /
                    +---------------+----------------------+
                                    v
                       orchestration plan revision
                       selects only permitted options;
                       records rationale, never consumption
                                    |
                                    v
                       +-----------------------------+
                       | generic Workflow evaluator  |
                       | exact digest + current facts |
                       +--------------+--------------+
                                      |
                      +---------------+----------------+
                      |                                |
                  READY                            NOT READY
                      |                                |
             append job/transition        append exact unmet checklist;
                                           authoritative state unchanged
```

Every Workflow chooses its stage vocabulary and order. Every compatible Execution Policy chooses who
executes and reviews, which declared gates activate, and which finite bounds apply. A policy can select or
narrow declared behavior; it cannot invent a missing stage or edge. `engineering.software-factory` is the
first package, not the engine's built-in process.

A ReviewPlan is a named child revision inside its pinned Gate Policy component. The only reference form is
`<gate-policy-key>@<gate-policy-revision>#review-plans.<name>`; the parent revision/digest owns its bytes, so
the enclosing `review_plans` map name is its identity and it has no independent key, revision, status, or
`VersionedComponent`.

## Enforced verification and repair

```text
 current candidate digest
          |
          v
 [mandatory stage gates] -- fail --> typed failure lineage
          | pass                         |
          v                              v
 +---------- one terminal review round on this digest ----------+
 | dispatch every required/applicable independent perspective   |
 | each started job appends one observed total_executions fact   |
 +-------------------------------+-------------------------------+
                                 |
                +----------------+----------------+
                |                                 |
        every perspective passes          any nonpass/error/blocker
                |                                 |
                v                                 v
             ADVANCE                    nonpassing_rounds += 1
                                                  |
                                      consume stable-lineage repair
                                                  |
                              +-------------------+------------------+
                              | finite capacity                      | exhausted,
                              v                                      | no progress,
                       mutate candidate                              | deadline/quota
                       generation += 1                               v
                              |                         one deduplicated escalation;
                              +--> invalidate declared proof         stop automation
                                   -> fresh required gates/review
```

One current-digest terminal round advances exactly when every required/applicable perspective passes;
there is no generic `required_passing_rounds` field. Only a terminal nonpassing round consumes
`max_nonpassing_rounds`. Candidate generations, per-lineage repairs, and the observed execution total are
separate append-only facts and survive reassignment, restart, model change, and digest change.

`total_executions` is immutable observed audit/cost, not plan-authored capacity; ReviewPlan v1 cannot author,
cap, or reset it. Current automation terminates through nonpassing-round, per-lineage repair,
candidate-generation, no-progress, deadline, quota, and hard-safety enforcement. A future aggregate
cost/resource stop requires a real use case, a separately versioned policy component, executable semantic
validation, and actual enforcement before publication. ReviewPlan v1 deliberately defines no field or
arithmetic for that future component.

For the software-factory package, `code-review` is the base perspective and covers correctness plus
maintainability. `security` and `rendered-design` activate only when their package predicates apply.
Functional QA, documentation truth, release preflight, staging QA, production smoke/live QA, and retro
remain stage gates rather than duplicate review perspectives.

## One ticket, orthogonal state and changing owners

```text
 permanent ticket CT-42 / lifecycle episode 1
 ------------------------------------------------------------------------>
 priority facts:     P2 -------- P1 ------------------------------------->
 Board lane:         backlog -> ready -> in_progress -> in_review -> ...
 Workflow stage:     arbitrary package stage keys + activity metadata --->
 custody:            Commander C0 ================================ close
 executors:          E1 -------- E2 -------- QA1 -------- release1 ------>
 reviewers:                                  R1 / conditional S1 -------->
 runner leases:      lease7 --fenced--> lease9 -------------------------->
 delivery facts:     change_merged -> staging_verified -> production_verified
```

Reassignment closes one interval and opens another with actor, reason, command, scope, and fence result.
It does not mutate custody, priority, stage, Board lane, evidence, delivery, age, or counters. Only a
protected atomic Commander-custody transfer can replace C0, with no gap and with checkpoint/context handoff.

Canonical Board lanes are `backlog`, `ready`, `in_progress`, `in_review`, `blocked`, and `complete`.
Priority is `P0|P1|P2`. The Board derives verification from stage `activity_class`, not stage names. Merge,
staging verification, production verification, rollback, and incident remain separate typed delivery facts.

## Durable wake, Routine, and run flow

```text
 assignment / mention / gate / Routine / retry / reconciliation
                              |
                              v
              committed wake_intent + outbox
                    dedupe/coalesce/policy
                              |
                              v
                        accepted job
                              |
                   lease + fencing token
                              v
                       execution_run
                 events + ACKs + checkpoints
                              |
                              v
            explicit terminal / waiting / typed failure
                              |
                              v
                 Workflow + Proof evaluate facts
```

A trigger is why work may become due. A wake intent is the durable request. A reasoning heartbeat is the
operator-facing name for one bounded `execution_run`. A lease heartbeat renews only a current fenced
lease. A scheduler beat materializes due Routine occurrences. None substitutes for another.

Routine occurrence, concurrency/catch-up outcome, ordinary command/job, outbox row, and `next_fire_at`
commit before dispatch. One logical scheduler owns Routine truth; there is no OS cron process per agent or
Routine. Scheduler completeness, runner liveness, ticket progress, and effect/reconciliation watermarks
are independent and make health `STATE UNKNOWN` when stale.

## Guarded harness command dispatch

```text
structured execution intent
 executable + argv/shell plan + cwd + pinned environment-resolution identities
                       |
                       v
 normalize expansions / parent traversal / globs / symlinks / targets
                       |
                       v
 canonical normalized-execution-plan digest + decision/attempt identity
                       |
                       v
 versioned CommandGuard decision + immutable bound receipt
       | allow              | block             | needs_operator
       v                    v                     v
 exact plan may       zero dispatch       exact one-use, short-lived
 dispatch                                 authenticated grant or zero dispatch
       |
       v
 Adapter enforcement receipt (signed/scoped for remote execution)
       |
       v
 matching receipt required before terminal completion is accepted
```

Every registered Harness or Supervisor Adapter capable of harness command dispatch owns the same final
pre-dispatch enforcement obligation; a process, shell, or provider path that bypasses it is an
architecture/conformance failure. The policy recognizes
filesystem root/home/workspace destruction, disk wipe/format, destructive database operations, protected
history rewrite, cluster/infrastructure destruction, and equivalent supported wrappers. Safe cleanup is
proved by capability plus containment, not a command or basename exception. Raw substring matching is
insufficient because quoted issue text is not execution intent, while expansions, indirection, and
resolved targets determine the actual blast radius.

One canonical digest covers executable identity, argv or explicit shell plan, normalized cwd, each
non-secret environment reference plus its pinned version/digest, and the exact resolved target set in the
actual dispatch namespace. Every decision, grant, and local or remote enforcement receipt binds that digest
and one decision/dispatch-attempt identity plus ticket/job/run, principal, exact Harness/Supervisor/provider/
target identities, policy revision, and evaluation/enforcement time, without logging secret values or
sensitive command content. At the final boundary the Adapter dispatches from captured/pinned resolution or
re-resolves and atomically compares it. Mismatch, uncertainty, or inability to record the receipt before
dispatch means zero dispatch; receipt uncertainty after dispatch may have begun leaves completion
incomplete/`STATE UNKNOWN`, never accepted. This guard reduces accidental destruction; sandbox/VM/OS
isolation, workspace scoping, short-lived credentials, egress controls, and Effects brokerage remain the
containment boundaries for malicious arbitrary code. Exact policy/schema/signature/provider mechanics wait
for the first real Harness consumer in CT-I2-004; [issue #17](https://github.com/simjak/ctower/issues/17)
tracks that implementation.

## Disaster-safe acceptance, restore, and cutover

```text
 command transaction commits
          |
          v
 off-host record ACK obtained? ---- no ----> durability_pending
          | yes                              non-accepted; replay same key
          v
 authoritative accepted response
          |
          v
 encrypted WAL/base/object/anchor backups
          |
          v
 +---------------- isolated restore ----------------+
 | recover vault/KMS access                          |
 | verify events, chains, anchors, objects, digests  |
 | replay erasure tombstones                         |
 | load signed expected-source inventory             |
 | inactive source -> explicit not_exercised/zero     |
 | active source -> import/reconcile trusted journal |
 | missing active source -> fail closed              |
 +-------------------------+--------------------------+
                           |
             +-------------+-------------+
             |                           |
        findings remain              all reconciled
             |                           |
   reads/effects stay disabled            v
   explicit degraded state       synthetic lifecycle + runner tests
                                         |
                                         v
                                 record measured RPO/RTO
```

At the ctower-project source-of-truth barrier, accepted record truth has RPO 0 because an off-host durable
ACK precedes acceptance. A monthly restore is unusable until key recovery, object/tombstone verification,
and validation of every signed expected-source inventory entry finish. I1 inventories root/effect/provider
sources explicitly as `not_exercised` with zero-source declarations; their absence is never success. Any
missing, unreadable, or gapped activated source fails closed. I2 commits a signed inventory revision marking
a source active before the first associated grant/effect. Ordinary reads and all effects remain disabled
while any activated source is absent or unreconciled; quarantine remains degraded evidence and never turns
absence into restore success.

The cutover is therefore ordered:

```text
prove acceptance + backup + isolated restore
  -> prove CLI/UI/four-stage generic evaluator
  -> inventory and freeze ctower-project legacy writers
  -> hash/export + reviewed alias map
  -> idempotent restricted import + reconciliation
  -> atomic client rewire
  -> seal legacy inputs read-only; any later write is an incident
```

There is no dual-write period. After rewire, rollback means a compatible ctower build/restore or explicit
read-only/spool mode, never restarting legacy mutation.

## Build sequence and earned Seams

```text
I1: L0 contracts/repository gates
     -> Record + Work + Proof
     -> off-host acceptance + restore
     -> spool-backed CLI
     -> thin Home + Board + Ticket
     -> capture -> frame -> verify -> close on final generic evaluator
     -> ctower-project cutover/dogfood

I2: deepen generic Workflow + Proof
     -> durable Runtime + CommandGuard and local process/tmux recovery
     -> activate unattended Commander on the proven always-on substrate
     -> complete five surfaces + Effects/release
     -> one software-factory production golden ticket
```

The direct-process and tmux Supervisor Adapters both pass one conformance suite, so their local public Seam
is earned. The systemd release integration remains internal because one live Adapter plus a test fake does
not justify a general provider Interface. Remote execution, Crabbox, reusable custom images, warm pools,
general effect providers, and executable extensions remain deferred until a real use case and at least two
independently valuable real Adapters earn each Seam. Current evidence says `not exercised`.

## Required failure proofs

Before either increment is complete, applicable tests must show that:

1. Duplicate commands, scheduler scans, webhook retries, and outbox replay converge without duplicate truth.
2. Loss of off-host acknowledgement returns only replayable `durability_pending`.
3. API/control-worker restart, host reboot, and isolated restore lose no accepted record.
4. Reads/effects cannot enable before key, object, tombstone, signed expected-source inventory, and activated-journal reconciliation; absent sources never count as success.
5. Runner/tmux loss fences stale authority and resumes from durable state without inferred success.
6. Every registered Harness or Supervisor command-dispatch path invokes CommandGuard at final pre-dispatch;
   decision/grant/local-or-remote enforcement receipts bind one canonical normalized-execution-plan digest
   and decision/dispatch-attempt identity to the complete execution context; blocked/attention commands,
   resolution mismatch, uncertainty, replay, expiry, and pre-dispatch receipt failure execute zero times;
   post-dispatch receipt loss cannot produce accepted completion; and observability remains redacted.
7. A candidate mutation invalidates exactly dependent proof and requires fresh applicable gates/review.
8. Author/self-review, missing perspectives, invalid bounds, and stale evidence fail closed.
9. Production verification failure enters incident, revocation, containment/rollback, verification, then triage.
10. Unknown scheduler, projection, runner, backup, telemetry, or reconciliation state is visibly degraded.
11. Remote/image/extension fixtures cannot be presented as an exercised runtime or public Seam.

Tmux is useful for same-host continuity and operator visibility. Durability comes from acknowledged records,
committed events/outbox entries, fenced leases, replayable cursors, immutable evidence, checkpoints,
off-host backups, and reconciled external receipts.
