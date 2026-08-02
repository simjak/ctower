# ctower architecture atlas

| Field | Value |
|---|---|
| Status | Compact derived operator and implementer map |
| Normative authority | [`SPEC.md`](SPEC.md), version 1.12 |
| Decision history | [`DECISIONS.md`](DECISIONS.md) |
| Last reviewed | 2026-08-02 |

This is the sole terminal-safe derived architecture atlas. It explains the canonical specification; it
does not add requirements, authorize work, or define exact schemas, operations, DDL, package values, or
deployment manifests. If this file and `SPEC.md` disagree, `SPEC.md` wins and this file is stale.

Implementation labels are strict:

- **Current walking slice** means the development-only bootstrap, CP2 task/Board, CP-1 Proof/Workflow,
  CP3-A durability-authority fixture, CP3-B deterministic scheduler/accepted-outbox/health paths, and
  accepted project-scoped typed event feed implemented in this repository. They are synthetic local
  evidence, not a deployed product.
- **I1** and **I2** otherwise remain committed target increments, not claims that the full behavior exists.
- **Deferred** means invariants may be recorded, but the runtime, product surface, and public Seam do not
  exist in I1/I2.

Authority milestones are deliberately separate. The fresh-database Company / Project / checkpoint
hierarchy and Project Delivery projection form the development pilot. The complete legacy corpus remains a
signed read-only provenance archive; only an exact reviewed still-actionable set is recreated through
ordinary generated API/CLI commands with stable aliases. Bulk import is dormant. CT-I1-008 may issue
development `GO_WITH_LIMITS` while CP3-D is red, but full normative I1 exit remains `NO-GO` and CT-I2-001
remains unauthorized until external-failure-domain acknowledgement, key recovery, isolated destructive
restore, and measured RPO/RTO pass.

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
generated Python client -> FastAPI Adapter -> Access / Work -----> Record -> Postgres 17 primary fixture
                                         \-> Proof ---------------> Record
                                         \-> Workflow ------------> Record
                                         \-> Projections ---------> stored disposable Board reads
                                              ^ injected Work-readiness + Proof-current capabilities
                                              | (no Workflow -> Work/Proof imports)
                                           composition root
                                                  |
                                   same-artifact control worker
                                   Routine scans + accepted outbox fold
                                                                    |
                                              named test-only hot standby (`remote_apply` ACK)
```

It covers one-use first-tenant bootstrap; tenant-scoped tickets; protected custody; priority, assignment,
lifecycle/admission, blocker, and relation facts; explicit immutable Workflow/policy pins; criteria,
evidence, and verdict proof; interpreted four-stage transitions; proof-gated resolve/close; linked cursor
audit; three fixed Routine revisions; an accepted-only, rebuildable six-lane Board; immutable delivery and
poison evidence; canonical, acceptance-gated recovery dispositions; and contributor-level health. Record owns idempotent append, hash-chained
events, links, positions, transactional outbox writes, canonical command roots, subject durability heads,
and typed pending/accepted reconciliation. Work, Proof, and Workflow own their authority above Record;
Projections replaces only disposable rows/cursors through a distinct role. HTTP Board reads never advance
the cursor; the separately launched same-artifact worker performs catch-up. Every normal/default write
remains `durability_pending`; a verifier-owned two-PostgreSQL fixture proves the named-standby ACK path,
including complete receipt-bound finalization, standby-read confirmation, promotion ambiguity, and typed
degradation for unreadable live evidence. Its no-login evidence role is quarantined before adoption and
retains neither schema-CREATE nor role-assumption paths after its two fixed probes exist. There is no
configured production off-host target, real fixed-job effects, backup/restore proof, web surface, or
production deployment.

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

I1 has no agent stage dispatch, autonomous Commander loop, runner daemon, production effect grant, or browser
surface. Its public operation is the API plus protected `ctowerctl`/`ctl`; explicit durable-thread intent and
Workflow-owned append-only current-episode risk are API/CLI facts. The API composition and one control worker
share one kernel artifact; Access, Record, Catalog, Work, Proof, Attention, the limited generic Workflow
evaluator, and Projections remain logical responsibilities behind Module Interfaces. React/Vite, browser
session/CSRF, routes, Playwright, and all browser evidence begin at I2.4 under D22. Service-per-noun units
such as a separate reconciler are not implied.

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

The implemented kernel dependency edges are acyclic:
`Work|Proof|Workflow|Attention|Runtime -> Record -> Telemetry`. Record imports none of those owners, and
Workflow imports neither Work nor Proof. The repository policy validates edge allowlists and the entire
ownership graph for cycles; composition satisfies Workflow's structural Work-readiness and current-proof
ports.

| Deep Module | Authority hidden behind its Interface |
|---|---|
| Access / Record | Authentication, authorization, idempotency-before-CAS, streams, hash chain, outbox, durability result, accepted project-scoped event pages |
| Catalog | One `VersionedComponent` lifecycle, compatibility, provenance, exact pins, future-only active pointers |
| Work | Permanent tickets, lifecycle episodes, custody, relations, priorities, blockers, typed Board intents |
| Proof | Criteria, artifacts, evidence DAG, independence, gate instances/verdicts, invalidation |
| Attention | Exact policy-qualified human actions, the typed append-only findings feed and its configured kind catalog, and Needs You projection inputs |
| Workflow | Arbitrary pinned graph readiness, legal edges, policy selection, routes, bounds, terminal decisions |
| Runtime | Accepted jobs, leases, fencing, cursors, ACKs, checkpoints, versioned CommandGuard decisions, local execution composition |
| Effects | Grants, releases, provider observations, receipts, incidents, rollback, reconciliation |
| Projections | Rebuildable Home, Board, Ticket, Fleet, Analytics, contextual Project Delivery projection, watermarks, KPIs |

There is no `Factory`, `TaskManager`, status service, generic provider manager, or microservice per table.
The software factory is data interpreted by Workflow. Public Interfaces stay small; private validators,
folds, SQL, and Adapter mechanics remain local to the owning Module.

The project event read path remains inside Record. It joins accepted-command confirmation and the
authoritative ticket project before materializing an event, orders by accepted position then canonical
record-position tie-breaker, and emits a cursor bound to that composite point and one project. The strict
union is generated from named OpenAPI branches, while membership and aggregate-ticket versus linked-ticket
scope strategy come from project-scope metadata on the canonical Record event catalog. Today that catalog contributes
the six ticket, Work, Workflow, and Proof kinds needed to replay Board/ticket facts. Session and heartbeat
events are absent pending [#200](https://github.com/simjak/ctower/issues/200); neither API nor a consumer may
synthesize them. Browser consumption remains in I2.4 and does not change the Record boundary.

## Workflow and Execution Policy compose at runtime

```text
  immutable Workflow revision               compatible Execution Policy revision
  +-----------------------------------+     +----------------------------------+
  | stages + activity metadata        |     | participants/capabilities        |
  | declared stage groups (optional)  |     | mandatory stage gates            |
  | legal edges + parallelism         |     | required review perspectives     |
  | typed failure routes              |     | family-diversity placement rules |
  | gate locations                    |     | finite nonpass/repair/generation |
  | required evidence slots per stage |     | finite nonprogressing mutations  |
  | skip predicate + skip slot set    |     | timeouts, placement, escalation  |
  | terminal conditions               |     |                                  |
  +----------------+------------------+     +-----------------+----------------+
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

A Workflow may also declare an ordered stage-group vocabulary. Groups label the pinned graph so a rollup
can say "review" or "ship" without any engine, policy, projection, or test branching on a stage key; they
declare no edge, gate, terminal condition, or ordering authority. The delivery sprint — think, plan, build,
review, test, ship, reflect — is exactly that: seven declared groups over the sixteen stages
`engineering.software-factory` already has, not a second package and not a process the engine knows.

Each stage declares its ordinary required evidence slots and the signing slot among them. A stage that
declares a skip predicate declares a second, alternative skip slot set with its own signing slot. The two
sets are alternatives, never a union, and the requested disposition picks one: `succeeded` resolves the
ordinary set, evidence-backed `skipped` resolves the skip set in its place and is admissible only while
the pinned predicate holds on accepted durable facts. A skipped stage therefore owes its skip proof
instead of the work it did not do, and a `skipped` request with an unsatisfied predicate is refused rather
than converted or assumed. `SPEC.md` INV-61, INV-62, and INV-63 are authority for all of this.

At I2.1, the publishable software-factory revision must materialize one complete authored activation/edge
sequence, `sf.e00..e15`. It is linear from activation through `intake -> think -> plan -> design ->
implement -> local-verification-qa -> risk-derived-review -> documentation -> release-preflight -> merge
-> staging-deploy -> staging-qa -> production-deploy -> production-smoke-live-qa -> retro ->
resolve-close`. Documentation has no pre-review parallel start or policy-created alternative. Each edge
reads one accepted snapshot: current predecessor completion, exact slot/gate/digest facts, and any
destination checkpoint/change predicate. False or unknown inputs leave the destination blocked and are
recorded; Runtime availability can delay dispatch but cannot invent movement. The checked-in
`packs/workflows/engineering.software-factory/v1.yaml` remains a draft skeleton with empty transition and
failure-route arrays; this atlas does not claim those I2.1 mechanics are current.

Each stage also declares a closed set of typed failure reason codes whose authored action is exactly one of
retry, return to a named stage, wait for a named durable fact, or incident-first. A report that matches no
code or more than one becomes `classification_unknown` and dispatches nothing. Incident/hard-safety holds
win over that unknown-classification hold, which wins over the earliest declared repair destination when
one disposition contains multiple failures. Product defects reach plan, design, or implement only through
distinct typed codes, and production failures cannot repair until containment, exact-environment
verification, and typed triage are committed. `SPEC.md` contains the complete predicate-input and
stage-by-reason tables.

The no-stage-name/group-name conformance proof derives its denominator rather than maintaining it. It
recursively parses every authored Workflow below the sole pack root, enumerates every published Workflow
revision from Catalog, walks every stage/group key field, and requires discovered identity-set equality
with the exercised set. Arbitrary injective key renames must preserve behavior after references are
rewritten structurally; a temporary extra stage/group must be discovered and exercised without editing a
key list.

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

Two different things guard a verdict, and the atlas keeps them apart because their waiver rules differ.
**Independence** is identity truth — `independent_of`, at minimum the candidate authors, plus INV-19's
author-cannot-review-self. It is never waivable and no operator command reaches it. **Family diversity** is
a placement eligibility rule that asks a weaker question: whether the verifying identity likely shares the
author's blind spots. It is referenced as a revision-pinned eligibility class, never a vendor or model
name, and because it is a policy-declared bound a tier may declare it waivable by protected operator
command. Waiving it never permits self-review.

The fourth bound every Execution Policy declares is `max_nonprogressing_candidate_mutations`, the
no-progress rule. A candidate's outstanding set is the run's open failure lineages plus the required slots
unfilled on that candidate's digest, taken when it finishes verification. A governed mutation is
progressing only when the outstanding set of the candidate it produced is a strict subset of the set of
the candidate it replaced. Trading one open defect for another is not progress, which is the case the
bound exists for; the count is per run, only a progressing mutation clears it, and the declared value is
capped at the number of governed mutations the generation bound permits so it is always reachable.

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

Each card also carries a five-member **context set** — tenant display identity, recorded change references,
applied labels, human-waiting, and delivery-surface availability. Every member reads one explicit fact
class and nothing else:

```text
 tenant display fact ------------> tenant display identity
 linked Change facts ------------> change / PR references
 applied-label facts ------------> labels        (label vocabulary revision pinned at application)
 qualifying Attention finding ---> human-waiting (Needs You qualification, never a blocker)
 pinned checkpoint declaration --> delivery-surface availability
                                   present | absent | undeclared (STATE_UNKNOWN)
```

An unavailable member is stated — empty set, declared absence, no qualifying checkpoint, or
`STATE_UNKNOWN` with its missing source — never omitted, and never inferred from a name, lane, stage key,
blocker age, or silence. At I1 the context set is carried by the generated API and protected CLI; browser
rendering of every card fact remains I2.4.

Human-waiting has exactly one source: the **Attention findings feed**, the typed append-only record under
Needs You. A finding names one kind drawn from a versioned configured **attention-kind catalog** and pins
the revision active when it was appended, so kinds are configuration rather than a product enum and
outbox-poison is one member of that catalog rather than the shape of the feed. Resolution, snooze, expiry,
and cancellation are appended facts; a need never ends by a row disappearing. Needs You and the Board card
read the same feed under the same policy qualification, so they cannot disagree.

## Project Delivery projection reads facts; it never commands work

The Project Delivery projection is a contextual Board/project read model over the hierarchy
`Company -> Project -> Increment/Milestone checkpoint`. It reads accepted checkpoint definitions, tickets,
Workflow runs, Proof/gates, blockers, evidence/artifacts, decisions, costs, and applicable release/outcome
facts. It also reads the versioned **Seat catalog** (a configuration aggregate enumerating stable seat
keys and labels) and per-slot **seat-assignment** and signing-seat facts, so each qualifying-stage evidence
slot carries an assigned seat or explicit unassigned state, and a signing seat on completed evidence. Seat
facts pin the catalog revision that was active at seat-assignment time (or current at evidence time), so
rebuild at one watermark reproduces the same seat facts even if the catalog has since advanced. The
projection cannot mutate any of these or accept manual status.

```text
 authoritative ticket / Workflow / gate / outcome / seat-assignment fact
                         |
                         v
                transactional outbox
                         |
                 reconcile immediately
                         v
 +---------------- Project Delivery projection ----------------+
 | checkpoint row + proof coverage + derivation reasons         |
 | done > blocked > released > verified > merged                |
 |      > ready_to_land > in_progress > planned                 |
 | per-slot assigned/signing seat (or unassigned)               |
 | source watermark + last reconciled + confidence/freshness    |
 +--------------------------+-----------------------------------+
                            ^
        no relevant fact for one hour -> freshness heartbeat
        recompute same facts; change no lifecycle state
```

`done` requires current proof for every declared exit criterion. Otherwise an effective blocker overrides
the headline while preserving the highest underlying lifecycle maturity for drill-down. Checkpoints skip
merge/staging/release states they do not declare, so accounting, compliance, hiring, and software all use
the same fold. Ticket counts never become a completion percentage.

A checkpoint definition MAY declare its **delivery surface** — landing boundary, non-production
environments, externally effective outcome — each with identity or as an explicit absence. Consumers read
three states per field: declared-present, declared-absent, and explicitly undeclared (`STATE_UNKNOWN`),
which is neither presence nor absence and satisfies no skip predicate, entry item, or availability claim.
The skip/entry rules, the projection, and the Board card's delivery-surface availability all read that one
pinned declaration; none of them substitutes a stage name or silence for it.

An overdue heartbeat is stale. A missing/gapped watermark, unknown integrity or proof validity, or unsafe
authorization coverage is `STATE UNKNOWN`, not a ninth delivery state. Deleting/rebuilding the projection
at one watermark must reproduce the same rows. The compact projection is generically project-scoped and
filters its authorized source links before materialization; current I1.7 authority still limits operational
use to ctower dogfood. I2.4 adds browser drill-through, interactive detail, broader visualization, trends,
cost/time analytics, and the reusable cross-domain view.

The development-pilot row and the full-I1 row are not interchangeable. The pilot may become `done` on a
CT-I1-008 `GO_WITH_LIMITS` while still exposing `CP3_D_NOT_PROVEN`. The full-I1 row remains `blocked` while
CP3-D is red. A development headline never unlocks CT-I2-001.

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

Routine occurrence, concurrency/catch-up outcome, canonical event/result/outbox lineage, ordinary fixed job,
and `next_fire_at` commit together before acceptance-gated dispatch. Nonexistent civil times remain visible
skips and repeated times use the earlier offset. One logical scheduler owns Routine truth; there is no OS cron process per agent or
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

## Disaster-safe acceptance, restore, and authority gates

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

Full normative I1 requires accepted record truth with RPO 0 because an external-failure-domain durable ACK
precedes acceptance. Its destructive isolated restore is unusable until key recovery,
object/tombstone verification, validation of every signed expected-source inventory entry, and measured
RPO/RTO finish. I1 inventories root/effect/provider sources explicitly as `not_exercised` with zero-source
declarations; their absence is never success. Any missing, unreadable, or gapped activated source fails
closed. I2 commits a signed inventory revision marking a source active before the first associated
grant/effect. Ordinary reads and all effects remain disabled while any activated source is absent or
unreconciled; quarantine remains degraded evidence and never turns absence into restore success.

D27 permits an earlier, narrower fresh-database development authority milestone for reviewed
reconstructible ctower engineering data only. It is always labeled `CP3_D_NOT_PROVEN`; unknown archive,
integrity, source, alias, or projection state disables writes. It excludes credentials, accounting,
production authority/effects, incidents, client data, and irreplaceable artifacts. CT-I1-008 may call that
development pilot `GO_WITH_LIMITS` and complete its I1.7 row. The separate full-I1 milestone remains
`NO-GO` while any CP3-D evidence above is missing.

D25 places a smaller persistent shadow runtime before that authority milestone:

```text
loopback API (verified wheel) ----> PostgreSQL 17 primary
          ^                              |
          |                        physical WAL replay
same-wheel control worker                |
  + ordinary finalizer ------------> named ACK standby
```

Both database ports and the API are loopback-only. User systemd supervises the API and worker; persistent
container volumes retain the primary and ACK copy. The approved `development_offhost_ack` policy reuses
Record's exact named-standby receipt/finalization authority but forces degraded health reason
`development_offhost_ack_cp3_d_not_proven`. It proves usable shadow mechanics, not an external failure
domain, CP3-D, production durability, or single-writer cutover. Secret Service resolves database and CLI
references inside the owning process; service files, release manifests, and config never contain values.
Host authentication is SCRAM from initial publication. A network-isolated initializer receives its secret
only through stdin, leaves the initialized volume, and is replaced by the steady-state container without a
password environment entry; the clone password is likewise stdin-only. Separately from the forced-degraded
policy dimension, the worker writes monotonic typed finalizer progress:
inactive/failed/refusing/unknown/future/stale state is degraded, and only an active worker with a completed
scan no older than ten seconds is healthy. A refused finalization appends an immutable attempt with
exponential eligibility; three refusals or ten minutes of age append a terminal quarantine, remove that row
from ordinary scans, and leave later rows serviceable. Configuration/state, Secret Service/DSN authority,
and finalizer progress/health have separate small control-API Interfaces. Bootstrap has a strict owner-only
replay checkpoint, so
interruption resumes exact identities instead of minting a capability. The Part A runtime manifest is
verified before a one-time install directly at the permanent service path, and that path's installed console
entry point must execute before install succeeds. Runtime installation, lifecycle, systemd, Docker, Git,
and interpreter helper processes share one deadline-requiring execution Seam that terminates its owned
process group on timeout. Staging, pointer exchange, release-triggered service restart, and rollback remain
in the separately reviewed release-lifecycle follow-up.

The development authority path is therefore ordered:

```text
create fresh Company / Project / checkpoints + Project Delivery projection
  -> inventory the legacy corpus + exact carry-forward allowlist
  -> hash/sign/seal the complete corpus as read-only provenance
  -> recreate each approved item through ordinary generated API/CLI commands
  -> attach and reconcile stable legacy aliases + source digests
  -> CT-I1-008 development verdict and writer epoch
  -> reject every later legacy write as an incident
```

There is no dual-write period, corpus importer, fuzzy dedupe, or automatic backfill. The ordinary command
path cannot forge proof, gates, effects, delivery, resolution, closure, or arbitrary status. Before the
epoch, the incomplete fresh database may be discarded while Mission Control remains authoritative. After
the epoch, rollback means a compatible ctower build/restore or explicit read-only/spool mode, never
restarting legacy mutation. A separate future decision is required before any bulk import may activate.

I1.7A installs only contracts, append-only storage shape, the read-only projection fold, generated query
path, and refusing online migration stubs. Those artifacts establish neither fresh authority nor
carry-forward completion. CT-I1-008 owns the development verdict. Passing it does not satisfy its
CT-I2-001 dependency: that edge means full normative I1 exit, including CP3-D.

## Build sequence and earned Seams

```text
I1: L0 contracts/repository gates
     -> Record + Work + Proof
     -> off-host acceptance + restore
     -> spool-backed CLI
     -> API + protected-CLI trust-spine operation
     -> capture -> frame -> verify -> close on final generic evaluator
     -> fresh Project Delivery pilot + minimal carry-forward
     -> CT-I1-008 development GO/GO_WITH_LIMITS
     -> CP3-D external-failure-domain/key/destructive-restore/RPO-RTO proof
     -> full normative I1 exit

I2 (only after full I1 exit): deepen generic Workflow + Proof
     -> durable Runtime + CommandGuard and local process/tmux recovery
     -> activate unattended Commander on the proven always-on substrate
     -> D22 browser realization + deepen five surfaces + Project Delivery projection detail/analytics + Effects/release
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
11. The Project Delivery projection rebuilds identically, applies its eight-state precedence across
    software and non-software checkpoints, regresses on proof invalidation, reconciles facts immediately,
    and emits an hourly no-change heartbeat without inventing progress or ticket-count completion.
12. Remote/image/extension fixtures cannot be presented as an exercised runtime or public Seam.

Tmux is useful for same-host continuity and operator visibility. Durability comes from acknowledged records,
committed events/outbox entries, fenced leases, replayable cursors, immutable evidence, checkpoints,
off-host backups, and reconciled external receipts.
