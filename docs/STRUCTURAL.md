# ctower — the structural constitution

Status: **operator taste draft**, authored for [R2815](https://github.com/simjak/ctower) per the
2026-08-06 director task. This is a structural/architecture reference, not a canonical source. It may
explain the system; it never overrides `SPEC.md`, and where it and `SPEC.md`/`DECISIONS.md` disagree, those
win (D8, D16). It does not amend scope, activate backlog, or supersede
[`IMPLEMENTATION-ROADMAP.md`](https://github.com/simjak/ctower/blob/main/IMPLEMENTATION-ROADMAP.md).

**The seed.** The operator's own component taxonomy and constraints, captured verbatim in
`mission-control/board/ctower-structural-doc-brief.md`, are the authoritative reference for what belongs in
this document. His wording carries intent; this document regroups only where structure genuinely improves,
and states why every time it does. It names 13 top-level component groups, not 14 — Templates is marked
`(?)` in his own text, which is likely why the task brief rounded to 14. All 13 are preserved verbatim below;
none is dropped, and no scope beyond his brief is invented.

---

## Part 1 — Purpose, problem, structure, and reasoning

### What ctower is

ctower is the command-and-control brain for an agentic workforce. Operators steer it from a UI; agents work
through a CLI; one Commander principal holds accountable custody of each unit of work from intake to close;
one Director oversees many project Commanders across a portfolio. It is not a chat product, not a generic
kanban board, and not a wrapper around an LLM — it is the durable record and enforcement layer that sits
underneath humans and replaceable AI agents doing real work, so that "done" is a provable fact instead of a
claim (`README.md:3-9`).

### The problem it solves

Task management for an agentic workforce exists to do one thing: **reduce operator attention while agents
do the work** (the operator's own words, `DECISIONS.md` D4 — "the product's north-star measurement is how
much operator attention the system requires per unit of completed work"). Notes, todo lists, kanban boards,
and ordinary ticketing systems were built for humans who remember context between sessions, notice when a
teammate goes quiet, and instinctively distrust an unverified "done." None of that holds for autonomous
agents:

- A todo list or kanban card has no memory of *why* a stage exists or what proves it finished — a human
  fills that gap from context the agent doesn't have. ctower makes the criteria, evidence, and gate part of
  the record itself, frozen before work starts (`SPEC.md` §"Domain model", Acceptance criterion / Evidence
  aggregates).
- A notes file is mutable and unaudited — an agent can quietly lower the bar to match what it produced. A
  ticket's acceptance criteria are frozen and evidence-bound; a verdict from the same principal who froze
  them is refused (`docs/agents/operating-contract.md` Rule 9; README's independence note).
- A chat thread or a task.md file has no server-enforced state machine — "done" is whatever the last message
  said. ctower's Workflow evaluator refuses every transition without a satisfied entry/exit contract and
  records an exact unmet checklist on refusal (`SPEC.md` §"Enforced verification and repair").
- None of the human-shaped tools have a lease, a fencing token, or a durable job — when a human forgets a
  task, another human eventually notices; when an agent's process dies mid-task with no lease, nothing
  notices unless the system is built to. ctower's Runtime module owns that recovery contract explicitly
  (`SPEC.md` §"Runner loss, lease expiry, reconciliation, and resume").

The operator's own diagnosis (`DECISIONS.md` D3, OH-D4) names the actual failure mode observed running an
agentic workforce today: **silent confident failure**, scope creep, and agents that exceed expectations just
often enough that trust — not capability — is the binding constraint. ctower's answer is not "smarter
agents"; it is a **trust layer**: evidence-bound tickets, independent verification, and session review that
make trust a property of the record rather than a feeling about the last transcript you read.

### The structural model

Fourteen — thirteen, corrected above — named groups is a workable taxonomy for describing the system to a
human, but it is not an implementation boundary: several of the operator's groups are facets of the *same*
underlying authority speaking through different surfaces (Board is a read of Ticket+Workflow facts, not a
second store), and a few name a UI page rather than a Module. `ARCHITECTURE.md` already derives a smaller,
cleaner set of **nine Deep Modules** from the same requirements the operator is describing from the outside.
This document regroups his 13 groups onto that existing three-layer architecture rather than inventing a
fourth taxonomy, because a fourth taxonomy is exactly the kind of "second source of truth" `DECISIONS.md`
D8/D21/D28 repeatedly forbid.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│ LAYER 3 — ADAPTERS  (replaceable, plug-and-play, earned per Seam)        │
│   Harness · Supervisor · Target · Workspace · Telemetry · Effect         │
│   Provider — each an immutable-revision contract; kernel never imports   │
│   an adapter's implementation, only its pinned Interface (D10)           │
├─────────────────────────────────────────────────────────────────────────┤
│ LAYER 2 — SURFACES  (how humans and agents touch the kernel)             │
│   UI  — 5 primary surfaces: Home · Board · Ticket · Fleet · Analytics    │
│   CLI — ctowerctl/ctl, generated from the same OpenAPI as the UI         │
│   Dual-surface law: every capability is API-first; UI and CLI are both   │
│   thin clients over it (`SPEC.md` §"Document contract")                  │
├─────────────────────────────────────────────────────────────────────────┤
│ LAYER 1 — KERNEL  (owns truth; private-VPS trust plane)                  │
│   Record & Access   — Access/Record: identity, authorization, the        │
│                        durable hash-chained event log                    │
│   Work & Delivery    — Work, Proof, Attention, Projections: the ticket,  │
│                        its evidence, human-need routing, derived views   │
│   Process             — Workflow, Catalog: stage graphs, execution       │
│                        policy, and every versioned configuration object  │
│                        (agents, personas, skills, templates live here    │
│                        as Catalog *data*, not code)                      │
│   Execution           — Runtime, Effects: jobs/leases/CommandGuard,      │
│                        and the external-effect boundary                  │
└─────────────────────────────────────────────────────────────────────────┘
```

Every Module in Layer 1 hides its own complexity behind a small Interface (`ARCHITECTURE.md`
§"Deep Modules and dependency direction"); the invariant that makes this modular rather than a distributed
monolith is that dependency arrows only point one way — `Work|Proof|Workflow|Attention|Runtime -> Record ->
Telemetry` — and a repository policy check fails the build on a cycle. Layer 2 exists because two very
different audiences need the same truth: an operator wants a page; an agent wants a typed contract it can
retry against deterministically. Layer 3 exists because "who does the work" — Claude Code, Codex, Hermes, a
future remote provider — must never leak into what the kernel considers true; D1 locked this in the first
architecture decision the operator made: **all harnesses are adapters**, the orchestration layer is owned,
never trapped inside one vendor's product.

#### Layer 1 detail — the nine Deep Modules

| Module | Owns | One-line invariant |
|---|---|---|
| **Access / Record** | Authentication, revision-pinned project grants, authorization, the append-only hash-chained event log, idempotency, outbox | Every authenticated request resolves to exactly one Actor and one authority record — no transport invents a second identity model (INV-73) |
| **Catalog** | One `VersionedComponent` envelope for every publishable configuration object — Workflow, Execution Policy, Agent Profile, Persona, Skill, Tool, Environment, Project, Company, Goal, Checkpoint, Notification/Integration | A published revision is immutable and content-digested; nothing "configures itself" by editing a live row |
| **Work** | Permanent tickets, lifecycle episodes, custody, relations, priority facts, typed blockers, Board intents | A ticket's ID never changes and it never becomes a second god object — everything else *links* to it, nothing lives inside it |
| **Proof** | Criteria, artifacts, the evidence DAG, verifier independence, gate instances/verdicts, invalidation | No close without current evidence for the exact digest of the work it checks — stale evidence stops counting the moment the work changes |
| **Attention** | The typed, append-only findings feed and Needs You's policy-qualified projection | A human need is a stated fact with a kind, owner, and reason — never inferred from a blocker's shape or a stage's age |
| **Workflow** | Arbitrary pinned stage graphs, legal edges, execution-policy composition, typed routes, terminal contracts | The engine has no hard-coded process; `engineering.software-factory` is one package among many the same evaluator can run |
| **Runtime** | Accepted jobs, leases, fencing tokens, cursors, durable ACKs, checkpoints, the versioned CommandGuard decision | A lost worker is a fenced, resumable fact, never a silent success or an orphan |
| **Effects** | Scoped grants, release receipts, provider observations, incidents, rollback, external audit reconciliation | Passing a gate is never itself authority to deploy/send/pay — the effect boundary issues its own narrow, short-lived grant |
| **Projections** | Rebuildable Home, Board, Ticket, Fleet, Analytics, KPIs, contextual Project Delivery | Every read is a fold over the log at a stated watermark; delete it and replay must reproduce it byte-identically |

#### Layer 3 detail — the harness-adapter worked example

The operator named harness adapters explicitly as the pattern every other component should follow. Its
shape, already locked in `DECISIONS.md` D10:

```text
Runner Interface   — offer/accept/lease/start/event/terminal exchange, fencing,
                      ordered cursors, durable ACKs, checkpoint/recovery
Supervisor Interface — a small process-control vocabulary: probe, observe,
                      interrupt, terminate, snapshot, adopt
```

The invariant that makes this "plug-and-play" rather than a promise: every attempt pins an **immutable
effective-run manifest**, composed independently from `HarnessSpec`, `SupervisorSpec`, `TargetSpec`,
`WorkspaceSpec`, and `TelemetrySpec` revisions. An unknown, incompatible, or ungranted component is a
refusal, never a silent fallback to a generic process. A Seam is only public once **two real Adapters and
one conformance suite** exist for it — a single implementation, however good, is not indirection worth
paying for (D17.6's "a fake alone never earns indirection"). Concretely: the local direct-process Supervisor
and the tmux Supervisor Adapter earn the first public Seam together; Claude Code, Codex, and Hermes earn the
Harness Seam the same way. This is the actual mechanism by which "harness adapters" stay modular instead of
becoming another place-specific integration — and it is currently **designed, not built** (see Part 3).

### Mapping the operator's 13 groups onto this model

| His group | Lands in | Regroup rationale |
|---|---|---|
| **Ticket** | Work + Proof (Layer 1) | His 8 facets map 1:1: task definition → Ticket + Acceptance Criterion; evidence → Proof; workflow stages → Workflow; assignee → Assignment/custody interval; assets → Artifact; work status → the four orthogonal state axes (priority/lane/stage/delivery); priority → Priority fact; comments → Inbound-thread events attached to the ticket. No regroup — this is the one group ctower's domain model already matches almost verbatim. |
| **Board** | Projections (Layer 1) | Not a second store. It is a versioned fold over Work+Workflow+Attention+Proof facts — the six lanes are *derived* from `activity_class`, never stage names (`SPEC.md` §"Task-management foundation"). Regrouped because treating it as its own component invites exactly the "manual status field" failure mode D21 rejected. |
| **Routines** | A contract shared by Catalog + Workflow + Runtime, not a Module of its own | A Routine is a versioned trigger revision (Catalog data) that a deterministic scheduler beat (Workflow/Runtime) turns into a wake intent. It doesn't own execution or storage independently, so it isn't a tenth Module — it's the wiring between three existing ones (`SPEC.md` §"Wake, reasoning-heartbeat, routine, cron, and watchdog contract"). |
| **Agents** | Splits three ways, deliberately | *Profiles/Harness/Skills* declaration → Catalog (`Agent Profile`, `Persona`, `Skill`, `Tool/Capability` component kinds). *Disposable workers* → Runtime's `Execution run/session` (stateless, replaceable). *Durable commanders* → Access's durable Commander principal + custody (D9) — structurally different from a worker session: a Commander survives model swaps, context resets, and process restarts; a worker session does not outlive its job. *Harness/Supervisor/Target/Workspace/Telemetry* → Layer 3 Adapters. *Scripts and tools* → `Tool/Capability` Catalog kind + `ctowerctl` itself. *Memory* has no ctower home yet — see the gap noted in Part 3. |
| **Integrations and plugins** | Thinner than it looks | *External/system events* → Inbound thread ingestion (Communication, below). *Notifications* → Attention's Needs You delivery. What's left — genuine third-party plugin execution — is the deliberately deferred Extension Host (`DECISIONS.md` D11): a manifest is data, not code; nothing executes until an isolated invocation-scoped grant exists. |
| **Knowledge base** | No current ctower home | Zero hits for "knowledge base" anywhere in `SPEC.md`. The closest kernel primitive is the `Artifact / document / revision` aggregate (content-addressed, immutable revisions), but there is no retrieval/semantic layer, no per-org/per-project KB concept, and no MCP-based external connector. README lists this plainly on the "designed, not built" side ("Memory that lets a worker recall how something was solved months ago"). A genuine gap — not a regroup. |
| **Communication** | Splits cleanly | *Inbox (agent-to-agent)* and *Chat (human steering)* → the `Inbound thread/conversation` aggregate, one durable channel-neutral event log. *Terminal* → Runtime's live structured event stream, with the raw terminal kept only as a compatibility view (`SPEC.md` §"Live observation, steering, interruption, and reassignment"). *Comments* → typed events on that same thread, linked to a ticket. The embedded question — task.md vs. inbox — is Part 2 Q1. |
| **Workflows** | Workflow (Layer 1) | Stages → the pinned graph. Commanders and custody → the Assignment/custody interval aggregate plus D9's orchestration-plan revision. Dispatchers → wake/job dispatch inside Runtime, triggered by Workflow readiness. |
| **Metrics and KPIs** | Projections (Layer 1) | Not a separate store — versioned SQL/query artifacts over the same event log Board reads (`SPEC.md` §"KPIs"). Tokens/cost/duration/review-rounds/model-quality are named KPI rows already, not a new component. |
| **Observability** | Splits three ways | *Skill-usage effectiveness* → Retro/process-improvement facts. *LLM reasoning/tool/decision observability* → the Telemetry Adapter plus an Execution run's ordered event cursor. *Usage/subscription limits tracking* has no ctower home and arguably shouldn't get one — see Part 4's closing note. |
| **Templates (?)** | Formalizes an existing pattern, not a new one | Part 2 Q2. |
| **Organization and projects** | Access + Catalog + Projections | Commander-per-project → the configured Commander principal per Project grant. Company/project workspace → the `Workspace/checkpoint` aggregate. Knowledge base per org/project → same gap as above. Director-per-organization/portfolio-manager and editor/file-explorer are **named gaps** — see Part 3. |
| **Access control** | Access (Layer 1) | Project-scoped grants (machine plane, built) and OIDC human role bindings (`operator`/`commander`/`viewer`, scaffolded) are the two disjoint authority planes D31 locked; neither implies the other. |

### The reasoning behind this structure

Four forces, all already locked by the operator, produced this shape rather than a flatter one:

1. **Dogfooding.** ctower has to run its own delivery (epic #105) before it asks anyone else to trust it.
   That only works if the kernel is small enough to reason about end to end — nine Modules, not thirty
   services — while still being complete enough to actually replace Mission Control's ledgers.
2. **Modularity as a discipline, not a slogan.** D12 explicitly forbids a "parallel revision authority" —
   a second Factory table, a second workflow engine, a second template kind. Every regroup above chose to
   fold a named group into an *existing* Module rather than mint a new one, precisely because the operator's
   own prior decisions already ruled out the alternative.
3. **UI/CLI split.** Every capability is authored once against the API; the UI and CLI are both thin
   generated clients over the identical OpenAPI surface (`README.md` §"Scope, in the project's own words").
   This is why "Layer 2" is one row in the diagram, not two systems that can drift.
4. **Custody and gates.** A ticket has exactly one accountable custodian at a time, and a gate's independence
   rule is enforced at the same transactional boundary as the state change it guards — not as an
   after-the-fact audit. That single fact is why Access/Record sits underneath every other Module rather than
   beside them.

---

## Part 2 — The two design questions

### Q1 — Do we need task.md if we have inbox?

**Verdict: task.md does not survive as a loose file. It is absorbed into the Ticket, as the operator's own
Ticket taxonomy already implies.**

The two things are not competitors; they were never doing the same job, and conflating them is exactly what
produced the question.

- **The inbox is the async MESSAGE TRANSPORT.** In ctower's domain model this is the `Inbound
  thread/conversation` aggregate: a durable, channel-neutral, ordered log of dispatch pointers, findings,
  and pages. Its whole contract is capture-before-classify — nothing is lost, nothing is summarized away,
  and a message may or may not ever become a ticket (`SPEC.md` §"Omnibox classification and promotion").
  Mission Control's `state/inbox.jsonl` is the operational precursor to exactly this aggregate today.
- **task.md is the durable WORK CONTRACT.** Goal, acceptance criteria, verification, stop condition — the
  thing a crew is *held to*, not merely informed by. The operator's own Ticket taxonomy names this as facet
  1: "Task definition (goal, acceptance criteria)." That is not a coincidence; it is the same content,
  described from the operator's operational experience of writing task.md files by hand every time.

ctower's Ticket + Acceptance Criterion + typed evidence slots is that same contract, but strictly stronger
than a markdown file: criteria are **frozen** before evidence exists (so the bar can't quietly move to match
what got built), evidence is **digest-bound** to the exact version of the work it checks (so a task.md's
staleness problem — nobody re-reads it after week one — cannot happen silently), and a verdict from the
candidate's own author is **refused**, not merely discouraged (`docs/agents/operating-contract.md` Rule 9).
A markdown file enforces none of that; it is trusted by convention, and D3's own diagnosis (silent confident
failure) is what happens when a convention is the only enforcement.

**Counter-arguments, and why they don't change the verdict:**

- *"task.md is human-readable and git-diffable without an API."* True today, but this is a tooling gap, not
  an architectural reason to keep a second contract. The dual-surface law means `ctl ticket capture` / `ctl
  ticket query` is at least as inspectable — and considerably more trustworthy, since it's typed and
  evidence-bound rather than free text a crew can drift from unnoticed.
- *"task.md is useful for ad hoc handoffs outside the ledger — a subagent prompt, a one-off note."* This is
  precisely the failure mode ctower's whole thesis rejects: a second, unaudited record of what a crew is
  supposed to be doing, next to the audited one. If the handoff matters, it belongs on the ticket's Inbound
  thread as a comment event; if it doesn't, it shouldn't be durable at all.
- *"Existing task.md files represent real, already-invested work."* Correct, and the migration path already
  exists: they are not bulk-imported as authority (D27 forbids implicit migration authority). Open items
  become ticket captures with the task.md content reborn as frozen criteria/evidence slots at the `frame`
  stage; closed items become signed read-only provenance, same as the rest of the legacy corpus.

**Migration implication.** New work stops minting a task.md file the moment `ctl ticket capture` exists for
that project (already true for `manibo` per D30/CT-I1-011). The inbox does not go away — it becomes the
Inbound thread, carrying exactly the message-transport role it always had, now durably linked to the tickets
it creates or references instead of living beside them as a separate, unlinked ledger.

### Q2 — Do Templates earn a place?

**Verdict: yes, but as the formalization of an instantiation layer the Catalog already has the bones of —
not as a fifteenth Catalog component kind — and sequenced after the core primitives, not before them.**

Modular, plug-and-play architecture genuinely requires an instantiation layer: a project is cloned from a
project template, a workflow is a stage-set template, a task class needs an AC/verification template. The
operator is right that this is missing today. Where a naive answer goes wrong is treating "Templates" as a
new thing to build. It is not — ctower already has the mechanism, just not the ergonomics:

- **A CompanyBundle *is* a company template.** It is a portable, secret-free YAML set that round-trips
  through `validate -> plan -> apply -> export` with **zero semantic diff** guaranteed (`SPEC.md`
  §"CompanyBundle validate, plan, apply, and export"). Apply it to a fresh tenant and you have instantiated
  a company from a known-good starting state — that is a template by any reasonable definition, already
  built as a contract.
- **A Project component *is* a project template.** `packs/components/projects/ctower.control-plane/v1.yaml`,
  `manibo.delivery/v1.yaml`, and `bh-loop.delivery/v1.yaml` already show the pattern: a Project is versioned
  data referencing a starter checkpoint hierarchy, not a hand-built one-off each time.
- **A Ticket Schema component *is* a task-class template**, once CT-I2-001 publishes the `ticket_schema`
  component kind — reusable criterion/evidence-definition vocabulary a Workflow's `stage.evidence[]`
  resolves against, rather than each stage inventing its own contract prose.
- **A Workflow Definition revision *is* a workflow template.** The whole point of the S7/S8 five-layer
  authoring contract is that a Workflow YAML is authored once, published as an immutable revision, and
  reused by every ticket that pins it.

Adding a literal `Template` Catalog kind on top of these would be exactly the "parallel revision authority"
D12 forbids: a second place a workflow's shape or a project's starting state could be described, competing
with the `VersionedComponent` envelope that already owns identity, lifecycle, and provenance for all of
them. The correct move is to recognize that **reusability is already a property of the existing kinds**, not
a missing kind.

**What is actually missing** is ergonomics: a curated, named, versioned library of starter bundles ("
software-factory-starter", "research-starter") and a one-line instantiation path (`ctl company bundle init
--from <starter>`), so "start a new project" doesn't mean hand-writing YAML from scratch. That is real,
worth building, and correctly scoped as **data plus a CLI convenience**, not a new architectural component.

**Sequencing.** A starter-bundle library is worthless before there is a coherent thing to template — the
`ticket_schema` layer (CT-I2-001) and a working S7/S8 workflow-authoring round trip need to exist first, or
the "template" would just be a workflow with nothing yet to resolve its evidence definitions against. Land
it alongside the I2.4 Admin/CompanyBundle UI surface, after the core primitives it templates are real. Part 4
places it there explicitly.

---

## Part 3 — Built pieces mapped to the structure

Evidence below is checked against `origin/main` (`2f385fa`, current at authoring time — the local checkout
lagged 22 commits and is not authoritative for this section). Status labels reuse `docs/project-status.md`'s
own vocabulary where they apply: **Development fixture** (code + tests exist, not a supported product path),
**Development shadow** (operator-installable, loopback-only, non-authoritative), **Planned** (specified, not
built), plus **BUILT / PARTIAL / NOT-STARTED** for pieces the canonical status page doesn't itself track.

### Kernel (Layer 1)

| Component | Status | Evidence | Reality |
|---|---|---|---|
| **Ticket / Work** | Development fixture | `README.md` "what works today": open, prioritize, assign, block/unblock, defer, comment, link, resolve, close | Real and tested against Postgres; not a hosted service |
| **Board fold (six lanes)** | Development fixture | `packages/ctower-kernel/src/ctower_kernel/projections/_board_sql.py:214-407`; `tests/modules/projections/test_board_fold.py`; API: `apps/ctower-api/src/ctower_api/_board_routes.py` | The lane derivation from `activity_class` is genuinely implemented and unit-tested, not a mockup |
| **Board — #207 "read-only operator surface over the shadow record"** | **BUILT**, merged | `gh pr view 207` → MERGED 2026-08-03, `f8f73c5` | Real: a 10+ route Next.js surface reading `/v1/board` |
| **Board — #234 "one crew in full — the profile behind every roster row"** | **BUILT**, merged | `gh pr view 234` → MERGED 2026-08-03, `83a9bdb` | Crew-profile pages, not board projection per se — correctly cited as a Board-adjacent PR, not the fold itself |
| **Board — #326 "wire INV-66/67 context-set fields"** | **NOT MERGED**, in flight | `gh pr view 326` → OPEN; `label_vocabulary`/`attention_kind_catalog`/`change_reference` absent from `origin/main` | The claim "in flight" is accurate; the context set (tenant identity, change refs, labels, human-waiting, delivery-surface availability) is speced but not yet on main |
| **Proof / Evidence** | Development fixture | README: "proof tied to the exact version of the work it checked... change the work and proof stops counting" | Built and enforced at resolve/close; not yet at every stage (`[planned]` in `docs/concepts/map.md` step 7a) |
| **Attention / Needs You** | **PARTIAL** | `docs/concepts/map.md` step 12a: "Present in the kernel, with no API to read it yet" | The typed findings feed exists in the kernel; there is no way to read Needs You from outside it yet |
| **Workflow evaluator + four-stage fixture** | Development fixture | `packs/workflows/ctower.trust-spine-four-stage/v1.yaml`; `tests/acceptance/increment-1/test_four_stage_workflow.py` | `capture -> frame -> verify -> close` genuinely runs against real Postgres through the generic evaluator, not a hard-coded state machine |
| **Runtime (jobs/leases/CommandGuard)** | **NOT-STARTED** | `apps/ctower-runner/` and `packages/ctower-runner-sdk/` each contain only a `README.md` stating "Product code begins in Increment 2" | Fully specified (D10, D19, D20); zero execution code exists yet — this is I2.2 scope, not a gap in what's been attempted so far |
| **Effects (deploy/release/incident)** | Planned | README's "designed, not built": "anything that reaches the outside world" | I2.5 scope; no code |
| **CompanyBundle / Catalog** | Development fixture | `project-status.md`: "Strict validate/plan/apply/export... exercised against real PostgreSQL" | Real, atomic, idempotent; does not yet activate runners/effects |
| **Feed — CT-I1-012 / #299 "typed project event feed"** | **BUILT**, merged | `gh pr view 299` → MERGED 2026-08-05, `bad5043`; `GET /v1/projects/{project_key}/events`; `packages/ctower-kernel/src/ctower_kernel/record/project_events.py`; `tests/contracts/http/test_project_event_feed.py`, `tests/acceptance/increment-1/test_portfolio_board.py` | Genuinely typed (6 event kinds), scoped, and tested at the wire level — the claim is accurate as stated |

### Surfaces (Layer 2)

| Component | Status | Evidence | Reality |
|---|---|---|---|
| **Protected CLI (`ctowerctl`/`ctl`)** | Development fixture | `docs/agents/operating-contract.md`; encrypted owner-only spool with crash/torn-write/quarantine handling | Real, and the actual reference implementation of "CLI for agents" — every exit code and refusal is typed |
| **Terminal — #322 "wire the live terminal into the crew profile and seat aggregate"** | **NOT MERGED**, in flight | `gh pr view 322` → OPEN | The "pinned, both-gates-green" framing in the seed brief does not hold at time of writing — it's an open PR |
| **Terminal — underlying tmux capture** | **BUILT**, but scoped narrower than claimed | `apps/ctower-ui/src/read/sources/tmuxBridge.ts` (uses `tmux list-sessions`/`capture-pane -p`), wired only into the `/feed` route (`apps/ctower-ui/src/app/feed/page.tsx:98`) via #207 | Live tmux capture is real and tailnet-bound, but today it feeds the thread/feed view — not the crew/seat terminal panels #322 is adding |
| **Chatbot composer** | **Mockup, by design** | `apps/ctower-ui/src/surfaces/feed/Composer.tsx` — deliberately disabled textarea/button, comment: "Read-only v1 has no mutation path... inert by design" | Confirmed: taste-only mockup, zero backend, no LLM wiring anywhere in the repo |
| **`apps/ctower-ui` — the whole surface** | **Worth the operator's attention** | 12+ route surfaces exist (`ticket`, `crew`, `board`, `feed`, `inbox`, `team`, `explorer`, `metrics`, `heartbeats`, `files`, `workspace`, `tree`) on Next.js 16 / React 19, with two merged "feat(ui)" PRs | `README.md`'s "what works today" table lists no web interface at all, and D22/D23 explicitly say I1 "introduces no browser product route." Both are stale against reality: a real browser surface is already running ahead of the SPEC's own I2.4 gate. This is not flagged as wrong — the operator may well want early UI dogfood — but it is a genuine documentation/canonical-status drift worth a decision, not a silent gap. |
| **`apps/ctower-web`** | **NOT-STARTED** | `apps/ctower-web/src/architecture.ts` is the entire source tree | A real stub, not a second product; confirms the memory that `ctower-ui` and `ctower-web` are not interchangeable names for the same thing |

### Adapters (Layer 3)

| Component | Status | Evidence | Reality |
|---|---|---|---|
| **Harness / Supervisor adapters** | **NOT-STARTED** | Zero `class.*Supervisor` hits repo-wide; `contracts/components/supervisor.schema.json`'s `execution` field is a hardcoded `const: "not_exercised"`; `packs/components/supervisors/local.process/v1.yaml` same | The operator's named worked example for modularity is currently **design rationale only** (D10) — no adapter code, no `bin/mux`-equivalent, no conformance fake exists in `packages/ctower-kernel`. The live worked example today is operational, not architectural: Mission Control's `bin/mux` + `crew/roles/*` + `board/model-routing-policy.md` already runs Claude Code, Codex, and Hermes as swappable harnesses for real crews — it is the pre-Seam precedent, not yet folded into ctower's kernel. |
| **Agent Profile / Persona / Skill (Catalog data)** | **Declarable, does nothing yet** | `packs/components/personas/operator.commander/v1.yaml`, `packs/components/agent-profiles/commander.protected-cli/v1.yaml` | `docs/concepts/map.md` 1a: "You can declare that much today and nothing runs it — declaring an agent profile does not start an agent" |

### Access control

| Component | Status | Evidence | Reality |
|---|---|---|---|
| **Project-seat machine credentials** | **BUILT**, merged | `#198` "issue scoped project-seat credentials" (0.5.0), `#191` "carry the seat facts" (0.5.0); migration 0039 | Real, scoped, revocable |
| **OIDC scaffold — #324** | **PARTIAL**, open | `gh pr view 324` → OPEN; own description: "Stops at provider binding"; `packages/ctower-kernel/src/ctower_kernel/access/oidc.py`, `_login_gate.py` with `enforcing=False` by default | Provider-agnostic OIDC machinery exists and is dark by default; human login is not live |

### Organization and projects

| Component | Status | Evidence | Reality |
|---|---|---|---|
| **Portfolio topology (D30): `ctower`/`manibo`/`bh-loop` as Projects** | **PARTIAL** | Issue #185 (epic, open) → #189 (merged docs plan) → #192/#198 (merged credentials) → #197 (merged read-model isolation) → #222 (merged prohibited-data-class refusal) | The topology and isolation are real and tested (`tests/acceptance/increment-1/test_manibo_ordinary_intake.py`) |
| **Manibo import ("53 cards serving")** | **PARTIAL, with a named limitation** | Crew-log evidence cited in issues #317/#320 (both open, filed 2026-08-05): 59 submitted / 53 accepted | Imported cards carry only their **import-time** backlog stage — there is no live-lane sync from the source board back into ctower, "by design, not a code defect" per #317/#320. Worth stating precisely rather than as a flat "migration machinery" claim. |
| **Director / portfolio-manager role** | **NOT-STARTED, named gap** | No portfolio-spanning principal exists in Access's authority model — only a per-project Commander and the single operator | Today's "Portfolio Director" is a Mission Control crew-profile role (`board/crew-profiles.md`), not a ctower Access concept. The operator's own "director per organization (portfolio manager)" sub-item has no kernel home yet. |
| **Company/project/product workspace** | **PARTIAL** | Only `packs/components/workspaces/local.checkout/v1.yaml` exists | A real primitive with one concrete instance, no browsable workspace surface (that's I2.4's Fleet contextual view) |
| **Editor and file explorer** | **NOT-STARTED, explicitly deferred** | `SPEC.md` §"Explicit do-not-build-yet list": "browser IDE replacement" | Named out of scope for both increments, not merely unstarted |

### Workflows / gates / dogfood tooling

| Component | Status | Evidence | Reality |
|---|---|---|---|
| **Documentation/landing-boundary gate — "one gate, two facts"** | **BUILT, live, but narrow** | PR #283 merged (`landing-boundary.yml` + `tools/landing_boundary/ci_conclusion.py`); `tests/landing_boundary/test_ci_conclusion.py` | This is a real, currently-required GitHub check on ctower's own repo today — genuine dogfood. But D32 and `SPEC.md:2200` are explicit: the general software-factory documentation gate "governs no merge today" for product tickets — it's I2 work behind full I1 exit. Issue #220 ("documentation gate is unskippable") is still open. |
| **FIFO merge train** | **BUILT, but not in ctower** | `board/ctower-merge-train-mechanism.md`; executor `tools/ctower-migration-drive` (cron, ~15 min) reading `state/.ctower-merge-queue` | Real and running, but it is Mission Control tooling orchestrating around ctower's GitHub repo from the outside — not ctower kernel code. A clean candidate for later absorption into a ctower-native Routine + Workflow, not yet attempted. |
| **Cross-model review topology** | **Process, not code** | `DECISIONS.md:1117` — "the normal two-round cross-model gates" | A real operating convention (Codex/Claude/GLM alternation per `board/model-routing-policy.md`), described in prose, not wired as an Execution Policy revision in ctower yet |
| **Ticket-close gate** | **Speced, not enforcing product tickets** | `SPEC.md` §"The fleet-lifecycle policy package" | D34's `fleet-lifecycle@1` package is authored; evaluation rides CT-I2-006, which is I2 scope |

### Also mapped, briefly

| Component | Status | Evidence |
|---|---|---|
| Personas/souls (Agents > Profiles) | **Mission Control-native today; ctower-declarable only** | `personas/*.md` + `crew/roles/*/soul.md` (10 seats) vs. `packs/components/personas/`, `packs/components/agent-profiles/` (declared, inert) |
| Crew/commander sessions (disposable vs. durable) | **Split status** | Session facts BUILT (D33/#258, merged, 0.7.0: "record: work sessions become facts the record can prove"); the Runtime that would actually run a disposable worker is NOT-STARTED (see above) |
| The inbox | **BUILT in kernel, unmigrated operationally** | `project-status.md`: "Inbound threads and intake — Development fixture"; Mission Control's `state/inbox.jsonl` remains the live operational instance |
| Request/crew-log ledgers | **Explicit co-source, not yet superseded** | `SPEC.md:482-484` names "the shared Mission Control R-counter" directly as the source-reference scheme ctower's own intake still relies on |
| KPIs/crew-log scoreboards | **Speced in ctower; running only in Mission Control** | `SPEC.md` §"KPIs" fully defines 25+ versioned metrics; no dashboard/API surfaces them yet. `board/crew-kpis.md` and `board/factory-kpis.md` are the live proto today |
| Capacity-sentinel/model-watch | **NOT-STARTED in ctower; live externally** | `tools/capacity-sentinel`, `tools/crew-model-watch`, `tools/claude-model-watch`, `state/capacity.json` — real, running, but outside ctower's kernel boundary entirely |
| Epic #105 — "ctower runs its own delivery" | **Open, in progress** | `gh issue view 105`: "our work items and their evidence already live in ctower's records; the remaining step is closing the loop." This is the dogfood epic Part 4 anchors to I2.6's golden ticket. |

---

## Part 4 — The incremental roadmap

This is **not a fourth scope model.** `IMPLEMENTATION-ROADMAP.md` already locks one priority-and-structure-
ordered checkpoint sequence derived from `SPEC.md`, and `CLAUDE.md` forbids a competing roadmap. What follows
is that same sequence, read through the operator's component-group lens, with a planning-level task count per
phase. The task counts are outcome-AC-style lines for sizing conversation only; they carry no backlog
authority, create no ticket, and do not supersede the stable `CT-*` IDs and validation commands that already
own each checkpoint's real exit contract.

**Dual-surface note that holds across every phase below:** the CLI is the parity baseline through I1 by
design (D22/D23 — "no I1 browser product implementation"). UI parity does not arrive incrementally
per phase; all five surfaces realize together at I2.4, over the same generated clients the CLI already uses.
Phases before I2.4 are agent/CLI-first by explicit SPEC choice, not by omission — `apps/ctower-ui`'s early,
parallel build (Part 3) is the one place this is already being anticipated ahead of schedule.

### Phase 0 — what exists today

Restated compactly from Part 3: Ticket/Work/Proof/Board fold/Feed/CompanyBundle are development fixtures;
project-seat access control and portfolio topology are real with named limits; OIDC, Runtime, Effects, and
harness adapters are speced but not built; `apps/ctower-ui` is a real early surface running ahead of the
formal I2.4 gate. Mission Control's personas, inbox, R-counter, KPI scoreboards, merge-train, and
capacity-sentinel remain the live operational substrate ctower has not yet absorbed.

### Phase 1 — durability + spool-CLI closure (I1.3–I1.4)

**Component focus:** Record & Access (durability), CLI-for-agents baseline.

1. Off-host WAL/record acknowledgement proves host-loss RPO 0 for accepted records.
2. Isolated restore verifies chains, anchors, objects, tombstones, and the signed source inventory.
3. Real reboot recovery passes with poison-outbox handling intact.
4. `ctowerctl`/`ctl` spool survives crash/torn-write/concurrent-writer/quarantine chaos with one stable
   command ID per intent.

*4 tasks.*

### Phase 2 — trust-spine fixture + fresh Project Delivery + dogfood GO (I1.6–I1.7)

**Component focus:** Work + Proof + Projections, Organization and projects.

5. The four-stage fixture runs end to end through the final generic evaluator with an exact unmet checklist
   on every refusal.
6. Company → Project → checkpoint hierarchy and compact Project Delivery projection exist on a fresh
   database for all three portfolio projects.
7. CT-I1-008 records a `GO_WITH_LIMITS` verdict for the reviewed reconstructible cohort.
8. Per-slot seat accountability (D28) is visible on qualifying stage evidence, assigned and signing seats
   independently.

*4 tasks.*

### Phase 3 — portfolio import chain + shared auth (I1.8)

**Component focus:** Access control, Communication (feed), Organization and projects.

9. Immutable Project identities and grant-aware custody land for all three projects.
10. Scoped isolation and each project's onboarding configuration are Commander-authored.
11. `manibo`'s remaining backlog enters item by item with the same live-lane-sync gap named in Part 3
    resolved or explicitly re-scoped.
12. The project-scoped typed feed (#299, already built) gains its remaining consumers.
13. Discovery-driven OIDC (#324) moves from scaffold to enforcing, alongside the unchanged machine plane.

*5 tasks.*

### Phase 4 — CP3-D + full normative I1 exit

**Component focus:** Record & Access durability closure — the hard gate everything in I2 depends on.

14. External-failure-domain acknowledgement is proven, not merely designed.
15. Key recovery and isolated destructive restore pass with measured RPO/RTO.
16. Full I1 exit is recorded; CT-I2-001 is authorized (never before this, regardless of any `GO_WITH_LIMITS`).

*3 tasks.*

### Phase 5 — deepen Workflow + the software-factory package (I2.1)

**Component focus:** Workflows, Templates (the `ticket_schema` layer this document's Q2 verdict depends on).

17. The strict S7/S8 five-layer Workflow Definition source-schema, resolved-plan, and publish gates all pass.
18. The `ticket_schema` Catalog kind is added and layer-4 evidence definitions resolve through it.
19. `engineering.software-factory@1` materializes its complete `sf.e00..e15` edge table with typed failure
    routes.
20. A non-engineering package (a different four-stage graph) runs on the same evaluator, proving the engine
    has no hidden software-factory branch.

*4 tasks — and the first point where a starter-bundle "template" library becomes worth building, per Q2.*

### Phase 6 — Runtime, CommandGuard, and the harness-adapter Seam (I2.2)

**Component focus:** Agents (Runtime + Adapters) — **this is where the operator's named worked example
actually gets built**, not merely designed.

21. Accepted/leased/running/terminal job states, fencing, and cursor replay are implemented against a real
    runner.
22. The direct-process and tmux Supervisor Adapters both exist and pass one shared conformance suite —
    earning the public Supervisor Seam per D10's two-real-Adapters rule.
23. The versioned CommandGuard decision is enforced at the final dispatch boundary for every registered
    Adapter, with zero execution on `block`/`needs_operator`.
24. Forced runner loss, lease expiry, and reconciliation resume checkpointable work within the specified SLO.

*4 tasks.*

### Phase 7 — activate the durable Commander (I2.3)

**Component focus:** Agents (durable commander), Routines/wake.

25. Strongest-healthy-profile resolution runs per bounded reasoning job.
26. One durable Commander principal keeps accountable custody across a forced model/process/context
    replacement, with plan history and counters intact.

*2 tasks.*

### Phase 8 — browser realization + Metrics/Observability surfaces (I2.4)

**Component focus:** Board/Ticket/Fleet/Analytics UI parity, Metrics and KPIs, Observability, the Templates
starter-library UX.

27. All five primary surfaces realize over generated clients with full run reconstruction after restart.
28. Needs You precision/recall targets are met with no false-calm state.
29. The Analytics surface exposes the already-specified KPI definitions (tokens, cost/stage, duration/stage,
    review rounds) as real queries, not prose.
30. Project Delivery interactive row detail ships with per-slot seat visibility.
31. A curated starter-CompanyBundle library and `company bundle init --from <starter>` ship in the Admin
    surface (this document's Q2 verdict).

*5 tasks.*

### Phase 9 — Effects, release trust, incident recovery (I2.5)

**Component focus:** Integrations/Effects — the "external events, notifications" facet of the operator's
Integrations group that finally gets a real boundary.

32. Scoped effect grants and immutable receipts exist at the actual deploy/send boundary.
33. The root-owned release supervisor verifies artifact provenance before install, independent of the
    application's own claim.
34. A production smoke/live-QA failure opens an incident, revokes grants, and proves verified rollback before
    any repair dispatch.

*3 tasks.*

### Phase 10 — one software-factory golden ticket (I2.6)

**Component focus:** proof of the whole system — this is where epic #105 closes.

35. One permanent ticket traverses all seven delivery-sprint groups, with `design` as its only evidence-
    backed skip.
36. `GET /v1/meta/build` and `ctl meta build` agree with the deployed release.
37. Forced runner loss, one Commander reasoning-job failover, one candidate invalidation, and one production
    rollback rehearsal are all exercised on the same ticket.
38. The retro closes epic #105 with an evidence-backed improvement or no-change decision.

*4 tasks.*

**Total across Phases 1–10: 38 planning-level tasks**, none of which authorize work by existing — they are a
structural reading of the same locked sequence, sized for conversation with the operator, not a new backlog.

### What this roadmap deliberately does not schedule

- **Knowledge base and general Observability (usage/subscription-limits tracking)** have no phase above
  because they have no architectural home yet, and forcing one in would be inventing scope the operator
  didn't ask for. The honest options, for the operator's taste pass: (a) knowledge base becomes a future
  Catalog/Artifact extension once the Extension Host (D11) is earned, since RAG-style retrieval is a natural
  first executable extension; (b) usage/subscription-limits tracking may simply stay outside ctower's kernel
  boundary permanently — it is provider-quota infrastructure, not ticket/workflow truth, and Mission
  Control's `capacity-sentinel` already does this job adequately as external tooling.
- **The Director/portfolio-manager role** has no phase because there is no proposed Access-model change to
  attach it to yet — naming the gap in Part 3 is the deliverable here; deciding whether it becomes a fourth
  human role (beside operator/commander/viewer) is the operator's call, not this document's.
- **Mission Control's merge-train, R-counter, and KPI scoreboards** are not scheduled for absorption into
  ctower here, even though Part 3 notes they are clean candidates for it, because the operator's brief did
  not ask for that migration — only for this document to be honest about where the real mechanism lives
  today.
