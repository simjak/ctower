# Readiness plan: three projects on one ctower

Status: **BLOCKED on authority and prerequisite work**. This document is a docs-only readiness plan for
[issue #185](https://github.com/simjak/ctower/issues/185); it does not activate product scope, amend
`SPEC.md`, or authorize use of the development runtime for authoritative manibo or BH.Loop work
(`SPEC.md:108-121`, `SPEC.md:136-139`, `README.md:19-24`).

## Outcome and non-goals

The intended outcome is one ctower installation with one portfolio tenant/company and three project scopes:
`ctower`, `manibo`, and `bh-loop`. Each scope has a Commander, intake provenance, project delivery
checkpoints, and Board visibility; a project Commander can act on that project's work and receives a typed,
zero-mutation refusal on another project's work (`SPEC.md:717-724`, `SPEC.md:2985-3010`,
`SPEC.md:3186-3192`).

This plan does not create a second database, make the shadow runtime production-safe, import historical
proof or status, grant Commanders Catalog write authority, put PHI/client data/credentials into ctower, or
make Mission Control and ctower concurrent writers (`DECISIONS.md:758-788`, `DECISIONS.md:850-887`,
`SPEC.md:1095-1099`). Browser work remains an I2.4 concern (`SPEC.md:433-466`).

## 1. Tenancy and project semantics as authorized

### Verdict

The target contract authorizes **one tenant/company with N projects**:

- A CompanyBundle carries one tenant identity, while its `resources` array may carry many components
  (`contracts/README.md:28-31`, `contracts/company/company-bundle.schema.json:7-32`). The SPEC explicitly
  describes one bundle containing `projects` and one Company -> Project -> checkpoint hierarchy
  (`SPEC.md:332-356`, `SPEC.md:975-997`).
- Project is a reusable, scoped Catalog component rather than a product-code roster; its payload carries a
  stable key and repository reference (`SPEC.md:896-900`, `contracts/components/project.schema.json:1-23`).
  Checkpoint identity is `(project, checkpoint)`, and activation orders checkpoints independently per
  project (`packages/ctower-kernel/src/ctower_kernel/catalog/_validation.py:153-178`,
  `packages/ctower-kernel/src/ctower_kernel/catalog/_checkpoint_sql.py:28-53`).
- Cross-project work uses explicit grants, which only makes sense inside a shared tenant authorization
  boundary; the authenticated tenant is server-derived and cannot be overridden by payload
  (`SPEC.md:1098`, `SPEC.md:3186-3191`).
- S1/S2 close hard-coded delivery vocabulary, not topology or rollout authority. D28 preserves generic
  configured keys and forbids a product-code roster (`DECISIONS.md:889-911`). The merged contracts accept
  `ledger-co/quarterly-close/Q3-close.2`, and migration 0037 aligns storage with that authored key domain
  (`tests/contracts/project_delivery/_fixture.py:12-65`,
  `packages/ctower-kernel/migrations/0037_relax_checkpoint_key_domain.sql:1-25`).

One installation can also contain later tenants, because first-tenant bootstrap closes permanently and
later tenants use ordinary Admin commands (`SPEC.md:954-973`). That is not the #185 topology: commands and
Board reads are tenant-scoped, so three tenants would yield three isolated Boards rather than the requested
portfolio view (`SPEC.md:3188-3190`,
`packages/ctower-kernel/src/ctower_kernel/projections/_board_sql.py:44-59`).

Issue #152 concerns two databases sharing a PostgreSQL cluster, whereas projects in the authorized topology
share one tenant/database. The present role lock is acquired in the caller's database even though roles are
cluster-global (`packages/ctower-kernel/src/ctower_kernel/record/_migration_control_sql.py:65-98`,
`packages/ctower-kernel/src/ctower_kernel/record/_setup_sql.py:265-306`). Closing #152 therefore remains the
explicit program gate in #185, but it must not be described as “project 2 creates database 2.”

### Missing execution authority

Multi-project **semantics** exist, so the task's semantic stop condition does not fire. Multi-project
**activation** does not exist:

- D24 limits development writing to an exact allowlist of public, low-value, reconstructible ctower
  engineering records and forbids credentials, accounting, production authority/effects, incidents, client
  data, and irreplaceable work (`DECISIONS.md:758-782`).
- D27 narrows the active fresh-start path to the ctower Company/Project/checkpoint hierarchy and the
  reconstructible `ctower-project` cohort (`DECISIONS.md:850-887`). The current public status likewise says
  shadow-only, not authoritative or irreplaceable work (`README.md:19-24`, `README.md:131-146`).
- The implementation enforces that narrowness: intake recognizes only company/project `ctower`, ticket
  bindings still have `CHECK (project_key = 'ctower')`, the CLI only accepts `ctower`, and cutover health is
  explicitly ctower-development data (`packages/ctower-kernel/src/ctower_kernel/record/_intake_state_sql.py:38-55`,
  `packages/ctower-kernel/migrations/0028_i17b_importer_isolation.sql:139-149`,
  `apps/ctowerctl/src/ctowerctl/_parser.py:505-513`,
  `packages/ctower-kernel/src/ctower_kernel/projections/project_delivery.py:261-302`).

Before Lane 1 begins, an append-only operator decision and reviewed SPEC revision must:

1. lock the topology to one portfolio tenant/company with project keys `ctower`, `manibo`, and `bh-loop`;
2. state that CP3-D still blocks authoritative portfolio cutover, and either authorize only a named
   reconstructible three-project shadow cohort or wait for full normative I1 before legacy writers stop;
3. prohibit PHI, client data, credentials, incidents, production authority, and sole-copy artifacts in the
   shadow cohort—especially for BH.Loop;
4. define operator-wide versus project-Commander grants and the fail-closed rule for unknown ownership;
5. add stable CT work IDs, dependencies, owners, file surfaces, and validation commands for Lanes 1–5.

Those are required decisions, not changes made by this plan; `SPEC.md` remains the only scope authority
(`SPEC.md:123-132`, `SPEC.md:3927-3953`).

## 2. Custody, principals, and project mutation refusal

The phrase “#180 custody model” in #185 is a stale live-record reference. As read on 2026-08-01,
[#180](https://github.com/simjak/ctower/issues/180) is about anonymous intake rejection diagnostics, not
custody. Task briefs must cite the SPEC and the code below until the issue link is corrected.

### What exists

| Surface | Current fact |
|---|---|
| Initial custody policy | The public Work policy permits Commander self-custody or an operator naming another principal; it has no project input (`packages/ctower-kernel/src/ctower_kernel/work/_custody_policy.py:12-36`). The Record adapter separately proves that the target is an enabled Commander in the same tenant (`packages/ctower-kernel/src/ctower_kernel/record/_ticket_sql.py:242-272`). |
| Principal scope | `Actor` contains principal, tenant, and kind only; `principals` has no project grant (`packages/ctower-kernel/src/ctower_kernel/record/interface.py:168-175`, `packages/ctower-kernel/migrations/0002_ticket_slice.sql:8-18`). First bootstrap creates one durable Commander; later principals are specified but not implemented by an Admin interface (`SPEC.md:963-973`). |
| Ticket scope | The Ticket aggregate is specified to carry tenant/project scope, but the `tickets` row has tenant only (`SPEC.md:717-724`, `packages/ctower-kernel/migrations/0002_ticket_slice.sql:51-67`). The separate binding is immutable per ticket but currently accepts only `ctower` (`packages/ctower-kernel/migrations/0028_i17b_importer_isolation.sql:139-149`). |
| Transfer | Custody transfer locks by tenant/ticket and accepts any enabled same-tenant Commander or operator; it never compares projects (`packages/ctower-kernel/src/ctower_kernel/record/_custody_sql.py:120-186`). |
| Other ticket mutations | Role checks such as priority authorization distinguish Commander/operator but do not evaluate project scope (`packages/ctower-kernel/src/ctower_kernel/work/interface.py:490-499`). |
| Checkpoint writes | CompanyBundle apply is operator-only; a Commander currently has no own-project or foreign-project Catalog mutation authority (`packages/ctower-kernel/src/ctower_kernel/catalog/postgres.py:243-255`). |

### What must be built

1. Add an append-only project-grant relation for principals. The operator has tenant-wide portfolio
   authority; each of the three Commander principals has exactly one active project grant. Authentication
   resolves grants server-side—never from request JSON—and disabled/historical principals keep attribution
   (`SPEC.md:3153-3161`, `SPEC.md:3186-3192`).
2. Materialize immutable `project_key` on every Ticket and ticket event/projection fact. Retain provenance
   bindings where they add source history, but remove the ctower-only constraint and reject any binding that
   disagrees with the Ticket aggregate (`SPEC.md:1098`,
   `packages/ctower-kernel/migrations/0032_thread_first_intake.sql:79-107`).
3. Put one project-authorization guard at the trusted Work/Record boundary and require every ticket,
   Workflow, Proof, relation, assignment, custody, and projection path to use it. An absent or unknown grant
   fails closed; a known mismatch returns a stable `project-scope-denied` problem and performs no authoritative
   mutation (`SPEC.md:2985-3010`, `SPEC.md:3186-3192`).
4. Resolve initial custody as `(ticket.project_key, target Commander grant)`. Commander A may self-place
   custody only on A's project; the operator may place custody with that project's eligible Commander through
   the protected path. Cross-project custody and transfer both refuse before interval/event writes
   (`SPEC.md:49-60`, `SPEC.md:2991-2995`).
5. Keep CompanyBundle apply operator-only. Project Commanders do not gain a partial-bundle mutation path;
   cross-project checkpoint safety follows from no Commander Catalog authority plus operator review of the
   one portfolio bundle (`SPEC.md:975-997`,
   `packages/ctower-kernel/src/ctower_kernel/catalog/postgres.py:243-255`).

Mission Control's ownership incident is the concrete refusal proof to preserve: project ownership must be
an explicit field and the caller must be identified
(`/srv/projects/mission-control/board/REQUESTS.md:68`). Its current guard correctly refuses a known mismatch
unless an audited reason is supplied, but still adopts an unowned legacy row after only a warning
(`/srv/projects/mission-control/tools/_project_ownership.py:224-277`). R2379 requires unknown ownership to
refuse rather than let the first writer adopt it (`/srv/projects/mission-control/board/REQUESTS.md:507`). The
phase-2 proof also keeps R IDs portfolio-global and requires cross-writer allocation and no-leak fixtures
(`/srv/projects/mission-control/docs/specs/state-project-ownership-phase-2.md:41-66`). Ctower must copy the
property, not the JSONL mechanism.

## 3. Provisioning projects 2 and 3 as data

### Apply shape

There is one tenant/company bundle, not one company or database per project. The operator expands one complete
portfolio `CompanyBundle`, then runs `company bundle validate`, `plan`, `apply`, and `export`; apply stages
immutable revisions and atomically moves one active pointer (`SPEC.md:975-997`,
`apps/ctower-api/src/ctower_api/_catalog_routes.py:69-81`,
`packages/ctower-kernel/src/ctower_kernel/catalog/postgres.py:243-255`). A separate manibo bundle followed by
a BH.Loop bundle would describe two competing complete desired states, so it is not the onboarding path
(`packages/ctower-kernel/src/ctower_kernel/catalog/_planning.py:24-83`).

After Lanes 0–3 remove platform hard-coding, onboarding changes only authored configuration:

- expand `company/company.bundle.yaml` from its current secret-free example into the reviewed complete
  portfolio bundle (`company/README.md:1-3`, `company/company.bundle.yaml:1-45`);
- add `packs/components/projects/manibo.delivery/v1.yaml` and
  `packs/components/projects/bh-loop.delivery/v1.yaml`, following the existing project pack at
  `packs/components/projects/ctower.control-plane/v1.yaml` and the strict project schema
  (`contracts/components/project.schema.json:1-23`);
- add one `packs/components/checkpoints/<checkpoint-key>/v1.yaml` for each checkpoint below and include its
  strict envelope/payload in the unified bundle. Every checkpoint has project scope, outcome, owner, ordered
  position, criteria, and evidence-policy references (`contracts/components/checkpoint.schema.json:1-68`,
  `packages/ctower-kernel/src/ctower_kernel/catalog/_checkpoint_sql.py:64-121`);
- add project workflow assignments in the same bundle; do not put principals, tickets, credentials, runtime
  state, or proof into YAML (`SPEC.md:977-997`, `company/company.bundle.yaml:419-436`).

The paths above are configuration artifacts, not new product branches. Component digests and provenance must
pin reviewed source revisions; configuration must contain no pipeline secret or BH.Loop PHI
(`SPEC.md:1093`, `SPEC.md:1108`).

### Manibo starter checkpoint set

These seven checkpoints summarize the real NFQ release train without hard-coding their names in product
code. The pipeline's declared order is verify -> infra -> publish -> deploy -> e2e -> production-infra ->
production -> production-e2e (`/srv/projects/manibo/.gitlab-ci.yml:25-34`).

| Key | Outcome and starter exit evidence |
|---|---|
| `manibo.verify` | Python, frontend, and Terraform static gates pass on the candidate (`/srv/projects/manibo/.gitlab-ci.yml:65-124`). |
| `manibo.staging-infra` | Reviewed staging plan is applied and its plan/apply artifacts are retained (`/srv/projects/manibo/.gitlab-ci.yml:184-217`, `/srv/projects/manibo/.gitlab-ci.yml:254-314`). |
| `manibo.images-published` | All release images are published by immutable commit SHA and emit digest artifacts (`/srv/projects/manibo/.gitlab-ci.yml:399-450`, `/srv/projects/manibo/.gitlab-ci.yml:452-575`). |
| `manibo.staging-deployed` | GitOps staging promotion reaches the declared cluster and the runtime wait succeeds (`/srv/projects/manibo/.gitlab-ci.yml:577-650`). |
| `manibo.staging-nfq-e2e` | The NFQ staging E2E suite passes and retains its artifacts (`/srv/projects/manibo/.gitlab-ci.yml:732-757`). |
| `manibo.production-released` | Production infrastructure applies; production deploy remains manually gated and depends on staging E2E (`/srv/projects/manibo/.gitlab-ci.yml:348-370`, `/srv/projects/manibo/.gitlab-ci.yml:652-718`). |
| `manibo.production-nfq-e2e` | The NFQ production E2E suite passes and retains its artifacts (`/srv/projects/manibo/.gitlab-ci.yml:759-784`). |

### BH.Loop starter checkpoint set

These seven checkpoints reflect BH.Loop's canonical D11/HIPAA delivery gates at
`bh-loop@f0c5ed64eee237ff0d0eb4def801081397416857`, not a generic software pipeline:

| Key | Outcome and starter exit evidence |
|---|---|
| `bhloop.contract-admission` | Canonical spec/decision review and the IP-assignment prerequisite are resolved before implementation (`bh-loop@f0c5ed64:IMPLEMENTATION-ROADMAP.md:107-124`). |
| `bhloop.d11-technical` | Identity/session, RBAC/RLS, encryption, every-attempt PHI audit, integrity/recovery, Secret Manager, and synthetic-only non-production evidence are green (`bh-loop@f0c5ed64:DECISIONS.md:352-383`, `bh-loop@f0c5ed64:SPEC.md:1168-1193`). |
| `bhloop.production-foundation` | The Google BAA/covered-services and threat-model gates are accepted before any production PHI path (`bh-loop@f0c5ed64:IMPLEMENTATION-ROADMAP.md:109-115`). |
| `bhloop.layer-1-foundation` | The Layer-1 foundation acceptance set and synthetic PHI mechanism proofs pass (`bh-loop@f0c5ed64:IMPLEMENTATION-ROADMAP.md:126-203`, `bh-loop@f0c5ed64:SPEC.md:1410-1418`). |
| `bhloop.layer-2-staff-assistant` | Staff-assistant safety outcomes and the independently reconcilable adoption denominator pass on the proven foundation (`bh-loop@f0c5ed64:SPEC.md:1420-1428`). |
| `bhloop.d11-organizational` | Executed BAA, subprocessor review, SRA, policies, officers, training, breach/retention plans, and legal posture are linked before a real lab result (`bh-loop@f0c5ed64:SPEC.md:1195-1203`). |
| `bhloop.biomarker-rail` | Counsel/Medical Director gates precede marker import, report release, and the Layer-4 exit evidence (`bh-loop@f0c5ed64:IMPLEMENTATION-ROADMAP.md:115-121`, `bh-loop@f0c5ed64:SPEC.md:1465-1475`). |

## 4. Intake mapping on the shared R counter

The intake command already carries `project_key`, source kind/ref, content, intent, taint, optional target,
and initial custody (`packages/ctower-kernel/src/ctower_kernel/record/intake.py:45-87`). Threads persist project
scope, and link-ticket intake checks that the target binding matches the thread project
(`packages/ctower-kernel/migrations/0032_thread_first_intake.sql:27-36`,
`packages/ctower-kernel/src/ctower_kernel/record/_intake_state_sql.py:251-280`).

The remaining identity bug is that source-alias uniqueness and its advisory lock omit project even though the
alias row stores it (`packages/ctower-kernel/migrations/0032_thread_first_intake.sql:64-77`,
`packages/ctower-kernel/src/ctower_kernel/record/_intake_state_sql.py:127-153`). Change the canonical source
identity to `(tenant_id, project_key, source_kind, source_ref)`; the shared R allocator remains portfolio-wide
and `R2693` is never renumbered (`/srv/projects/mission-control/docs/specs/state-project-ownership-phase-2.md:54-61`).

For one owned Mission Control row, the bridge stamps:

| Intake field | Mapping |
|---|---|
| authenticated tenant | Derived from the project principal's credential; never present as a caller override (`SPEC.md:3188-3189`). |
| `project_key` | Exact latest-row `project` value mapped to `ctower`, `manibo`, or `bh-loop`; absent/unknown ownership refuses before spool enqueue (`/srv/projects/mission-control/tools/_project_ownership.py:124-147`, `/srv/projects/mission-control/board/REQUESTS.md:507`). |
| `source.kind` | `mission-control-request` for R rows; tasks use their separately declared kind. The kind is bounded and typed (`contracts/domain/intake/thread-intake.schema.json:26-33`). |
| `source.ref` | Existing stable alias `mc:<project>:request:R<counter>:sha256:<source-digest>` so the global R identity and exact source revision remain attributable. Project is also a first-class key, not security inferred from this string (`/srv/projects/mission-control/tools/ctower_writer_adapter.py:19-24`, `/srv/projects/mission-control/tools/ctower_writer_adapter.py:185-226`). |
| content/title/priority | Source row text and explicit P0/P1/P2 mapping; no status, proof, workflow, or delivery claim is imported (`DECISIONS.md:878-882`). |
| intent/taint | `create_ticket` and `authenticated` only for the trusted local ledger adapter; untrusted external producer content uses its actual taint (`packages/ctower-kernel/src/ctower_kernel/record/intake.py:20-42`). |
| initial custodian | The enabled Commander granted to the same project; mismatch refuses under the custody guard in section 2 (`packages/ctower-kernel/src/ctower_kernel/record/_ticket_sql.py:242-272`). |

The current Mission Control adapter is not yet a bridge: it is intentionally ctower-only, emits
`createTicket` rather than thread-first intake, and is imported by no legacy writer
(`/srv/projects/mission-control/tools/ctower_writer_adapter.py:1-4`,
`/srv/projects/mission-control/tools/ctower_writer_adapter.py:19-24`,
`/srv/projects/mission-control/tools/ctower_writer_adapter.py:185-226`). Lane 5 replaces its generated request
with `submitIntake`, preserves spool-first ACK behavior, and adds three-project ownership fixtures.

## 5. Project Delivery and Board separation

### Current separation

- Project Delivery has a generic top-level `project_key`, and its read SQL selects exactly
  `(actor.tenant_id, requested project_key)` (`contracts/domain/project-delivery/project-delivery.schema.json:230-289`,
  `packages/ctower-kernel/src/ctower_kernel/projections/_project_delivery_sql.py:158-207`). Active checkpoint
  materialization and reconciliation already group definitions by project
  (`packages/ctower-kernel/src/ctower_kernel/catalog/_checkpoint_sql.py:38-53`,
  `packages/ctower-kernel/src/ctower_kernel/projections/_project_delivery_reconcile_sql.py:137-152`).
- Board is tenant-separated only. Its contract/card/query has no project field, its route accepts no project
  filter, and the read loads every tenant card before applying other filters
  (`contracts/domain/task-management/board-view.schema.json:20-64`,
  `apps/ctower-api/src/ctower_api/_board_routes.py:34-62`,
  `packages/ctower-kernel/src/ctower_kernel/projections/_board_sql.py:44-59`).

### Gap list

1. No project grant is checked on Project Delivery reads; any authenticated principal in the tenant can ask
   for any configured project (`packages/ctower-kernel/src/ctower_kernel/projections/_project_delivery_sql.py:158-184`).
2. Board storage, `BoardCard`, generated contracts, API, CLI, and `_matches` all omit project
   (`packages/ctower-kernel/migrations/0008_board_projection.sql:57-82`,
   `packages/ctower-kernel/src/ctower_kernel/projections/interface.py:207-230`,
   `packages/ctower-kernel/src/ctower_kernel/projections/_board_sql.py:324-340`,
   `apps/ctowerctl/src/ctowerctl/_parser.py:389-400`).
3. Ticket source events do not carry project, so the Board consumer cannot derive it without the separate
   binding (`packages/ctower-kernel/src/ctower_kernel/record/ticket_events.py:18-40`,
   `packages/ctower-kernel/src/ctower_kernel/projections/_board_sql.py:99-119`).
4. Project Delivery accepts configured ticket proof links but reads Board facts by tenant/ticket only; there
   is no assertion that every linked ticket belongs to the row's project
   (`packages/ctower-kernel/src/ctower_kernel/projections/_project_delivery_reconcile_sql.py:155-190`,
   `packages/ctower-kernel/src/ctower_kernel/projections/_project_delivery_sources_sql.py:168-196`).
5. The CLI artificially restricts a generic generated route to `ctower`
   (`apps/ctowerctl/src/ctowerctl/_parser.py:505-513`,
   `tests/contracts/project_delivery/test_generated_clients.py:19-77`).
6. Project Delivery durability/data-class values describe the ctower development cutover, not arbitrary
   projects; BH.Loop must never be represented as disaster-safe or PHI-authorized by those values
   (`contracts/domain/project-delivery/project-delivery.schema.json:99-137`,
   `packages/ctower-kernel/src/ctower_kernel/projections/project_delivery.py:261-302`).

Lane 3 adds project to the authoritative ticket event and Board card/query, writes project into the Board
projection, filters at SQL before materializing a view, checks the actor's project grants, and validates every
Project Delivery source link. A project-scoped read returns only that project's rows/cards; an operator may
request a portfolio view, but aggregation still cannot reveal a source the operator cannot read
(`SPEC.md:486-489`, `SPEC.md:1095`, `SPEC.md:1120`).

## 6. Sequenced implementation lanes

The order preserves #185: authority -> #152 -> principals/isolation -> configuration -> bridge. No lane is
active until Lane 0 creates stable CT authority (`SPEC.md:3927-3953`).

### Lane 0 — authority and stable backlog activation

**Files:** `DECISIONS.md`, `SPEC.md`, `ARCHITECTURE.md`, `IMPLEMENTATION-ROADMAP.md`, and the generated
traceability index in its declared machine-owned path (`SPEC.md:123-132`). This plan changes none of them.

**Acceptance:** the reviewed operator decision covers the five authority points in section 1; stable CT IDs
own Lanes 1–5 and their dependencies; the SPEC says whether the three-project cohort is shadow-only or waits
for CP3-D; `ARCHITECTURE.md` is derived and non-divergent. No decision weakens D24/D27 or claims full I1 while
CP3-D is red (`DECISIONS.md:850-887`).

**Verification:** `just check && just verify`; traceability proves each new AC/INV/backlog reference resolves,
and a docs review searches for any accidental production, authority, PHI, or dual-write claim.

### Lane 1 — close #152's cluster-global role race

**Files:** `packages/ctower-kernel/src/ctower_kernel/record/_migration_control_sql.py`,
`packages/ctower-kernel/src/ctower_kernel/record/_setup_sql.py`, focused cluster-authority support/tests under
`tests/acceptance/increment-1/`, and any authored setup contract changed by the selected fixed coordination
database (`packages/ctower-kernel/src/ctower_kernel/record/_migration_control_sql.py:65-122`).

**Acceptance:** two fresh databases in one PostgreSQL cluster start role provisioning concurrently; every one
of at least 30 synchronized trials produces the same valid cluster role shape with no catalog collision,
partial membership, unsafe adoption, or retry-only convergence. Different clusters do not serialize each
other. A missing/unreachable coordination database returns a bounded typed setup error and creates no role
mutation. Same-database migration serialization remains green.

**Verification:** a new deterministic two-database concurrency test plus
`uv run pytest tests/acceptance/increment-1/test_database_role_privileges.py tests/acceptance/increment-1/test_projection_role_adoption.py -q`,
then `just check && just verify`.

### Lane 2 — project principals and custody authority

**Files:** a new additive kernel migration and authored access/admin contract; `contracts/http/openapi.yaml`;
`packages/ctower-kernel/src/ctower_kernel/access/`; `record/interface.py`, `_ticket_sql.py`,
`_custody_sql.py`; `work/_custody_policy.py`; the API Admin/Work adapters; generated clients through the
normal codegen command; custody/access acceptance tests. Generated files are never hand-edited
(`SPEC.md:113-116`, `SPEC.md:3153-3161`).

**Acceptance:** ordinary authenticated Admin commands create two additional enabled Commanders and grant
exactly one of the three projects to each Commander; replay is byte-identical and conflicting replay refuses.
Each Commander self-places initial custody only on its own project. The operator can place or protected-
transfer custody only to that project's eligible Commander. Cross-project, disabled, absent, ambiguous, and
stale-grant cases return typed zero-mutation refusals. The full mutation matrix is tested for all ordered
project pairs, not only ctower -> manibo.

**Verification:** focused access/custody contract and acceptance suites, generated-client/codegen drift,
tenant-leak fuzzing, `just check`, then `just verify`.

### Lane 3 — immutable ticket project scope and read isolation

**Files:** additive migrations for Ticket/source/Board scope; `record/intake.py`, `_intake_state_sql.py`,
ticket events and SQL; shared Work/Workflow/Proof authorization policy; `projections/_board_sql.py`,
`_project_delivery_sql.py`, `_project_delivery_reconcile_sql.py`; Board and Project Delivery schemas; API/CLI
adapters; generated clients; intake/Board/Project Delivery acceptance tests
(`SPEC.md:1098`, `SPEC.md:1120`).

**Acceptance:** every ticket has one immutable project; source aliases key on tenant/project/source; all
ticket-linked mutations verify the actor grant; Board cards carry project and filter in SQL; Project Delivery
source links reject a foreign-project ticket; generated clients and CLI accept configured project keys. Three
projects with identical titles, stages, and source-ref suffixes never cross in Board, delivery rows, counts,
watermarks, or drill-down. Unknown scope is `STATE_UNKNOWN`/refused, never inferred. Cross-project mutation
attempts leave event, outbox, assignment, proof, workflow, and projection fingerprints unchanged.

PR #197 deliberately leaves six ticket mutation routes unscoped until the project-grant authority in #192
and its route repair in #198 land: `POST /v1/tickets/{ticket_id}/custody`,
`POST /v1/tickets/{ticket_id}/workflow/start`, `POST /v1/tickets/{ticket_id}/priority`,
`POST /v1/tickets/{ticket_id}/assignments`, `POST /v1/tickets/{ticket_id}/intents`, and
`POST /v1/tickets/{ticket_id}/relations`. Inventory-derived skipped tests name every route and point to
#192/#198; they record the gap without duplicating #198's authorization predicate.

**Verification:** new three-project contract vectors and an endpoint mutation/read matrix; existing
`tests/contracts/project_delivery`, `tests/contracts/task-management`,
`tests/acceptance/increment-1/test_intake.py`, `test_checkpoint_delivery.py`, and Board suites; codegen/traceability;
`just check && just verify`.

### Lane 4 — manibo and BH.Loop configuration onboarding

**Files:** only `company/company.bundle.yaml`, the two project payloads, fourteen checkpoint payloads, and
their configuration tests/fixtures under existing `packs/components/` and `tests/contracts/components/`
surfaces (`SPEC.md:865-930`, `packs/components/projects/ctower.control-plane/v1.yaml:1-8`). No Python,
TypeScript, migration, API, or projection edit is permitted in this lane.

**Acceptance:** validate succeeds; plan lists exactly two new projects, fourteen new checkpoints, and the
intended assignments; apply is one atomic operator command; replay deduplicates; export -> validate -> plan
has zero semantic diff. Removing, renaming, or reordering a checkpoint is a bundle-data mutation with no
product-code diff. Every provenance digest pins the cited pipeline/spec revision. Secret and PHI canaries are
rejected. Both project views render all seven configured rows without literal-key branches.

**Verification:** CompanyBundle/component/project-delivery contract suites, a no-product-code path-diff
assertion, generated manifest/digest checks, `just check`, then `just verify`.

### Lane 5 — project-aware Mission Control bridge

**Files:** `/srv/projects/mission-control/tools/ctower_writer_adapter.py`, its isolated tests, the exact legacy
writer call sites activated by the separately authorized bridge task, and ctower intake/spool conformance
tests. It uses generated ctower models only; it never connects to ctower persistence
(`/srv/projects/mission-control/tools/ctower_writer_adapter.py:97-139`,
`SPEC.md:67-69`).

**Acceptance:** the adapter reads one latest row with an explicit project, emits `submitIntake` with the
mapping in section 4, preserves one command ID through spool/ACK, and returns the accepted ticket/project.
Known foreign ownership and unknown ownership both refuse before enqueue. The three project aliases retain
their shared R IDs and never collide. Retry, lost-ACK, duplicate source, permanent-refusal, and quarantine
cases remain bounded and named. Legacy mutation for a reviewed cohort stops only at its approved authority
epoch; there is no dual-write fallback (`DECISIONS.md:774-782`, `DECISIONS.md:878-882`).

**Verification:** `python -m unittest tests.test_ctower_writer_adapter` in Mission Control; ctower generated
client, intake, spool, and refusal-lineage suites; a user-level three-row walkthrough showing three accepted
tickets, three correctly filtered Boards, and all six ordered foreign-Commander mutation refusals; then each
repository's full declared gate.

## Release, rollback, and final proof

There is no feature flag in this plan. Catalog activation is an atomic versioned pointer and is future-only;
rolling back configuration means applying a reviewed predecessor/superseding bundle, never rewriting accepted
history (`SPEC.md:889-894`, `SPEC.md:1115`). Bridge rollback stops new
project writers and leaves already accepted ctower facts readable; it never resumes a legacy writer after an
authority epoch (`DECISIONS.md:774-782`).

The release candidate is ready only when one operator and each project Commander complete the three-project
walkthrough; negative reads and writes cover every ordered project pair; bundle export is zero-diff; Board and
Project Delivery rebuild byte-identically; no PHI/client/secret canary is stored; and `just verify` passes on a
clean intended tree (`SPEC.md:486-489`, `SPEC.md:3186-3192`, `IMPLEMENTATION-ROADMAP.md:511-525`). Full
authoritative portfolio cutover remains blocked until the Lane-0 decision's stated authority gate—necessarily
CP3-D for work outside the permanently narrow development cohort—has accepted evidence
(`DECISIONS.md:765-773`, `DECISIONS.md:866-877`).
