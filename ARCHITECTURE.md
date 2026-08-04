# ctower architecture atlas

| Field | Value |
|---|---|
| Status | Compact derived operator and implementer map |
| Normative authority | [`SPEC.md`](SPEC.md), version 1.13 |
| Decision history | [`DECISIONS.md`](DECISIONS.md) |
| Last reviewed | 2026-08-02 |

This is the sole terminal-safe derived architecture atlas. It explains the canonical specification; it
does not add requirements, authorize work, or define exact schemas, operations, DDL, package values, or
deployment manifests. If this file and `SPEC.md` disagree, `SPEC.md` wins and this file is stale.

Implementation labels are strict:

- **Current walking slice** means the development-only bootstrap, CP2 task/Board, CP-1 Proof/Workflow,
  CP3-A durability-authority fixture, and CP3-B deterministic scheduler/accepted-outbox/health paths
  implemented in this repository. They are synthetic local evidence, not a deployed product.
- **I1** and **I2** otherwise remain committed target increments, not claims that the full behavior exists.
- **Deferred** means invariants may be recorded, but the runtime, product surface, and public Seam do not
  exist in I1/I2.

Authority milestones are deliberately separate. One tenant and database contain the configured `ctower`,
`manibo`, and `bh-loop` Projects, their commander-authored checkpoints, and disjoint Project Delivery
projections. During `SHADOW_ONLY_CP3_D_NOT_PROVEN`, Mission Control and applicable GitHub/GitLab records
remain co-sources; reviewed reconstructible coordination records enter through ordinary signed item-by-item
intake with project-scoped identities. Bulk import is dormant. CT-I1-008 may issue development
`GO_WITH_LIMITS` while CP3-D is red, but it stops no writer and grants no sole authority. Full normative I1
exit remains `NO-GO` and CT-I2-001 remains unauthorized until portfolio isolation work completes and
external-failure-domain acknowledgement, key recovery, isolated destructive restore, and measured RPO/RTO
pass.

Investor-plain: ctower can show one coherent portfolio without pretending it has already replaced the
systems that run that portfolio. The shadow proves separation and operating usefulness first; the operator
can consider cutover only after disaster recovery is independently proven.

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

## Portfolio topology and project-grant boundary

The portfolio shares infrastructure, not authority. Project is immutable on every Ticket and linked fact.
Ticket IDs retain their authored instance-global UUIDv7 contract; source identities are `(tenant, project, source kind, source ref)` and
render as stable `<project>-R<nnn>` references from the shared counter.

```text
one tenant / one PostgreSQL database
  |
  +-- Project: ctower  ---- configured owner: ctower-commander
  +-- Project: manibo  ---- configured owner: manibo-commander
  +-- Project: bh-loop ---- configured owner: bhloop-commander
          |
          +-- Project grant -> seat credential -> exact scope subset
                 pins Project + seat catalog + access policy + credential revisions/digests
```

The three owner keys are configuration values, never product-code roster literals. Issue #152 gates only a
future multi-database topology. Access resolves the active, revision-pinned grant server-side on every call;
initial custody additionally requires an eligible configured Commander with an active target-Project grant.

| Operation | Required Project authority | Additional boundary |
|---|---|---|
| Issue or revoke credential/grant | Operator only | Append-only; revocation refuses the next call |
| Issue or revoke a human role binding | Operator only | Append-only, revision-pinned; revocation refuses the next request |
| Register/enable/rotate a provider registry entry | Operator only | Platform admin needs the operator role too |
| Apply portfolio CompanyBundle | Operator only | Versioned configured Project/seat/checkpoint data |
| Read Ticket/Board/Delivery | Active matching grant or role binding | Existing visibility rules still apply; `viewer` is read-only inside its bound keys |
| Intake/link/request initial custody | `capture` | Target Project and eligible Commander must match |
| Ordinary typed Work mutation | `transition` | Foreign Project refuses `project-scope-denied` |
| Record ordinary allowed Evidence | `evidence` | Foreign Project and prohibited classes refuse |
| Owner/protected/gate/effect/incident/production operation | Existing stricter authority | Never implied by a Project scope |

Intake and Evidence share the refusal boundary. `credential_material`, `production_customer_data`,
`phi_hipaa_covered`, `pii_beyond_staff_identity`, and `live_incident_indicator` refuse as
`prohibited-data-class` with the exact class name and zero mutation. BH.Loop may retain only D11 control
references, GitHub/GitLab artifact references, and deidentified control IDs—never patient or clinical
content. All six directed cross-Project mutation pairs and a revoked credential's next call have named,
zero-diff proofs.

Authentication has two entry planes and one authority result:

```text
human: configured OIDC discovery -> verified (issuer, subject) -> pinned role binding --+
                                                                                       +-> typed Actor
machine: project-seat Bearer -> revision-pinned Project grant + exact scopes -----------+   -> one custody/audit model
```

INV-73 makes that convergence a chokepoint: one Actor per authenticated request, one authority record per
plane, and no transport that carries its own principal, custody, or attribution record.

Manibo's provider-agnostic OIDC modules and conformance behavior are the source pattern. Per the Manibo
Commander, ctower preserves that contract at a pinned revision instead of extracting a package while both
consumers are changing; a third consumer or measured non-drift may reopen extraction. The provider registry,
verified discovery domains, and `operator|commander|viewer` human role bindings are versioned configuration
that only the operator may create, enable, or rotate. The registry pins one exact redirect URI matched by
string equality. UI uses only an opaque record-backed session; direct human and machine APIs use their
respective Bearer credentials.

Provider egress is exactly three bounded call sites, each fail-closed:

| Call site | Bound | Terminal outcome |
|---|---|---|
| Discovery fetch | 1+2 attempts, 5 s each, 20 s ceiling, 24 h max cache age | `auth-provider-unverifiable` |
| Token exchange | 1+1 attempts, 5 s each, 12 s ceiling | `auth-exchange-invalid` |
| JWKS fetch/rotation | 1+2 attempts, 5 s each, one refetch per 5 min per entry | `auth-provider-unverifiable` |

Provider tokens are verified then discarded; no refresh token and no `offline_access` are stored. Every auth
denial carries a stable code — `auth-provider-unavailable`, `auth-exchange-invalid`,
`auth-provider-unverifiable`, `auth-identity-unresolved`, `auth-session-invalid`, `reauthentication-required`,
`auth-role-denied`, `project-scope-denied` — never a bare 401/403. All auth routes stay
tailnet/private-HTTPS-only, and CT-I1-013 cannot pass without an independent CSO verdict.

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
audit; append-only recorded work sessions carrying seat, crew, model, harness, worktree, branch, the
authored `dispatched|briefed|working|gated` lifecycle, and a Record-computed duration beside
caller-observed token counts; three fixed Routine revisions; an accepted-only, rebuildable six-lane Board; immutable delivery and
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
product surface. Its public operation is the API plus protected `ctowerctl`/`ctl`; explicit durable-thread
intent and Workflow-owned append-only current-episode risk are API/CLI facts. After the import chain,
CT-I1-013 adds only login/callback/session/logout/auth-error routes and auth evidence. The API composition and
one control worker share one kernel artifact; Access, Record, Catalog, Work, Proof, Attention, the limited
generic Workflow evaluator, and Projections remain logical responsibilities behind Module Interfaces.
React/Vite product routes, the five surfaces, and product Playwright evidence begin at I2.4 under D22/D31.
Service-per-noun units such as a separate reconciler are not implied.

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
| Access / Record | Authentication, revision-pinned Project grants, authorization, prohibited-class refusal, idempotency-before-CAS, streams, hash chain, outbox, durability result |
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

R2707 adds one authoring path in front of that composition, not another engine. The CompanyBundle resolves
Company, Project, Team/profile, and Ticket-schema keys before privately normalizing the strict S7/S8
Workflow Definition YAML into the same immutable Workflow payload shown above. That source authors the
Workflow-owned half only — graph and derived endpoints, stages and responsibilities, ordinary and skip slot
sets with their signing slots, gate locations, typed routes, and the group vocabulary — while perspectives,
gate activation, and finite bounds stay with the separately pinned Execution Policy. Source-schema
validity, resolved-plan validity, and Catalog publication are separate gates, and a payload missing a
Workflow-owned fact is refused with that fact named rather than defaulted. S7 and S8 edit/project the same
source; only a published normalized revision/digest can run. Per-project overlays are additive evidence
requirements only. Stage `owner` selects an eligible responsibility/capability and never supplies D28 seat
truth; assigned seats remain explicit facts and signing seats still derive from Evidence assignment.

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

Six slot contracts in the software-factory package carry extra bound requirements because prose replaces
them most often: `plan.criteria`, `implement.warm-gate`, every `use-proof`/`live-use-proof`/`verification`
transcript, `risk-derived-review.round-manifest`, `documentation.revision`, and
`release-preflight.release-notes`. The last two are why documentation cannot be asserted: the docs revision
binds the current candidate digest, the generating command run, and every documented surface that candidate
adds or changes, and the release-scoped artifact binds the release manifest plus each included change's
current documentation completion. Neither adds an evidence kind — both are `artifact-digest`.

`documentation` and `release-preflight` declare no skip predicate, so neither can be omitted at any risk
tier, and the record binds the real landing the only way it can: one required status check on the change
resolves the ticket's **landing-boundary predecessor set** — every stage the pinned graph places before the
stage carrying the landing boundary — and reports each stage's fact separately as `pass`, `fail`, or
`STATE_UNKNOWN` on the head revision's candidate digest. Green requires every fact; unknown is a failure.
The set derives from the pinned graph, never from stage-key strings, so the check carries no branch
AC-WF-25 forbids. The check is a pure reader — no authoritative write, no Evidence, no slot, no gate — and
is never itself proof. `SPEC.md` INV-74 and AC-REL-09 are authority for this.

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
`Company -> Project -> Increment/Milestone checkpoint`. One configured fold serves the `ctower`, `manibo`,
and `bh-loop` Projects, while active matching grants produce three mutually disjoint filtered views. It
reads accepted checkpoint definitions, tickets, Workflow runs, Proof/gates, blockers, evidence/artifacts,
decisions, costs, and applicable release/outcome facts. It also reads the versioned **Seat catalog** (a
configuration aggregate enumerating stable seat keys and labels) and per-slot **seat-assignment** and
signing-seat facts, so each qualifying-stage evidence
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
at one watermark must reproduce the same rows. I1.7 exposes only the three Project hierarchies and compact
disjoint read-only CLI text projections, with optional deterministic JSON, for portfolio dogfood. Each
compact projection is generically project-scoped and filters its authorized source links before
materialization. I2.4 adds browser drill-through, interactive detail, broader visualization, trends,
cost/time analytics, and the reusable cross-domain view.

The development-pilot row and the full-I1 row are not interchangeable. The pilot may become `done` on a
CT-I1-008 `GO_WITH_LIMITS` while every portfolio row still exposes health `CP3_D_NOT_PROVEN` and portfolio
responses separately expose authority label `SHADOW_ONLY_CP3_D_NOT_PROVEN`. The
full-I1 row remains `blocked` while CP3-D is red or CT-I1-009..013 are incomplete. A development headline
never unlocks CT-I2-001 or freezes a co-source.

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

D30 supersedes D24/D27's pre-CP3-D writer-epoch allowance. The fresh database may hold only reviewed
reconstructible coordination data under `SHADOW_ONLY_CP3_D_NOT_PROVEN`; Mission Control and applicable
GitHub/GitLab records stay co-sources, and unknown integrity, source identity, Project authorization, or
projection state fails closed. Credentials, accounting, production authority/effects, incidents, customer
or PHI data, and irreplaceable artifacts remain excluded. CT-I1-008 may call the narrow development pilot
`GO_WITH_LIMITS` and complete its I1.7 row, but it stops no writer. The separate full-I1 milestone remains
`NO-GO` while CT-I1-009..013 or any CP3-D evidence above is missing.

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
Record's exact named-standby receipt/finalization authority but forces technical degraded-health reason
`development_offhost_ack_cp3_d_not_proven`; portfolio responses additionally expose authority label
`SHADOW_ONLY_CP3_D_NOT_PROVEN`. It proves usable shadow mechanics, not an external failure domain, CP3-D,
production durability, or single-writer cutover. Secret Service resolves database and CLI
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

The portfolio shadow path is therefore ordered:

```text
create fresh Company / ctower + manibo + bh-loop Projects and disjoint projections
  -> CT-I1-008 narrow shadow-only development verdict
  -> CT-I1-009 immutable identities + revision-pinned grants + grant-aware custody
  -> CT-I1-010 exact scopes + isolation + commander-authored onboarding configurations
  -> CT-I1-011 ordinary signed item-by-item intake of manibo's 115 items
  -> CT-I1-012 project-scoped typed feed + three disjoint Board proofs
  -> CT-I1-013 two auth planes -> one Actor/custody/audit model + CSO gate
  -> prove CP3-D
  -> separately accept portfolio authority; only then freeze legacy writers
```

There is no tailer, corpus importer, fuzzy dedupe, or automatic backfill. The ordinary command path cannot
forge proof, gates, effects, delivery, resolution, closure, or arbitrary status. Throughout shadow
operation the incomplete fresh database may be discarded while Mission Control and applicable
GitHub/GitLab records remain authoritative co-sources. A separate future decision is required before any
bulk import may activate; this decision does not pre-authorize the eventual source-of-truth cutover.

I1.7A installs only contracts, append-only storage shape, the read-only projection fold, generated query
path, and refusing online migration stubs. Those artifacts establish neither portfolio authority nor
shadow onboarding completion. CT-I1-008 owns the narrow development verdict. Passing it does not satisfy
its CT-I2-001 dependency: that edge means full normative I1 exit, including CT-I1-009..013 and CP3-D.

## Build sequence and earned Seams

```text
I1: L0 contracts/repository gates
     -> Record + Work + Proof
     -> off-host acceptance + restore
     -> spool-backed CLI
     -> API + protected-CLI trust-spine operation
     -> capture -> frame -> verify -> close on final generic evaluator
     -> fresh three-Project Delivery shadow + ordinary reviewed intake
     -> CT-I1-008 development GO/GO_WITH_LIMITS
     -> CT-I1-009 identities, grants, credentials, grant-aware custody
     -> CT-I1-010 scopes, isolation, prohibited-class refusal, onboarding configs
     -> CT-I1-011 manibo 115-item ordinary signed intake
     -> CT-I1-012 project-scoped feed + three disjoint Board proofs
     -> CT-I1-013 config-driven human OIDC + unchanged machine credentials + one Actor/audit model
     -> CP3-D external-failure-domain/key/destructive-restore/RPO-RTO proof
     -> full normative I1 exit

I2 (only after full I1 exit): deepen generic Workflow + Proof
     -> durable Runtime + CommandGuard and local process/tmux recovery
     -> activate unattended Commander on the proven always-on substrate
     -> consume CT-I1-013 auth + deepen five surfaces + Project Delivery projection detail/analytics + Effects/release
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
12. One-tenant/N-Project setup yields `ctower`, `manibo`, and `bh-loop` with three disjoint Board views,
    instance-global UUIDv7 Ticket IDs, and stable project-scoped source references without roster literals.
13. All six directed cross-Project mutation pairs refuse by name with zero diff; issuance, exact scope,
    revocation, and the revoked credential's next call are independently proven.
14. Intake and Evidence refuse every prohibited class by exact name, including a PHI-shaped fixture, while
    allowed deidentified BH.Loop control and artifact references remain usable.
15. Remote/image/extension fixtures cannot be presented as an exercised runtime or public Seam.

Tmux is useful for same-host continuity and operator visibility. Durability comes from acknowledged records,
committed events/outbox entries, fenced leases, replayable cursors, immutable evidence, checkpoints,
off-host backups, and reconciled external receipts.
