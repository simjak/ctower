# ctower derived checkpoint roadmap

| Field | Value |
|---|---|
| Status | Non-normative execution sequence derived from `SPEC.md` 1.13 |
| Product increments | Exactly two: Increment 1 and Increment 2 |
| Work authority before development epoch | SPEC temporary bootstrap backlog / Mission Control |
| Work authority after development epoch | ctower tickets for the reviewed cohort only |
| Last reviewed | 2026-08-02 |

This roadmap makes the normative build order easier to execute. It does not create a third scope model,
approve work, mirror ticket status, or override the stable IDs, acceptance criteria, validation commands,
or two product increments in [`SPEC.md`](SPEC.md). [`DECISIONS.md`](DECISIONS.md) preserves rationale.
No extra operator decision is required to begin L0 or I1 as specified. I2 remains unauthorized until full
normative I1 exit; a CT-I1-008 development `GO` or `GO_WITH_LIMITS` does not satisfy that dependency while
CP3-D is red. Normal operator-only gates still apply to material taste, a newly discovered
architecture/security direction, destructive action, or incident.

The approved authority shape is fresh start plus minimal carry-forward: create the ctower Company /
Project / checkpoint hierarchy and Project Delivery projection on a fresh database; keep the complete
legacy corpus as signed read-only provenance; recreate only the exact reviewed still-actionable set through
ordinary generated API/CLI commands with stable aliases. Bulk legacy import is dormant pending a separate
future decision.

## One checkpoint sequence

Contract Level 0 is the opening checkpoint group inside I1, not a product increment.

```text
INCREMENT 1 — durable task-management dogfood

 [L0 contracts + repository gates]
              |
 [co-located control + bootstrap]
              |
 [Record + Work + Proof + evaluator subset]
              |
 [off-host acceptance + isolated restore]
              |
 [spool-backed CLI]
              |
 [API + protected CLI trust-spine operation]
              |
 [four-stage fixture on final generic evaluator]
              |
 [fresh Project Delivery pilot + exact minimal carry-forward]
              |
 [CT-I1-008 development GO / GO_WITH_LIMITS]
              |
 [project identity -> isolation -> intake -> typed feed]
              |
 [two auth planes -> one Actor/custody/audit model + CSO]
              |
 [CP3-D: external ACK + keys + destructive restore + measured RPO/RTO]
              |
============== FULL NORMATIVE I1 EXIT ==============
              |
INCREMENT 2 — autonomous generic workflow + one golden path

 [deepen generic Workflow + Proof/policy]
              |
 [durable Runtime + CommandGuard + local process/tmux recovery]
              |
 [activate durable Commander orchestration]
              |
 [I2.4 browser realization: five surfaces + Project Delivery detail/analytics + Effects/release]
              |
 [one software-factory production golden ticket]
```

The order matters. Development dogfood may begin with limits before CP3-D, but its authority is confined to
the reviewed reconstructible cohort and remains visibly `CP3_D_NOT_PROVEN`. Full normative I1 exit remains
`NO-GO` until CP3-D passes, and only that exit authorizes CT-I2-001. Always-on scheduling, reconciliation,
restart, and restore proof precede unattended Commander autonomy. The I1 fixture uses the same generic
Workflow Module Interface that I2 deepens; no temporary stage-name engine is allowed.

## Checkpoint exit contract

A checkpoint is complete only when all applicable conditions hold:

1. Its stable backlog item contracts and designated validation commands pass.
2. Authored schemas, package values, generated output, tests, and documentation remain in their sole homes.
3. At least one real vertical behavior is observed through the public Interface; private database edits or
   process/session state are not evidence.
4. Each new durability or authority claim has an injected failure plus restart/replay/recovery evidence.
5. Acceptance criteria bind exact artifacts, digests, actors, environments, and current verdicts.
6. Unknown or incomplete state fails closed and is visible; no self-report, terminal exit, or screenshot
   alone establishes completion.
7. A retro or checkpoint review turns a process defect into a linked improvement or an evidence-backed
   no-change decision.
8. Later checkpoint suites remain `not_yet_required`; no placeholder test is presented as passing.
9. A checkpoint that first gains arbitrary local or remote harness command execution also implements and
   proves the final pre-dispatch CommandGuard contract; resequencing execution cannot move or waive this
   prerequisite.
10. Any Project Delivery projection row is derived from current authoritative facts at a visible watermark;
    manual status, ticket-count completion, a freshness heartbeat, or a missing source cannot claim progress.

Execution status belongs to the temporary SPEC backlog before the development epoch and to ctower tickets
for the reviewed cohort afterward. This file records sequence and exit logic only.

## Increment 1 — durable task-management dogfood

### I1.0 — Contract Level 0

**Stable work:** `CT-L0-001` through `CT-L0-009`.

Freeze the smallest contracts needed for independent work:

- authority/ownership, DDL and privilege homes, canonical events/hash/idempotency, OpenAPI and codegen;
- P0/P1/P2, typed blockers/intents, six Board lanes, arbitrary stage `activity_class`, assignment kinds,
  delivery facts, and scheduling fairness;
- domain-neutral Workflow, Execution/Gate/Evidence policy, Routine, wake/job/lease/cursor vocabulary;
- strict Python/TypeScript boundaries, Repository Policy, Ruff/format/mypy/Pydantic, file/function/complexity
  gates, observability, secrets, hooks, CI, deterministic generation, and expected-suite scope;
- one `VersionedComponent` envelope, CompanyBundle schemas, first-tenant bootstrap contract, and package
  materialization/provenance;
- denial/deferred-capability contracts for remote execution, images, and executable extensions without
  claiming public Seams.

**Exit:** `just check` and the L0-scoped `just verify` contract are real, non-mutating, and fail missing,
empty, drifted, oversized, cyclic, secret-bearing, shallow pass-through, or unowned current-scope work.
The exact Python pin remains gated by D14 compatibility evidence; no `uv.lock` is created prematurely.

### I1.1 — Co-located trusted control and first-tenant bootstrap

**Stable work:** `CT-I1-001`.

Build one private-VPS control artifact used by the `ctower-api` composition and one application control
worker. Add the checksum-locked migrator, least-privilege Postgres roles, digest object store, vault/KMS
references, private TLS edge, telemetry, and one-use local/private first-tenant trust-root ceremony.

The bootstrap transaction creates the tenant, disabled historical bootstrap actor, initial operator/admin,
durable Commander principal, vault bindings, events/outbox, receipt, and permanent disable atomically.
It creates no ticket, profile, workflow, credential value, or runtime state.

**Exit:** crash, replay, concurrent use, expiry, wrong origin, changed body, and second-use tests create no
duplicate or partial authority; the token appears in no argv, URL, environment, log, event, or artifact.

### I1.2 — Record, Work, Proof, and the generic evaluator subset

**Stable work:** `CT-I1-002`, `CT-I1-003`, and applicable L0 contracts.

Implement the first deep Modules behind small Interfaces:

- Access/Record: authenticated append, idempotency before CAS, hash chain, outbox, cursors, replay tombstones;
- Catalog/Work: exact component pins, permanent ticket identity, lifecycle episodes, custody, assignment
  intervals, relations, P0/P1/P2, blockers, typed Board intents, resolution/close;
- Proof/Attention: criteria freeze/revision, content-addressed artifacts, evidence, protected verdicts,
  invalidation, exact human actions;
- Workflow evaluator subset: pinned graph, activity metadata, legal edge, entry/exit, gate and terminal
  decisions for arbitrary definitions, with a test that rejects branching on fixture stage names.

**Exit:** no-proof/no-close, self-verdict denial, corrupt-object, selective invalidation, exact replay,
cross-tenant, concurrency, projection rebuild, and accepted/refused transition tests pass through Interfaces.

### I1.3 — Acknowledged durability and disaster-safe operations

**Stable work:** durability spine of `CT-I1-006`, completed with the later I1 surfaces before final exit.

Make acceptance mean recoverability:

```text
record commit -> required off-host ACK -> accepted
             \-> ACK unavailable -> durability_pending (safe replay)
```

Add off-host WAL/record acknowledgement, encrypted database/object backups, external anchors, vault/KMS
recovery, Routine occurrences for synthetic/backup work, poison-outbox handling, completeness watermarks,
real reboot recovery, and isolated restore. Restore must verify chains, anchors, objects, and erasure
tombstones, then verify a signed expected-source inventory. I1 lists root-supervisor, effect, and provider
journals explicitly as `not_exercised`/zero-source; absence is not success. Every activated source must be
present and reconciled from its trusted cursor before ordinary reads or effects can enable.

**Exit:** host-loss accepted-record RPO is 0; artifact RPO is explicitly separate and no worse than the
SPEC target. Restore records measured RPO/RTO. Missing keys, objects, receipts, cursors, or journal matches
keep the environment isolated and visibly degraded. A missing activated inventory source fails closed.
This CP3-D proof is mandatory for full normative I1 exit and CT-I2-001 authorization; it is not optional
merely because development dogfood received `GO_WITH_LIMITS`.

### I1.4 — Protected spool-backed CLI and CompanyBundle path

**Stable work:** `CT-I1-004`.

Implement `ctowerctl`/`ctl` through the generated OpenAPI client. The encrypted owner-only spool preserves
one command ID across crash, torn write, concurrent writer, disk full, timeout, replay, rejection, and
quarantine. It removes nothing until authoritative acceptance. CompanyBundle validate, semantic plan,
apply, and canonical export use the same authenticated command path as UI changes; YAML is never watched
and contains no secrets, counters, sessions, receipts, or live work.

**Exit:** API/CLI parity, kill/replay, two-writer, disk, poison, secret, and zero-semantic-diff round-trip
tests pass. `durability_pending` remains a non-accepted replayable result.

### I1.5 — Deferred browser product realization alias

**Stable work:** stable deferred alias `CT-I1-005` -> `CT-I2-005` I2.4 browser sub-checkpoint.

No I1 browser product implementation or product evidence is authorized. CT-I1-013 is the sole earlier
exception and owns only login/callback/session/logout/auth-error routes plus auth evidence. D22's
React/Vite product routes/navigation, screenshots, product UI QA, and narrow Fleet/Analytics presentation
are realized at I2.4. This stable alias preserves audit history; it is not an I1 predecessor or a deleted
scope item.

I1 retains the API/CLI semantics D22 selected: durable-thread-first explicit
`discussion|create_ticket|link_ticket` intent/provenance; Workflow-owned append-only risk; six-lane fold;
typed intents; health/Attention; and pending/refusal/quarantine/degraded/`STATE UNKNOWN` reporting.

### I1.6 — Four-stage trust-spine fixture on the final evaluator

**Stable work:** the integrated fixture in `CT-I1-003`, `CT-I1-006`, and `CT-I1-008`.

```text
capture [work] -> frame [work] -> verify [verification] -> close [work]
```

Run `ctower.trust-spine-four-stage@1` through the public generic Workflow Interface. `capture` records the
off-host-accepted ticket, priority, source, and custodian. `frame` freezes criteria/evidence/gate contracts.
`verify` records current-digest evidence and a protected verdict. `close` resolves and administratively
closes only after server validation. The API/CLI six-lane projection derives `in_review` from activity
metadata, not the word verify.

**Exit:** daily synthetic runs, restore/reboot, public API/protected-CLI, Proof, and forbidden-stage-name
tests all pass.
The clean-install first-success trial meets AC-ADM-03: on a supported private VPS, a first operator installs,
bootstraps, applies the minimal CompanyBundle, captures one ticket, and completes this fixture through the
protected CLI within 60 minutes of operator elapsed time, without direct DB/legacy writes or hidden recovery.
This is an acceptance target, not current behavior.

### I1.7 — fresh ctower-project authority and development dogfood

**Stable work:** `CT-I1-007`, `CT-I1-008`.

Deliver this checkpoint in reviewable parts:

- **Current I1.7A visibility boundary:** development-only authority truth, cutover-health and Project
  Delivery contracts, generated read clients, minimal append-only storage, a pure read-only fold, and
  online-only migration stubs that refuse. These are not writer or completion evidence.
- **Fresh authority preparation:** establish the Company / Project / checkpoint hierarchy and compact
  Project Delivery projection on a fresh database; inventory the full legacy corpus and exact
  still-actionable carry-forward allowlist.
- **Minimal carry-forward and dogfood:** hash/sign/seal the full legacy corpus read-only; recreate only the
  reviewed actionable set through ordinary generated API/CLI commands with stable aliases/source digests;
  reconcile through public reads; then issue the CT-I1-008 development verdict and commit the writer epoch.

The development path is:

```text
fresh Company / Project / checkpoints + Project Delivery projection
  -> signed read-only legacy archive + exact reviewed carry-forward allowlist
  -> ordinary generated API/CLI create/link/assign commands + stable aliases
  -> exact public-read reconciliation
  -> CT-I1-008 development GO or GO_WITH_LIMITS
  -> writer epoch; reject every later legacy mutation
```

There is no tailer, dual-write interval, fuzzy dedupe, automatic backfill, or active bulk importer. Ordinary
commands cannot forge proof, gates, effects, delivery, resolution, closure, or arbitrary state. Before the
epoch, rollback may discard the incomplete fresh database while Mission Control remains authoritative.
After the epoch, rollback is a compatible ctower restore/build or explicit read-only/spool mode; legacy
mutation never resumes. Bulk import stays dormant behind a separate future operator decision.

The CT-I1-008 development verdict may be `GO_WITH_LIMITS` and may complete the development Project Delivery
pilot/I1.7 checkpoint. It does not satisfy the disaster-safe authority criterion and excludes credentials,
accounting, production authority/effects, incidents, client data, and irreplaceable artifacts. Full
normative I1 exit remains `NO-GO` until CP3-D proves external-failure-domain acknowledgement, key recovery,
isolated destructive restore, and measured RPO/RTO and CT-I1-009..013 pass.

The same checkpoint establishes only the hierarchy needed to dogfood project delivery:

```text
ctower company -> ctower project -> ordered Increment/Milestone checkpoints
                                    -> outcomes + owners + exit criteria
                                    -> qualifying tickets/Workflow/proof/outcome facts
                                    -> compact Project Delivery projection rows
```

The compact read-only Project Delivery CLI text projection, with optional deterministic JSON, shows checkpoint
key/label, deterministic headline state, outcome, accountable owner, `proven / declared` exit-criterion
coverage, source watermark, freshness, authorized source IDs, and derivation reasons. Relevant accepted
facts reconcile rows immediately; one hour without a relevant change publishes a freshness heartbeat that
cannot move lifecycle state. Stale or incomplete sources are loud. There is no manual status, ticket-count
percentage, browser drill-through, interactive row-detail product, broad visualization, trend/cost/time
analytics, or reusable cross-domain UI in I1.7; those depend on this proven hierarchy/rebuild contract and
belong to I2.4.

**Development exit:** every reviewed carry-forward item and stable alias is accounted for exactly once
through ordinary commands; the complete legacy corpus has a signed read-only manifest; zero post-epoch
legacy writes occur; the attention baseline is frozen; and applicable development evidence is archived.
The ctower checkpoints reproduce the same compact Project Delivery projection after restart, apply the
canonical eight-state precedence with proof-aware `done`/`blocked`, and expose immediate reconciliation,
hourly no-change freshness, and stale/unknown faults without accepting a projection write. A
`GO_WITH_LIMITS` result keeps `CP3_D_NOT_PROVEN` visible.

**Full I1 exit:** remains `NO-GO` until CT-I1-009..013 and the required CP3-D evidence pass. Only that full exit satisfies
CT-I2-001's dependency on CT-I1-008. From the development epoch, ctower tickets—not this file or the SPEC
table—own implementation status for the reviewed cohort.

### I1.8 — portfolio import chain, then shared authentication

**Stable work:** `CT-I1-009` through `CT-I1-013`.

The order is fixed: immutable Project identities/grants and grant-aware custody -> exact scopes/isolation
and Commander-authored onboarding config -> ordinary item-by-item Manibo intake -> project-scoped typed feed
and three disjoint Board proofs -> authentication. The last step preserves Manibo's provider-agnostic OIDC
contract at a pinned revision, following its Commander's recommendation not to extract a package while both
consumers are changing. It adds discovery-driven human OIDC beside unchanged project-seat machine
credentials and resolves UI session, human API bearer, and machine bearer requests into the same
Actor/custody/audit model. Providers and exact `operator|commander|viewer` human role bindings are versioned
configuration. Auth routes remain tailnet-only and do not realize the five product surfaces.

**Exit:** the ticket reports reuse `1/1`, identity planes `2/2`, Actor/custody models `1/1`, roles `3/3`,
transports `2/2`, provider-specific product branches `0`, configured providers `discovered = exercised`,
and independent CSO verdict `1/1`; every ambiguity, replay, revocation, foreign-project attempt, secret scan,
and exposure check fails closed. No auth evidence can infer that an earlier import-chain item passed.

## Increment 2 — autonomous generic workflow and one factory golden path

### I2.1 — Deepen generic Workflow and Proof/policy

**Stable work:** `CT-I2-001`, `CT-I2-002`, `CT-I2-006`.

**Authorization gate:** CT-I2-001's dependency on CT-I1-008 means the full normative I1 exit, not the
development dogfood verdict. Do not start this checkpoint while CP3-D is red, even if CT-I1-008 recorded
`GO` or `GO_WITH_LIMITS` for the development cohort.

Deepen the same I1 Workflow Interface with arbitrary stage attempts/jobs, package-defined classification,
mandatory stage gates, required perspectives, finite anti-spin bounds, stable cross-digest failure lineages,
candidate/nonpassing/repair/execution facts, typed failure routes, selective Proof invalidation, sealed
review, readiness explanations, and protected waivers. A different four-stage non-engineering package must
run on the same evaluator with different stages, participants, perspectives, gates, and bounds.

The software-factory publication materializes the SPEC's complete `sf.e00..e15` edge table, including each
predicate revision and accepted-input contract, and its complete stage-by-reason retry/return/wait/incident
table. Documentation has exactly one incoming edge after current-digest review. Unknown predicate input
blocks movement; unknown or ambiguous failure classification dispatches no repair. Conformance exercises
every edge in true and refused form and every route action, including local/staging
requirements-versus-design-versus-implementation defects and production incident-before-repair.

This is also where the delivery sprint stops being a convention and becomes package data. The published
`engineering.software-factory` revisions declare the seven sprint stage groups over the sixteen pinned
stages, each stage's ordinary required typed evidence slots and signing slot, the mandatory stage gates,
the perspective independence contracts and family-diversity placement rules, the finite bounds including
the no-progress rule, and the six skip predicates whose alternative skip slot sets replace the ordinary
required slots and signing slot of the stage they excuse. The only earlier work is the optional stage-group
field frozen with CT-L0-004's stage schema; I1 publishes no grouped package and renders no group rollup.

**Exit:** no engine branch or platform default depends on software-factory stage/tier/group vocabulary;
missing perspectives/gates, client-authored counters, self-review, family collapse, invalid bounds,
unfilled required slots, silent skips, no-progress, and exhaustion fail closed with one deduplicated
escalation. The no-name proof recursively discovers every authored Workflow document and every published
Workflow Catalog revision, derives all stage/group keys from parsed payloads, asserts
discovered=exercised identity equality, applies behavior-preserving arbitrary renames, and proves with an
omission sentinel that a newly authored key enters the test without a maintained denominator.

### I2.2 — Durable Runtime and local execution continuity

**Stable work:** runtime/materialization parts of `CT-I2-003`, all of `CT-I2-004`.

Implement accepted/leased/running/terminal jobs, exclusive leases/fencing, cursor replay, durable command
ACKs, structured chunks/gaps, checkpoints, cancellation, reconciliation, and immutable effective manifests.
Exercise the local Codex/Claude Harness compositions and the direct-process and tmux Supervisor Adapters
through one conformance suite. Unknown component revisions fail closed.

Before the first Adapter may dispatch an arbitrary command, implement the versioned CommandGuard tracked
by [issue #17](https://github.com/simjak/ctower/issues/17) at every final local Harness or Supervisor
command-dispatch boundary. Normalize executable identity, argv or shell plan, cwd, bounded environment
references, parent traversal, globs, symlinks, and candidate targets; classify execution intent and
catastrophic action rather than matching raw substrings. `block` and `needs_operator` execute nothing. An
operator grant is strongly authenticated, exact-command/exact-target, one-use, short-lived, replay-proof,
and audited; safe cleanup requires capability plus containment. Every decision produces a redacted
immutable receipt. Any future remote Adapter must enforce a signed scoped decision/grant and return a
matching enforcement receipt before completion is accepted.

This checkpoint is where the first real Harness consumers earn exact CommandGuard policy, schema, storage,
signature, and local transport mechanics; this roadmap does not freeze them earlier. Remote provider
mechanics remain deferred until their separate real Seam is earned. The guard is accidental-destruction
defense, not a substitute for sandbox/VM/OS isolation, short-lived credentials, workspace scoping, egress,
or Effects brokerage.

Kill the wrapper, runner, tmux server, network, and host at declared points. A replacement must reconstruct
from ctower state, reject old epochs, preserve sole-copy work, and resume checkpointable work within the
specified recovery SLO. Pane/process/session existence is not health, ACK, terminal result, or evidence.

**Exit:** the worker substrate can operate unattended across restart/loss with zero orphaned nonterminal
jobs. Every registered Harness or Supervisor command-dispatch path also proves pre-dispatch guard
invocation, resolved-target and wrapper cases, zero execution on block/attention, one exact override use,
replay/expiry refusal, direct bypass rejection, and redacted service-level observability; a remote Adapter
additionally proves matching signed enforcement receipts. This is the activation gate for autonomous
Commander reasoning; Commander is not asked to compensate for missing scheduler, lease, checkpoint,
reconciliation, or command-guard durability.

### I2.3 — Activate the durable Commander

**Stable work:** Commander/capability part of `CT-I2-003` and orchestration across `CT-I2-001..006`.

Resolve the strongest healthy policy-permitted general-reasoning profile for each bounded reasoning job,
while one durable Commander principal keeps accountable ticket custody through verified production,
retro, resolve, and close. Persist orchestration-plan revisions, context/risk facts, selected policy options,
participants, gates, perspectives, finite bounds, evidence, and rationale. The plan never authors consumed
counts. Delegate implementation and independent verdicts; do not make the Commander a heavy worker.

**Exit:** forced model/process/context replacement preserves the same principal, custody, plan history,
counters, checkpoints, and exactly-once dispatch. No eligible strong profile, policy ambiguity, or exhausted
automation becomes one precise operator action rather than status-chasing noise.

### I2.4 — Browser realization, five surfaces, observability, and improvement views

**Stable work:** `CT-I2-005`, `CT-I2-009`.

Consume CT-I1-013's proven session/CSRF boundary, then realize and deepen Home, Board, contextual Ticket, Fleet, and
Analytics over generated clients and rebuildable
projections. Home/Ticket Attention adds exact-scope CommandGuard confirmation, grant state, and linked
decision/authorization/enforcement receipts without raw sensitive command content. Ticket also adds live
structured run/steering/ACK/gap, manifest, current proof, readiness refusals, delivery/incidents, cost, and
retro. Fleet shows profiles, runners, jobs, workspaces, routines, capacity, budgets, and health without
treating terminals as truth. Analytics versions attention, flow, quality, recovery, cost, release, and
improvement queries with watermarks and anti-gaming guardrails.

Build the richer Project Delivery projection surface on the hierarchy and deterministic compact fold already
proven at I1.7. Authorized interactive rows expose accountable owner; Workflow stage and independent Kanban/
Board state; tickets, Workflow runs, changes/PRs, and applicable releases/outcomes; exit criteria and current
proof coverage; passed/missing gates; blockers/dependencies; evidence/artifacts; decision history; estimated
versus actual cost/time; and last verified/reconciled time with confidence/freshness. Add broader
visualizations, trends, cost/time analytics, and reusable views for software, accounting, compliance, hiring,
and other configured Workflows. It remains contextual to the five surfaces and never creates a writable
status authority or third product increment.

**Exit:** exactly five primary surfaces, complete run reconstruction after restart, allocation fractions=1,
Needs You precision/recall, exact-scope guard confirmation and linked receipt views, no false calm, and KPI
drill-down to permanent tickets/provenance all pass. Project Delivery projection row detail is
authorization-safe; cross-domain fixtures share the eight-state fold; proof invalidation regresses only
dependent conditions; and restore/rebuild at one watermark reproduces the same rows and derivation reasons.

### I2.5 — Effects, root-owned release trust, and incident recovery

**Stable work:** `CT-I2-007`, `CT-I2-008`.

Implement changes/releases, distinct staging/production environments, scoped grants, receipts, the live
`systemd-vps/v1` integration, and its fault-injection implementation behind the internal Effects boundary.
The separately supervised root helper verifies artifact bytes, signature/attestation, subjects, and trusted
builder/workflow identity against root-owned policy before install. General runners hold no production or
root credentials. Before the first grant/effect, activation commits a signed expected-source inventory
revision that changes the root/effect journal from `not_exercised` to active and pins its trusted cursor.

Production smoke/live-QA failure must create an incident, revoke unused grants, contain or safely roll back,
verify the exact resulting environment, and record triage before repair can dispatch. Ctower restart must
reconcile root-supervisor receipts by cursor before inferring an effect result.

**Exit:** wrong/missing/revoked/untrusted provenance performs no install; staging and production have
separate receipts and live evidence; an injected failure proves verified rollback and no direct repair.

### I2.6 — One software-factory production golden ticket

**Stable work:** `CT-I2-010`, after `CT-I2-001..009`.

Use one permanent software-factory ticket to add `GET /v1/meta/build` and matching `ctl meta build`. The
package, not the engine, declares the full path from think/plan/design through implementation, local QA,
review, docs, release preflight, merge, staging, production verification, retro, resolve, and close.

The ticket traverses all seven declared sprint groups and omits none. `design` is its only evidence-backed
skip, because a read-only build-metadata endpoint satisfies neither the user-interface nor the
material-architecture predicate: it adds one operation inside the already-published `/v1` surface and one
command inside the already-published `ctowerctl` surface, under their existing compatibility contracts, so
it introduces no new protocol. That stage completes on its skip slot set alone, with no `contract` slot
filled; every other stage completes with its ordinary required slots filled and signed, and the
traceability report shows per-group `filled / required` coverage plus that one skip proof.

The golden policy selects one base `code-review` perspective covering correctness plus maintainability,
with package-specific finite nonpassing, repair, and candidate-generation bounds. Conditional `security`
or `rendered-design` activates only when its predicate applies. API/CLI QA, docs truth, release preflight,
staging QA, production smoke/live QA, and retro remain mandatory stage gates, not duplicate perspectives.
ReviewPlan v1 never treats `total_executions` as a limit; it remains an immutable observed audit/cost fact.

Force one runner loss, one Commander reasoning-job failover, one candidate invalidation, and one production
failure/rollback rehearsal. Release the root-verified signed artifact to distinct staging and production,
verify the real endpoint/digest independently, record the retro, and server-validate resolution/closure.

**Exit:** `GET /v1/meta/build` and `ctl meta build` agree with the deployed release; every gate/effect/failure
is reconstructable from ctower IDs without Mission Control ledgers, task/status files, raw terminal state,
or vendor sessions; the production golden ticket passes the exact I2 validation contract in the SPEC.

## Workflow and Execution Policy are different configuration concepts

Every package composes the same two platform concepts:

| Concept | Answers | Never owns |
|---|---|---|
| Workflow | Which stages, activity classes, and optional stage groups exist? Which edges, parallel groups, failure routes, gate locations, skip predicates, required evidence slots, and terminal conditions are legal? | Participants, model choice, consumed counters, or undeclared edges |
| Execution Policy | Who may execute/review? Which declared gates/perspectives activate? What independence, finite bounds, timeouts, placement, budgets, escalation, and waiver constraints apply? | New Workflow nodes/edges, groups, slots, verdicts, evidence, or server-owned consumption |

The software factory is one versioned package using those concepts. A research, hiring, legal, incident,
or accounting package may choose completely different stage keys and review perspectives without changing
the engine.

## ReviewPlan accounting law

For one immutable candidate digest, one terminal review round dispatches every required/applicable
independent perspective. The round advances immediately when all of them pass with no blocker. There is no
generic `required_passing_rounds`, platform tier table, fixed-two rule, or automatic ceiling.

A ReviewPlan is a named child revision of one pinned Gate Policy component. Its only reference form is
`<gate-policy-key>@<gate-policy-revision>#review-plans.<name>`; the parent revision/digest owns the bytes, so
the enclosing `review_plans` map name is the child identity and it has no independent key, revision, status,
or `VersionedComponent`.

- Only a terminal nonpassing round consumes `max_nonpassing_rounds`.
- Each governed mutation consumes `max_candidate_generations` and one stable lineage's
  `max_repairs_per_lineage` as applicable.
- Candidate mutation invalidates declared dependent QA/review proof; a later pass is fresh proof, not a
  repeated-pass requirement.
- `total_executions` is an append-only server fact for every started perspective job. Plans cannot author or
  cap, or reset it; ReviewPlan v1 defines no aggregate execution-limit field.
- A future aggregate cost/resource stop requires a real use case, a separately versioned policy component,
  an executable semantic validator, and actual enforcement before publication. No field or arithmetic is
  specified before then.
- Any applicable bound, no-progress rule, deadline, quota, or hard-safety stop yields one deduplicated
  escalation and no further automatic dispatch.

## Earned extension points and deferred scope

I1/I2 expose only what real variation justifies:

- **Earned public Seam:** local Supervisor Interface, with direct-process and tmux real Adapters plus one
  shared conformance suite.
- **Internal integration:** `systemd-vps/v1` plus a fault-injection implementation inside Effects; one live
  integration and one fake do not earn a generalized provider Seam.
- **Deferred:** Crabbox/remote runners, reusable custom images/setup terminal, warm pools/shared caches,
  generalized effect providers, executable Extension Host/workers, plugin marketplace, visual workflow
  editor, second production workflow, broad connectors, public SaaS, and HA control plane.

Deferred contracts preserve immutable pins, exact-identity cleanup, secret-free reusable state, fencing,
reconciliation, and fail-closed observations. They must be reported `not exercised`. A future public Seam
requires a real use case, at least two independently valuable real Adapters, and an unchanged conformance
suite; a fake alone is hypothetical indirection.

## Validation ownership

This roadmap does not duplicate command truth. The stable backlog row in `SPEC.md` owns each checkpoint's
designated validation command. The repository-wide handoff remains:

```text
just check     warm non-mutating quality gate
just verify    full manifest-scoped, drift/cleanliness/conformance/acceptance gate
```

Every checkpoint extends the committed expected-suite manifest in the same change that makes its suite
current. The development authority epoch recreates only the exact reviewed still-actionable stable backlog
set through ordinary generated commands, with one stable alias each; the signed legacy archive keeps
everything else as read-only provenance and bulk import remains dormant. After that, ctower ticket history
is the only live implementation board for the reviewed cohort. Full normative I1 exit still gates I2.
