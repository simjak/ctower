# ctower — locked decisions & working assumptions

Ledger for the dedicated architecture discussion. Append-only; a locked decision is only reopened by the operator.

## D1 — Build strategy: LAYER-ON-TOP (locked 2026-07-13, operator)
ctower **owns** the orchestration layer — ticket store+graph+timeline, catalog (flows/gates/routing),
souls+skills, analytics, board webUI+API+CLI, access control. **All harnesses are adapters** underneath:
Claude/Fable (commander), Codex (engineer/QA/review), **Hermes = ingress/cron/connectors/night-watch adapter**
(demoted from candidate-platform), Pi/GLM (research/prose). Delivery path = incremental growth from the current
MC substrate (tools/req, crew-log, bin/mux, Control Tower) per SPEC P0–P6. Rationale: the core value
(durable trackable completion + improvement loop) lives in the owned layer; extending Hermes would trap it
inside a harness we don't own — un-sellable, single-harness lock-in.

Corollary (persona portability): personas are harness-neutral bundles
`personas/<name>/{soul.md, agents.md, skills.yaml, tools.yaml}`; each adapter **materializes** them natively
(Claude→CLAUDE.md+skills, Codex→AGENTS.md, Hermes→context-files, Pi→system prompt). `tools.yaml` feeds access control.

## Working assumptions (A2/A4 ratified by landed research 2026-07-13; contest freely)
- **A2 Compute (RATIFIED, refined — research lane 5):** VPS move + Control Tower auth hardening
  FIRST (reuses 100% of bin/mux/tmux/CT; CT's steer path already exists via /api/crew/<id>/steer).
  **crabbox.sh REJECTED as platform** (short-lived execution broker, explicitly not a persistence or
  auth layer; Crabfleet RBAC = pattern to copy, not adopt). Fly.io Sprites = the isolation upgrade
  for high-blast-radius crews later, not the default. Highest-leverage missing guard: per-crew
  network egress allowlisting; §6 prose gates should become machine-checked flow-engine gates.
- **A3 Store:** Postgres (analytics + board need SQL), but append-only event log stays the
  canonical source of truth; Postgres is the rebuildable projection. (Timing moved to day-one by D6.)
- **A4 Brain (RATIFIED, refined — research lane 3):** gbrain already ships a first-class Postgres+
  pgvector engine; remote multi-agent HTTP MCP HARD-REQUIRES the Postgres engine (PGLite cannot
  serve remote agents). Path: single Hetzner-VPS Postgres+pgvector now (no HA) → Autobase-on-Hetzner
  when load-bearing (spike connection-string/failover + real cost first) → Supabase = safe fallback.
  Per-crew OAuth clients scoped by --source. gbrain's "Minions" Postgres job queue noted as a
  reusable durable-work-queue primitive.
- **A5 WebUI v1 scope:** board + ticket detail + comments-as-steering + human-gate approvals + crew
  evidence view; "commander from browser" v1 = ttyd web terminal on `tmux -L mc`; real chat surface v1.5.

## D2 — WebUI journey forks (locked 2026-07-13, operator)
- **Front door = omnibox-first.** One input on Home; intake classifies discussion|actionable|event.
  Chat IS intake; a structured create-form is a power-user shortcut only.
- **Steering = dual, timeline-captured.** Default async via ticket comments; direct crew chat allowed
  for sync course-correction but the exchange is auto-captured onto the ticket timeline. One history, two speeds.
- **Home = needs-you inbox.** Gates + escalations + questions first; board one click away.
  Serves the ≤3-4-live-threads mental-load north star.
- The 5 surfaces of the webUI: Home(needs-you) · Board · Ticket detail(timeline/comments/evidence/files) ·
  Fleet · Analytics. Visual language: GCP-console style (white, semantic chips, no blue-on-black).

## Working assumptions — ticket model (Part 2, derived from the journey; contest freely)
- **A6 Everything is a timeline event; the snapshot stays thin.** Comments, steering, assignee history,
  skill usage, session metrics are EVENT KINDS (`comment · steer{channel} · assignee_changed ·
  skill_used{skill,version} · evidence_attached · session_reviewed{tokens,cost,duration,goal_met}`),
  not new tables/fields. Any view = a fold over the log.
- **A7 References ≠ evidence, and evidence is criterion-bound.** `refs[]` = inputs (spec, design,
  meeting notes, KB precedent). `acceptance[]` = [{criterion, evidence[]}] = outputs; RESOLVE IS BLOCKED
  until every acceptance criterion has evidence; the human-gate card auto-assembles from `acceptance[]`.
- **A8 Ticket IDs (revised 2026-07-13 by the wedge design — IDs never mutate):** a ticket's ID is
  permanent from birth. Typed intake that knows the department at creation mints the dept prefix
  (alert→INC-…); everything else mints `TKT-…` and KEEPS it — department is a field set at triage,
  the ID is just a name. Legacy R### backfills as TKT-### with `legacy_ref`. (Original A8 said
  "TKT- only pre-triage"; revised because mutating IDs breaks references.)
- **A6 naming reconciliation (2026-07-13):** slice-1 canonical event vocabulary lives in
  DESIGN-ctower-office-hours.md §Wedge Contract; `assigned{from,to}` replaces `assignee_changed`;
  `steer` = `comment` with `channel: direct|comment` + transcript ref. Supersedes SPEC §2.2 enum.
- **A9 Cost is folded, never stored:** ticket cost = Σ its crews' `session_reviewed` events.

## D3 — Office-hours outcomes (locked 2026-07-13, operator; /office-hours question IDs in parens)
- **Core stance (operator's words):** *"First I'm solving my own problems. I'm not competing with
  anybody. If I solve my own problems, then perhaps it is useful for others. If not, I still solved
  my problems."* This is the product's north-star framing — the landscape gap is evidence, not a
  competitive motivation.
- **Goal (OH-D1):** internal workhorse first; sellability = design constraint (config-not-hardcode,
  API-first dual-surface), not a v1 goal.
- **Dominant pain (OH-D2):** operator mental load (chasing status across cmux/tmux/chat/boards).
- **Wedge (OH-D3/D3.1):** ticket event log + thin needs-you fold as ONE slice — operator overrode
  quick-relief in favor of the durable spine, then accepted the fold synthesis.
- **Observed surprises (OH-D4):** silent confident failure + scope-creep + agents exceed
  expectations ⇒ thesis: capability is not the constraint; TRUST in agent output is. ctower = the
  trust layer (evidence-bound tickets, independent gates, session review).
- **Premises P1-P5 ratified (OH-D6):** feel-it-slice-first (amended: within B, walking skeleton,
  relief ~2-3 wks) · lie-proof desk is the point · own-problems-first · vendors are USB sticks ·
  no proof, no done (evidence weight scales by ticket type).
- **Second opinion (OH-D7):** skipped by operator.
- **Approach (OH-D8):** B — service from day one (Postgres event store + API + CLI + needs-you view),
  walking-skeleton discipline. **Supersedes SPEC §10 P0-P1 file/git store phasing; resolves SPEC §12
  open-decisions 1 (Postgres now) and 4 (single-operator bearer token now).** Approach A (grow the
  tools) rejected as first move; C (fork Vibe-Kanban/amux chassis) rejected (foreign data model,
  proven upstream-death risk).
- **Process note:** deep technical discussion (schemas, endpoints, part-by-part) happens AFTER the
  what-to-build lock — this ledger + the design doc are the lock artifact.

## D4 — THE key metric (operator, 2026-07-13): OPERATOR ATTENTION
The product's north-star measurement is **how much operator attention the system requires per unit
of completed work** — attention-minutes per resolved ticket, interrupts/day, morning-sweep time,
operator-bypass count. Durability, observability, and visibility all serve this: visibility exists
so attention is only drawn when genuinely needed (needs-you), never for status-chasing. Every
feature must answer: does this reduce the attention the fleet demands from the operator?

## D5 — CEO review of the full corpus: LOCK HELD + 7 wedge amendments (locked 2026-07-13, operator: "fold them in")
Review artifact: REVIEW-ceo-2026-07-13.md (Fable 12 findings + Codex-xhigh outside voice 24 findings;
4 confirmed criticals; 1 cross-model tension). Amendments folded into DESIGN rev 4 §Wedge Contract amendments:
(1) per-principal tokens + server-derived actor + protected event kinds · (2) server-enforced P5
(`criterion_added`/`criteria_frozen` join the vocabulary; `resolved` = server-validated transition) ·
(3) log durability+integrity (pg backup + restore drill + hash chain + insert-only role + running daily
JSONL export→git = backup + rollback + anti-split-brain in one) · (4) event envelope (schema_version,
per-event idempotency key, causation/correlation IDs, server sequence, ignore-unknown-kinds-loudly) ·
(5) needs-you trustworthiness (freshness age, watchdog, synthetic-ticket alert, Commander gate/escalation
emissions via ctl day one) · (6) attention-instrumentation events in the slice-1 schema · (7) timeline
reframe (cutover = trailing milestone after 5 clean compare-days, outside the 2–3-wk wedge window).
**Tension C17 (event sourcing vs plain state table) resolved: lock held** with the discipline corollary —
folds one-SQL-query simple, no projection framework in slice 1. SPEC.md now carries a supersession banner
(+ 4 inline markers); SPEC v2 rewrite queued after the deep technical discussion; deep-tech agenda
enriched to 11 items (DESIGN §Open Questions).

## D6 — Deep technical discussion + eng review: ENG-PLAN rev 2 LOCKED (2026-07-13, operator, /plan-eng-review D1–D8)
All 11 open-questions agenda items decided or dispositioned. Stack: **Python 3.12-pinned/FastAPI/
psycopg3/plain-SQL migrations** (repo-incumbent). Wake: **thin wakekeeper — wake_outbox table +
NOTIFY-as-hint**, no persistent Commander daemon. Evidence: **digest-referenced blobs**
(PUT /v1/blobs, erasable bytes, immutable metadata). Reads: **pure SQL views**. Concurrency:
**append transaction** (FOR UPDATE, per-ticket seq, idempotency-before-CAS, per-ticket hash chain
anchored by the daily git export). Auth: **default-deny principal×event×state matrix** — crews
CAN resolve proven work (server-validated), can NEVER forge gate_result/resolved/criteria_frozen.
Migration revised: **reads cut over to the API at dual-write start** (kills split-brain). Work:
**L0 contract lane first** (schemas+hash spec+OpenAPI), then L1–L5 file-manifested. Review: Fable
4-section (7 findings) + Codex-xhigh outside voice (32) → 39 reconciled, ZERO cross-model tension,
all ratified (D8) into ENG-PLAN-ctower-wedge.md rev 2 — **eng review CLEAR, ready to build**.

## D7 — There is no legacy: clean-start go-live, migration machinery deleted (locked 2026-07-14, operator)
Operator verbatim: *"look, there is no legacy, the current setup was built 5 days ago."* The dual-write
window, tailer (cursor protocol, origin='tailer'), 5-day fold-compare gate, reads-cutover sequencing,
and trailing-cutover milestone are DELETED from the wedge (they treated a week-old JSONL draft as a
production system to be carefully taken over). Go-live = ONE day: freeze old JSONL read-only
(git-archived; emergency fallback; closed history stays there, un-imported) → one-time import of OPEN
items only (legacy_ref, origin='backfill', eyeball-verified vs the frozen board) → same-day API-first
rewire of tools/req + crew-log (spool-backed). Zero-drop guarantee now rests on: ctl spool + one-time
verified import + daily synthetic ticket. Codex ENG-PLAN findings 8/9(partial)/13(migration)/21
resolve by removal. The daily JSONL export→git SURVIVES on its two remaining roles (external
tamper-anchor + independent backup) — the legacy-rollback rationale is retired. Wedge honest total
back to ≈2 weeks. ENG-PLAN rev 3.

## Working assumptions — routing & ownership (2026-07-14, from operator gap-spot; contest freely)
- **A10 Notification routing:** the wakekeeper is a RECIPIENT ROUTER over wake_outbox rows —
  needs-you arm→operator/CT; assignee-crew (actor≠assignee)→mux nudge with a `ctl show --since`
  pointer; dead-owner or unassigned/escalated→Commander. Push accelerates, pull (`ctl show` at
  brief checkpoints) guarantees. IN the wedge (~+1d) — required for D2's steer-via-comments journey.
- **A11 Ownership:** one assignee at a time (operator|commander|crew:<name>; dept queues P5), folded
  from `assigned{from,to}` (full custody history). Assign rights: commander/operator→anyone;
  crew→handback-to-commander only; gateways/import→never. Ownership = durable NAME, not a session
  (dead session ≠ orphaned ticket; respawn-same-name continues from timeline+worktree). Gates do
  not transfer ownership — they queue the operator's action while the assignee keeps delivery.
- **A12 Ingress (P4 shape confirmed):** each gateway = thin Hermes adapter with its OWN principal
  token (actor honest by construction), source-auth (DKIM/allowlist/HMAC), tainted external content,
  dedup by the S1 UNIQUE(source_kind, source_ref) — the wedge already builds the whole socket.

## Session log
- 2026-07-13: D1 locked; first deep-dive = Part 3 (user journey & UX), then Part 2 (ticket model).
- 2026-07-13 (pm): /office-hours run → D3 block; research lanes 1-5 landed 13:34-13:37 and absorbed
  (lane 1 corrects the cron premise: Hermes cron = fresh session + daemon + shared memory + soul
  reload, NOT same-context re-entry; lane 4: Commander loop has no daemon home = the real 24/7 gap;
  CT server today doesn't survive reboot — launchctl submit, no plist). Design doc
  DESIGN-ctower-office-hours.md written; adversarial review iter-1 = 6/10 FAIL, 15 issues; fixes
  applied (see doc rev 2); D4 attention-metric declared by operator.
- 2026-07-13 (late pm): review iter-2 = 8/10 (all 15 iter-1 fixes verified; 6 reconciliation issues)
  → fixed in rev 3 (canonical event vocab, escalated kind, origin-tagged migration + synthetic
  ticket, client-UUID idempotency, concurrent baseline, A6/A8 ledger refinements). Iter-3 = 9/10
  PASS; 4 minor concerns persisted in the doc (3 of them = deep-technical-discussion agenda).
  **Operator APPROVED the design (OH-D9). Lock complete — next: the deep technical discussion.**
- 2026-07-13 (eve): /plan-ceo-review on the FULL corpus (operator-directed) → REVIEW-ceo-2026-07-13.md;
  double-blind: Fable review + Codex-xhigh outside voice; operator approved fold-in ("fold them in") →
  DESIGN rev 4 + SPEC supersession banner + D5. Next: the deep technical discussion (11-item agenda).
- Deltas the operator's raw notes add to SPEC: dual-surface law (every capability = API first; webUI+CLI
  are thin clients), acknowledgement-routing as a first-class event property in catalog/types.yaml,
  skill-usage tracking as timeline events (makes the improvement loop measurable), Meet/Zoom meeting-bot
  connectors parked to v2.

## D8 — One canonical SPEC and cohesive ctower target architecture (locked 2026-07-17, operator)

The operator approved the documentation and architecture consolidation for R359/R361. The documentation
model is now:

- `SPEC.md` is the one canonical current system truth. Product contract, UX, domain model, architecture,
  workflow and verification, security/operations, acceptance criteria, KPIs, and build increments live
  together there rather than in competing architecture or engineering-plan documents.
- `DECISIONS.md` remains separate and append-only as the authoritative rationale/history. This entry does
  not rewrite D1–D7 or erase the historical reasoning that led here.
- `ARCHITECTURE.md`, `ENG-PLAN-ctower-wedge.md`, design/review/kickoff/vision files, and the five research
  files are historical references. They are retained for provenance and must not be implemented directly
  where they differ from the canonical SPEC.
- Because ctower has no ticket API yet, SPEC contains a temporary stable-ID bootstrap backlog for the
  contract, Increment 1, and Increment 2. It is imported once when ctower can own ticket state; afterward
  live state exists only in ctower and SPEC retains increment definitions, not a parallel board.

The operator's exact acceptance phrase for the previously presented cohesive direction was *"the rest
ok"*. That acceptance locks the following connected direction:

1. **ctower-native source of truth.** Ticket, workflow, gate, evidence, attention, delivery, effect, run,
   and audit semantics belong to ctower. Mission Control JSONL, Paperclip, task/status files, terminal
   history, and vendor sessions are import/adapter/provenance inputs only after cutover.
2. **Locked D2 human IA.** The five primary surfaces remain Home (Commander omnibox + Needs You), Board,
   Ticket detail, Fleet, and Analytics. All other entities are contextual views.
3. **One ticket with orthogonal state.** A permanent ticket spans lifecycle episodes, but ticket lifecycle,
   workflow stage/attempt, execution job/run, gate, delivery, attention, and custody are separate linked
   state models. `reopened` starts a new episode rather than becoming a stable status.
4. **Three-tier topology.** An authenticated private-VPS control/orchestration tier and durable record tier
   own policy and truth; a replaceable outbound-connected worker plane runs local `bin/mux` first and later
   VPS/sandbox runners through one durable lease/fencing/cursor protocol.
5. **Effects are brokered.** Passing a ticket gate does not itself authorize deploy/send/IAM/destructive
   action. Short-lived scoped grants and immutable receipts must exist at the real effect boundary, with
   external audit reconciliation and no standing production authority on general runners.
6. **Paperclip is selective input, not SSOT.** Proven mechanics may be ported or wrapped behind ctower-owned
   interfaces and conformance tests; Paperclip may not remain a writable ticket source or competing UI/audit
   truth after the cutover barrier.
7. **Trust spine, then one golden path.** Increment 1 preserves the locked authenticated Postgres event-log,
   evidence/gate, spool, Needs You, health, backup/restore, and one-day no-dual-write cutover wedge.
   Increment 2 adds exactly one end-to-end software-factory ticket on the `bin/mux` runner, including durable
   jobs, independent gates, staging/production effect receipts, live verification, failure recovery, retro,
   resolution, and closure. Remote/sandbox/general catalogs wait.

Implementation-state clarification: as of this decision, the verified implementation is still the legacy
local Control Tower/mux substrate. The canonical SPEC describes the target service and its first two build
increments; it does not claim that ctower behavior already exists.

## D9 — Strongest-capability Commander and risk-scaled review/repair budgets (locked 2026-07-17, operator)

Operator verbatim: *"I think the oposite the commander should be the smartest model, to lead the tasks until done, decided how mny review rounds needed etc."*

This decision supersedes exactly two earlier active assumptions:

1. The model-specific `Claude/Fable (commander)` phrase in D1 and active-constitution claims that make a
   cheap/Fable profile the default or exclusive Commander. D1's ctower-owned orchestration layer,
   harness-as-adapter boundary, incremental build strategy, and persona portability remain locked.
2. The global fixed-two-cycle review/repair rule. All evidence, independent-review, human-gate, effect-
   brokerage, authorization, no-proof/no-done, and anti-spin locks remain in force.

The replacement policy is:

1. **Strongest available reasoning seat.** Commander quality is optimized before token cost. At each
   reasoning wake, a capability policy resolves the strongest available healthy general-reasoning profile
   authorized for the seat. Current examples include Opus-class and Codex xhigh-class reasoning; no vendor
   or model is permanently declared smartest. Fable may assist only as a non-authoritative scout,
   summarizer, or polling helper, never as accountable Commander or final gate authority.
2. **Accountable until terminal.** One durable Commander principal retains orchestration accountability for
   each ticket through planning, delegation, evidence/review responses, release verification, retro, and
   resolve/close (or explicit terminal cancellation). A new model, harness, process, or context window
   continues that same ownership from ctower state; no immortal session is required.
3. **Lead, do not implement.** The Commander owns the versioned orchestration plan, desired/observed
   reconciliation, routing decisions, review topology, budget rationale, and terminal verification. Heavy
   implementation, test authoring, UI work, release operations, and independent verdicts remain delegated
   to the responsible personas and cannot be self-reviewed by the Commander.
4. **Versioned risk/evidence budget.** Each ticket records an `orchestration_plan` revision containing risk
   facts, mandatory gate participants, independence constraints, planned review rounds, separate repair-
   attempt limits per failure fingerprint, and rationale. Initial policy floors/defaults are low=1,
   standard=2, elevated=3, and critical=3. The Commander may add reviewers, review rounds, or repair
   capacity when new evidence justifies it and must append a new plan revision.
5. **Distinct accounting.** A review round is one complete execution of the required independent gate
   topology on a current artifact/evidence digest. A repair attempt is one mutating response to a typed
   failure fingerprint; it consumes that fingerprint's counter and invalidates declared dependent proof.
   Reassignment, prose, a changed model, or a restarted context cannot reset either counter. A pass exists
   only when all mandatory gates for the current digest pass and no blocking finding remains.
6. **Floors, ceiling, and anti-spin.** The engine rejects any plan below its risk-derived floor, missing a
   mandatory reviewer/gate, or above the hard automatic ceiling of 5. The Commander may raise a budget up
   to 5 with recorded new evidence but cannot erase consumed work. Repeated no-progress or fingerprint
   exhaustion creates exactly one deduplicated escalation and stops automatic cycling even if another
   counter has nominal capacity.
7. **Operator authority.** Exceeding ceiling 5, lowering or waiving a waivable policy floor, or changing a
   non-waivable safety invariant requires the appropriate authenticated operator decision; non-waivable
   invariants remain refused. A waiver is audited and never rewritten as a passing gate or fabricated proof.

## D10 — Compositional execution and the tmux boundary (canonical architecture rationale, 2026-07-17)

This entry refines the implementation shape of D8's replaceable worker plane; it does not change the
operator-locked ticket, evidence, gate, effect, or delivery semantics. Every accepted attempt records one
immutable effective-run manifest composed from independently versioned `HarnessSpec`, `SupervisorSpec`,
`TargetSpec`, `WorkspaceSpec`, and `TelemetrySpec`, plus the selected environment, image, placement, policy,
profile, skill, and capability revisions. The composition digest is evidence input. An unknown,
incompatible, revoked, or ungranted component is a refusal, never a fallback to a generic process.

The Runner Interface owns authenticated offer/accept/lease/start/event/terminal exchange, fencing, ordered
cursors, durable command ACKs, continuous log chunks, replay, explicit gaps, checkpoint/recovery, and the
capability distinction between `LIVE_INPUT` and `INTERRUPT_AND_RESUME`. A Supervisor Interface owns the
small process-control vocabulary: probe, observe, interrupt, terminate, snapshot, and adopt. Supervisor
handles are scoped observations under the ctower lease epoch; they are not job identity, completion proof,
or audit authority.

`bin/mux`/tmux is the production Supervisor Adapter and an optional same-host continuity/visibility aid for
the Increment-2 golden ticket. It cannot mutate ticket state or satisfy gates from terminal/session state,
and `send-keys` delivery is not an acknowledged command. A bounded direct-process Supervisor is the second
justified real local Adapter; the deterministic fake injects loss, stale-epoch, replay, and gap faults. That
pair plus one conformance fake earns the public Seam without building a generic plugin framework; additional
Supervisor families still require a second justified use and unchanged conformance. The Paperclip adapter
audit at pinned source commit
`5d42382df4c5724085967027485fcd39b91b01ae` is provenance for the adopted lease/heartbeat/conformance ideas,
not a runtime dependency or competing authority.

## D11 — Trusted Extension Host and five-surface IA boundary (canonical architecture rationale, 2026-07-17)

The kernel alone owns record, ticket, Workflow, policy, gate, evidence, Attention, job, effect, and secret
truth. Extension-readiness is provided by one deep Extension Host Module with a small Interface for staging,
approval, enablement, scoped invocation, inspection, upgrade, disablement, and uninstall. Manifests are
revision-pinned data and are parsed without executing package code. A requested capability is not a grant;
any future executable extension receives only invocation-scoped identity, resource/tenant scope, egress,
quota, expiry, and revocation. It has no database credential/direct connection, kernel-table access, host
socket, standing secret, canonical mutation path, primary-route authority, or provider/effect authority
outside the broker.

D2's five primary surfaces remain exhaustive: Home/Needs You, Board, contextual Ticket detail, Fleet, and
Analytics. Members, access, secrets, environments, images, adapters, and extensions are secondary Admin
surfaces. An extension may contribute schema-validated host-rendered content only to named contextual slots;
it cannot create a sixth primary surface, replace Needs You, write a canonical projection, or ship same-origin
third-party UI. General plugin workers, executable third-party UI, migrations, a marketplace, and a broad
connector SDK remain deferred until isolation, capability, recovery, and two-real-Adapter conformance earn
scope. The Paperclip plugin/modularity audit at pinned commit
`5d42382df4c5724085967027485fcd39b91b01ae` supplies selective provenance, not an installed plugin platform.

## D12 — Greenfield modular monorepo and universal configuration model (canonical architecture rationale, 2026-07-17)

Implementation starts in a new `ctower` monorepo. Mission Control, Paperclip, task/status files, and the
research corpus are migration or design provenance only; none is reused as the trusted kernel. The control
plane is a Python modular monolith: `ctower-api` and its control worker deploy from one kernel artifact,
while `ctower-runner`, `ctower-web`, and `ctowerctl` are separately deployable clients of authored contracts.
Module dependencies point contracts -> kernel Modules -> backend/workers -> clients/Adapters; the web and
runner cannot import kernel persistence, and no second stack or microservice-per-noun is introduced.

One deep Catalog Module owns a universal `VersionedComponent` envelope and lifecycle for configuration
categories. Category-specific schema and conformance remain typed, but there is no parallel workflow,
policy, profile, skill, environment, image, placement, extension, cadence, or integration revision
authority. A secret-free `CompanyBundle` is portable desired-state authoring over the same authenticated
command API used by UI edits: validate, semantic plan/diff, security/compatibility/conformance, stage
immutable revisions, then atomically move a future-only active pointer. YAML/Git is not watched for runtime
truth and contains neither secret values nor sessions, handles, counters, verdicts, or live ticket state.

`engineering.software-factory` is one named Workflow component, not a Factory aggregate, service, table,
Interface, worker, or second state machine. Workflow owns declared stages, legal edges/failure routes, gate
locations, and terminal conditions. Compatible Execution/Gate/Evidence policies own participant selection,
optional-gate activation, D9 limits, timeouts, budgets, placement, escalation, and waiver constraints; they
cannot invent an absent stage or edge or rewrite consumed work/proof. The migrated software-factory SKILL
is provenance/human guidance, never execution authority. Authored schemas, migrations, generated clients,
fixtures, conformance suites, deployment manifests, docs, and import compatibility each have exactly one
durable home in the monorepo. General-purpose Catalog editors and a marketplace remain outside the two
increments; the typed catalog kernel and CompanyBundle contract do not imply those products exist. D8's
phrase “general catalogs wait” therefore continues to exclude generalized service/sandbox catalogs and
catalog product surfaces, while the minimal typed configuration Catalog prevents parallel revision
authorities inside the locked first-two-increment architecture.

## D13 — Remote execution, placement, and reusable-image trust boundary (canonical architecture rationale, 2026-07-17)

Every agent or harness may eventually run in a distinct local, VPS, provider, or sandbox environment, but
ctower remains the record, lease, evidence, gate, and effect authority. Each attempt pins an immutable
`EnvironmentRevision` and `ImageRevision`; a recorded `PlacementDecision` explains all candidates,
hard-constraint exclusions, no-colocation checks, trust/capability/resource inputs, soft scoring, and the
selected Target/Supervisor/Workspace/Telemetry composition. A soft preference cannot waive a hard
constraint, and an active pointer change affects future attempts only.

A provider-neutral Remote Execution Provider Interface covers validate, provision, inspect, execute,
observe, cancel, destroy, reconcile, workspace, and image operations. Provider allocation/session/lease
identifiers are scoped metadata beneath ctower's outer job lease and fencing token; provider assertions
cannot advance a Workflow or gate without ctower evidence. Crabbox at pinned source commit
`cf5081fcc116f8d28983b265652b8abf9ed24f5e` is an optional future Adapter/provenance source, never a mandatory
dependency or alternate control plane. Contract-L0 negative fixtures and deterministic fake providers are
in scope; the Increment-2 production runner remains local `bin/mux`, while broad remote pools wait.

The reusable-image lifecycle is setup -> capture -> scrub -> secret scan -> SBOM/vulnerability scan ->
conformance -> attest -> candidate/active, with explicit failed, superseded, revoked, rollback, reference-
aware GC, and deletion outcomes. Runs pin immutable image digests; mutable `latest` is forbidden. Captures
may retain tools, runtimes, and safe caches, never credentials, login sessions, standing secrets, sole work,
or authoritative evidence. Secrets arrive just in time after boot and are revoked/scrubbed at finalization;
browser terminals are short-lived, scoped, audited, TTL-bound, and network-policy constrained. Provider
loss, missing/revoked images, digest mismatch, target/runner loss, stale provider leases, workspace-
finalization ambiguity, log gaps, and incomplete capture all fail closed and reconcile before reuse or
progress. General custom-image administration/runtime waits beyond the first two increments.

Scope note: D10-D13 record architecture rationale required to implement the already canonical D8/D9
direction. They intentionally do **not** lock the proposed P0/P1/P2 priority, six-lane Board projection,
typed-blocker, or scheduling shape; that task-management contract remains a recommendation in `SPEC.md`
pending explicit operator confirmation.

## D14 — Day-one repository quality baseline; exact Python pin pending (2026-07-17)

The operator explicitly required clean-code standards and machine gates in the repository from its first
commit: authored files should remain approximately below 500–600 lines; god objects must be prevented;
observability exists from day one; external/process contracts are fully typed with Pydantic; Ruff owns
Python lint/format; strict mypy, pre-commit hooks, and coding standards are mandatory. This requirement is
locked. It deepens D12's greenfield modular monolith and does not create another product increment.

The executable shape is one deep Repository Policy Module, not unrelated scripts. Its small Interface
parses the repository once and emits one typed report for ownership/dependency direction, private imports,
logical source/function/complexity/nesting/public-surface/fan-out budgets, generated drift, observability
discipline, and exact expiring exceptions. Pre-commit, `just check`, `just verify`, and required CI call the
same policy implementation. Ruff, mypy/Pydantic, TypeScript/ESLint/Prettier, code generators, Gitleaks, and
test/coverage tools remain specialist executables rather than reimplemented rules. Tests use public Module
Interfaces and shared Adapter conformance; a coverage percentage cannot substitute for behavioral proof.

D12's two-language architecture remains the recommended allocation: Python for the trusted control plane,
runner, CLI, and separately isolated release helper; TypeScript for the browser. Go or Rust may later
implement a narrow measured provider/runner/privilege Seam, but neither is introduced in the first two
increments.

The exact Python-version supersession is intentionally **not locked by this entry**. Standard-GIL CPython
3.14.6 is the recommendation, with 3.13.14 as an explicit tested fallback. An L0 compatibility fixture must
prove the complete FastAPI/Pydantic-mypy/psycopg3/uv/Ruff/mypy/OpenTelemetry/codegen/release-helper lock and
Linux artifacts before the operator accepts an append-only supersession of D6's 3.12 phrase. Until then,
D6 remains historical authority for the exact runtime pin; `SPEC.md` labels 3.14.6 as recommended rather
than silently rewriting that audit fact.

## D15 — Contract clarifications: lineage vocabulary, first trust root, continuous custody, and scoped verification (2026-07-17)

This is an architecture clarification for implementation consistency, not a new operator-locked product
choice and not a rewrite of D1–D14.

1. **D9 “failure fingerprint” means stable failure lineage for budget accounting.** D9's anti-reset intent
   is implemented by one server-normalized, digest-independent `failure_lineage_key`. A
   `failure_occurrence_fingerprint` identifies one observation on exact inputs and remains immutable
   evidence, but candidate digest, prose, executor/model/session, or occurrence fingerprint cannot create a
   fresh repair budget. This narrows terminology without changing D9's floors, ceiling, or operator gates.
2. **The empty instance has one explicit trust-root ceremony.** A short-lived one-use capability accepted
   only over the root-owned local/private bootstrap channel atomically creates the first tenant, disabled
   historical bootstrap actor, initial operator/admin, durable Commander, vault-binding references,
   canonical command/events/outbox, and a disable receipt. It is permanently unusable when consumed or
   when any tenant exists. CompanyBundle and all later administration remain ordinary authenticated
   commands; bootstrap is not a second control plane.
3. **Accountable ticket custody is total, not merely unique.** Every nonterminal actionable episode has
   exactly one eligible durable Commander custodian with gapless atomic transfer. An explicit protected
   operator suspension may temporarily hold custody while autonomous progress is paused. Executors,
   reviewers, runners, models, sessions, and provider handles are separate assignments and never become
   custody by implication.
4. **`just verify` is scope-manifested.** The command is stable from CT-L0-007 onward, while one committed
   expected-suite manifest grows monotonically with the backlog. A suite declared current must exist and
   pass; a later suite is reported not-yet-required, never fabricated as a placeholder pass. Logical gate,
   scheduler, reconciler, evidence, and analytics responsibilities remain inside the deep Proof, Workflow,
   Runtime, Effects, Attention, and Projections Modules rather than becoming service-per-noun Modules.

## D16 — One derived architecture atlas; durable wake, heartbeat, Routine, and cron vocabulary (2026-07-17)

The operator explicitly requested that the terminal-safe ctower architecture diagram be saved as
`ARCHITECTURE.md` and that heartbeat and cron behavior be designed after reading the relevant Paperclip
documentation. This decision supersedes only D8's classification of the root `ARCHITECTURE.md` filename as
historical. D8's substantive rule remains: `SPEC.md` is the one canonical current system truth and
`DECISIONS.md` is the append-only rationale ledger. Exactly one root `ARCHITECTURE.md` may now exist as a
compact derived ASCII atlas. It adds no requirement or execution authority, must change with the SPEC, and
loses every conflict with the SPEC. Historical architecture documents remain historical.

The following vocabulary and durability boundaries are locked:

1. A **wake intent** is an idempotent committed command/outbox fact that may create or coalesce a bounded
   job. It is durable before dispatch and is distinct from receipt or execution.
2. A **reasoning heartbeat** is the operator-facing name for one bounded execution run. It is not agent
   identity, durable memory, a scheduler clock, or proof of completion.
3. A **lease heartbeat** is a runner-liveness/progress frame valid only under the current fencing token. It
   cannot advance Workflow, proof, or effects.
4. A **scheduler beat** is a deterministic due-trigger scan. Recurring work belongs to a revision-pinned
   Routine; no Routine or agent gets its own operating-system cron process.
5. Agent wakes are event-driven by default. A schedule occurrence, its concurrency/catch-up outcome,
   ordinary command/job, outbox record, and `next_fire_at` advance commit transactionally before dispatch.
   Exact Routine revision, timezone, daylight-saving rule, concurrency, catch-up, backlog cap, and component
   pins remain attributable; every queued, skipped, coalesced, or refused occurrence remains visible.
6. Tmux panes, processes, sandboxes, remote-provider sessions, and model sessions remain replaceable
   continuity hints, never durability. Cancellation fences authority immediately; fresh runs reconstruct
   from committed state and content-addressed context/checkpoints.
7. Scheduler completeness, runner liveness, ticket progress, and control/effect reconciliation are separate
   deterministic detectors with independent watermarks. A watchdog agent reviews one fingerprinted stopped
   condition and cannot create repeated work for an unchanged fingerprint or expand its authority.

Paperclip is prior art, not a dependency or second control plane. Ctower adopts its useful event-driven
wakes, timer-off default, versioned Routine triggers, explicit concurrency/catch-up, visible run outcomes,
continuation wakes, and mechanical `HEARTBEAT.md` procedure. Ctower hardens those ideas by separating the
four overloaded runtime terms above, committing occurrence/outbox truth before dispatch, treating session
resume as optional acceleration, fencing cancellation immediately, retaining structured/redacted durable
records rather than trusting full transcripts, and forbidding routine direct-database control paths.

## D17 — Configurable rigor, task-first dogfood, acknowledged durability, and earned Seams (locked 2026-07-18, operator)

The operator approved the task-management shape and the revised direction to proceed. This entry preserves
D1–D16 as history while superseding only their conflicting implementation details. In particular, it
supersedes D9/D15's universal risk-tier floors, fixed review counts, and platform-wide ceiling; D13's
predeclared general remote-provider Interface and fake-provider L0 scope; and D13's statement that the
task-management model remained pending. The durable principles behind those entries remain: accountable
Commander custody, independent verification, protected waivers, append-only server facts, stable failure
lineages, bounded automation, immutable pins, exact-identity cleanup, and fail-closed recovery.

1. **Workflow and Execution Policy remain domain-neutral.** A Workflow declares stages, activity metadata,
   legal edges, failure routes, and terminal conditions. A pinned Execution Policy and orchestration-plan
   revision declare participants, mandatory stage gates, `required_perspectives`,
   `max_nonpassing_rounds`, `max_repairs_per_lineage`, `max_candidate_generations`, and optionally
   `max_total_executions` only when the domain independently needs a cost/resource stop. `total_executions`
   and all consumed counts are immutable server facts used for audit, cost, and exhaustion checks; clients
   and plan prose cannot author or reset them. Every applicable policy must be finite, but ctower has no
   universal low/standard/elevated/critical numbers or automatic ceiling. Concrete values belong to the
   pinned domain package; the default `engineering.software-factory` examples deliberately omit a total
   cap and remain finite through nonpassing-round, repair, candidate-generation, no-progress, deadline,
   quota, and hard-safety bounds. If another domain selects a total cap, policy publication requires at
   least one maximum co-active perspective round plus adjudication reserve, and a resolved ticket requires
   at least its active perspective round plus reserve. The cap may independently stop work while other
   bounds retain capacity; it does not promise that every independent bound can be consumed simultaneously.
   One all-perspective pass on the current digest advances; only a terminal nonpassing round consumes
   `max_nonpassing_rounds`. Candidate generation, review outcome, lineage repair, and observed execution
   total are separate dimensions. A later candidate may invalidate a prior pass and require fresh review,
   but no repeated passing round is required.
2. **Task management is approved as orthogonal facts, not one overloaded status.** Priority is P0/P1/P2.
   Lifecycle, blockers, workflow stage, assignments, Board lane, and delivery facts are independent.
   Canonical Board lanes are `backlog`, `ready`, `in_progress`, `in_review`, `blocked`, and `complete`, with
   familiar UI labels allowed. The Board fold derives verification versus work from each stage's
   `activity_class`; the engine never branches on software-factory stage names. Delivery uses typed facts
   such as `change_merged`, `staging_verified`, and `production_verified`; capitalization of “done” has no
   semantic authority. Reassignment changes custody/executor/reviewer intervals without erasing history,
   age, proof, or counters.
3. **The build order is task-first and self-dogfooding.** L0 freezes only the smallest contracts and
   repository gates. I1 builds Record/Work/Proof, policy-required off-host acceptance, backup/restore and
   key/journal recovery, the protected CLI spool, thin Home/Board/Ticket, and a four-stage
   `capture -> frame -> verify -> close` fixture interpreted by the final generic Workflow Module
   interface. Only after those pass does the ctower project freeze/import/rewire and make ctower its sole
   writable task source. I2 deepens that same Workflow Module with generic stage jobs, Commander planning,
   Runtime, independent verification, Effects, release, and one software-factory production golden path.
   There is no temporary hard-coded workflow engine.
4. **Acceptance means disaster-recoverable acknowledgement.** At cutover, an authoritative accepted record
   has RPO 0 because the response is not accepted until the policy-required off-host durable ACK commits.
   If that ACK is unavailable, the response is explicit non-accepted `durability_pending` and safely
   replayable under the same command key. Restore recovers vault/KMS material, verifies events/objects/
   tombstones, and reconciles root-supervisor, effect, and provider journals before ordinary reads or effects
   enable. Artifact bytes may retain a separately declared RPO no worse than five minutes; they cannot be
   misrepresented as accepted authoritative records.
5. **Release trust is independently rooted.** The application submits desired artifact identity only. A
   root-owned release supervisor verifies artifact bytes, signature/attestation, subjects, and trusted
   builder/workflow identity against root-owned policy before installation. Missing, wrong, revoked, or
   untrusted provenance performs no install. Supervisor/effect journals and receipts survive ctower restart
   and participate in restore reconciliation.
6. **Public Seams are earned.** I1/I2 implement the local process/tmux Supervisor Seam justified by two real
   Adapters. The golden path also implements one live `systemd-vps` integration and a fault-injection test
   implementation behind an internal Effects boundary; that pair does not become a generalized public
   provider Seam. General remote execution, Crabbox, custom images, warm pools, executable extensions, and
   a generalized effect-provider Seam keep only durable invariant/deferred-capability contracts at L0.
   Each gains a public Seam only when a real use case and at least two justified real Adapters exist; a fake
   alone never earns indirection or product scope. Current evidence must say `not exercised`, not imply a
   runtime from contract fixtures.
7. **Operational correctness starts on day one.** Browser writes remain visibly unsent or
   durability-pending until accepted. The encrypted owner-only CLI spool and poison outbox paths fail closed
   under crash, disk, corruption, and permanent-delivery failures. The exact design-load fixture is a
   versioned repository artifact. Before project cutover, at least five and preferably ten working days of
   instrumented legacy operator-attention data are frozen; provisional absolute targets apply until 30
   comparable post-cutover tickets permit the relative target. A clean install's first verified success has
   its own timed acceptance criterion.
8. **The canonical spec stays readable and executable mechanics stay owned.** `SPEC.md` owns requirements,
   architecture, user flows, acceptance criteria, KPIs, and increment intent. Schemas, OpenAPI, migrations,
   package YAML, fixtures, and validation commands own mechanical detail in their exact repository homes.
   Generated SPEC/AC/INV traceability indexes prove coverage and drift; they do not create another source of
   truth. `ARCHITECTURE.md` remains the one compact derived atlas allowed by D16 and loses every conflict with
   the SPEC.

## D18 — ReviewPlan v1 ownership, observed execution facts, and restore-source inventory (locked 2026-07-18, operator)

This entry preserves D1–D17 as history and supersedes **only** D17.1's optional aggregate-execution-cap
clause and its associated publication arithmetic. Every other D17 decision remains in force.

1. **ReviewPlan v1 has no aggregate execution limit.** It owns `required_perspectives`,
   `max_nonpassing_rounds`, `max_repairs_per_lineage`, and `max_candidate_generations`.
   `total_executions` remains an immutable server-owned audit/cost observation for every started
   perspective execution; neither policy input nor an orchestration plan can author, cap, or reset it. A
   future aggregate cost/resource stop requires a real use case, a separately versioned policy component,
   an executable semantic validator, and actual enforcement before publication. No field or arithmetic for
   that future component is decided now.
2. **A ReviewPlan is a named child revision.** It lives inside one pinned Gate Policy component and is
   addressed only as `<gate-policy-key>@<gate-policy-revision>#review-plans.<name>`. The parent revision and
   digest own the child bytes, and the enclosing `review_plans` map name is the child identity. A ReviewPlan
   has no independent key, revision, status, `VersionedComponent` identity, or standalone reference form.
3. **Restore success requires a signed expected-source inventory.** Each inventory revision names every
   authoritative root-supervisor, effect, and provider journal plus its activation state and trusted cursor
   or zero-source declaration. I1 records these unactivated sources explicitly as `not_exercised`/zero-source;
   absence is never success. A missing, unreadable, or gapped activated source fails closed. Before I2
   activates a root/effect source, the activation transaction commits a signed inventory revision marking
   it active before any associated grant or effect can execute.

## D19 — Versioned CommandGuard before arbitrary harness dispatch (locked 2026-07-20, operator R593)

The operator required an enforceable catastrophic-command guard before ctower activates arbitrary local or
remote harness execution. This decision deepens D10's compositional execution boundary and D17/D18's
fail-closed sequencing without changing their ticket, Workflow, Proof, Effects, or earned-Seam authority.
The observed design lead was a raw-text denylist that blocked a non-executing issue-description command
because it merely quoted a dangerous token. Text occurrence is not execution intent.

1. **Runtime decides; every dispatch-capable Harness or Supervisor Adapter enforces at the final boundary.**
   Runtime owns one versioned CommandGuard decision over the proposed execution. Each registered local or
   remote Harness or Supervisor Adapter that can launch, invoke, or submit a harness command must invoke and
   enforce it at the last trusted point before process, shell, or provider dispatch. A direct bypass is an
   architecture and conformance failure. A changed plan or target requires a new decision.
2. **Normalize actual intent and targets.** Evaluation resolves executable identity, argv or explicit shell
   plan, cwd, bounded environment references, parent traversal, globs, symlinks, wrappers/indirection, and
   candidate targets in the dispatch namespace. Unresolved, ambiguous, or broad protected targets fail
   closed. Safe cleanup is permitted only through an authorized capability with proven containment inside
   an exact disposable root; basename or command-name exceptions are insufficient.
3. **Typed decisions and immutable redacted receipts.** The result is exactly `allow`, `block`, or
   `needs_operator`. Every result binds ticket, job/run, principal, Harness/provider, policy revision,
   normalized-command digest, cwd, resolved targets, rule/reason, and time in an immutable receipt. Raw
   secrets, expanded credential values, and sensitive command content do not enter application logs or
   telemetry. `block` and `needs_operator` execute zero commands.
4. **Minimum catastrophic classes are explicit.** Policy covers root/home/workspace or broad filesystem
   destruction; disk/filesystem/volume format or wipe; destructive database operations; protected source
   history/reference rewrite; cluster, container-host, cloud, or infrastructure destruction; and equivalent
   supported wrappers or indirection.
5. **Override is exact and consumable, never standing authority.** A `needs_operator` decision can proceed
   only through a strongly authenticated grant bound to the original receipt, exact normalized command and
   targets, nonce, short expiry, and one atomic use. Expiry, replay, changed resolution, scope mismatch, or
   concurrent second use performs no dispatch and is audited. No grant disables the guard globally.
   Remote execution receives a signed scoped decision/grant and returns a matching enforcement receipt
   before ctower accepts completion.
6. **This is accidental-destruction defense, not sandbox containment.** An allowed interpreter, script, or
   binary may perform effects invisible to the structured dispatch plan. Sandbox/VM/OS isolation,
   short-lived credentials, workspace/tenant scoping, egress controls, least privilege, and Effects
   brokerage therefore remain independent required controls.
7. **Sequence and non-freeze boundary.** This contract is a hard prerequisite inside CT-I2-004/I2.2 and
   follows any resequenced checkpoint that first gains arbitrary command execution. I1 and PR #16 have no
   agent-command execution surface and remain outside this scope. This decision freezes human semantics and
   acceptance evidence, not the exact policy grammar, schema, storage, signature, or provider protocol;
   those mechanics wait for the first real Harness consumer to earn them. GitHub issue
   [#17](https://github.com/simjak/ctower/issues/17) tracks implementation.

Rejected alternatives:

- **Prompt- or skill-only instructions:** valuable guidance, but model compliance is not an enforcement
  boundary and cannot prove zero dispatch on refusal.
- **Raw regex-only denylist:** misses expansion, symlink, wrapper, and target semantics while producing the
  observed false positive on quoted non-executing text.
- **Universal standing override or global disable:** replayable ambient authority defeats exact scope,
  expiry, accountability, and safe concurrent operation.
- **Treating CommandGuard as a sandbox:** overclaims containment once allowed arbitrary code can issue its
  own syscalls or access already granted credentials.

## D20 — Bind CommandGuard decisions to dispatch and close the rollback bypass (locked 2026-07-20, operator)

This entry preserves D19 as append-only history and supersedes/narrows only its incomplete digest,
receipt-binding, final-dispatch, and rollback semantics. D19's Runtime ownership, catastrophic classes,
typed decisions, exact one-use grants, accidental-destruction boundary, I1 exclusion, CT-I2-004 timing,
earned-Seam rule, and deferred exact mechanics remain in force.

1. **One canonical normalized-execution-plan digest.** The digest covers executable identity, argv or the
   explicit shell plan, normalized cwd, each non-secret environment-resolution identity as its reference
   plus pinned version/digest and never the secret value, and the exact resolved target set in the actual
   dispatch namespace. It replaces any interpretation of D19's `normalized-command digest` as a partial
   command-text or target-independent digest.
2. **One decision/dispatch-attempt binding.** Every decision receipt, operator grant, and local or remote
   enforcement receipt binds that digest plus the same decision/dispatch-attempt identity, ticket/job/run,
   principal, exact Harness/Supervisor/provider/target identities, policy revision, and evaluation or
   enforcement time. Local enforcement is evidence-bearing under the same contract as remote enforcement;
   provider non-applicability is explicit rather than an omitted ambiguous field.
3. **No evaluation/dispatch gap.** At its final boundary the Adapter dispatches only from the captured or
   pinned resolution that was evaluated, or re-resolves and atomically compares the canonical digest
   immediately before dispatch. Mismatch, uncertainty, inability to compare, or inability to durably record
   the required receipt before dispatch performs zero dispatch and requires a new decision. Receipt loss or
   uncertainty discovered after dispatch may have begun leaves completion incomplete/unknown and never
   accepted; process or provider success cannot substitute for the receipt.
4. **Rollback remains inside CommandGuard.** Manual operator initiation is legal only through a healthy,
   registered, conformance-tested Adapter that obtains and enforces a fresh CommandGuard decision at final
   dispatch. If none is healthy, new dispatch remains disabled. Direct `bin/mux`, shell, process, or
   provider invocation is forbidden as rollback.

This narrowing is required because D19's earlier receipt field lists did not unambiguously bind environment
resolution, Supervisor and target identity, local enforcement, one dispatch attempt, and both evaluation
and enforcement time to the same complete plan, nor require a captured resolution or atomic final compare.
The I2 rollback text also permitted manual `bin/mux`, contradicting D19's no-bypass rule at the exact moment
a guard-path failure would make bypass most dangerous. This decision freezes only human security semantics
and acceptance obligations; exact policy grammar, schema, storage, signature, and local/remote transport
still wait for CT-I2-004 and any independently earned remote Seam.

## D21 — Generic derived Project Delivery projection (locked 2026-07-21, operator)

Tickets answer whether individual work moved; they do not by themselves answer whether a project is being
delivered. The operator approved one generic **Project Delivery projection** over the hierarchy
Company -> Project -> Increment/Milestone checkpoint. The software-factory table is one configured use,
not a platform-wide delivery vocabulary. Accounting, compliance, hiring, research, and other Workflows may
configure different checkpoint labels, exit criteria, and applicable lifecycle facts on the same projection.

The Project Delivery projection is rebuildable and read-only. It derives every row from versioned
checkpoint definitions and accepted durable ticket, Workflow, gate, evidence/artifact, blocker, decision,
cost, and applicable release/outcome facts. Manual status edits were rejected because they would create a
second source of truth and permit displayed confidence to diverge from proof. Ticket-count completion
percentages were rejected because tickets differ in value, scope, criteria, and lifecycle, and splitting or
closing tickets could game the number. The truthful progress expression is checkpoint completion plus
explicit `proven exit criteria / declared exit criteria`, missing gates, and visible confidence/freshness.

The deterministic headline precedence, highest first, is `done`, `blocked`, `released`, `verified`,
`merged`, `ready_to_land`, `in_progress`, then `planned`. `done` requires current valid proof for every
declared exit criterion. Otherwise an
effective blocker prevents the next required criterion and overrides the headline while the underlying
lifecycle maturity remains available for drill-down. Checkpoints skip merge, staging, or release states
that their domain does not declare; skipping never weakens exit criteria. Proof invalidation, rollback, or
incident may regress the derived row without rewriting historical facts.

Relevant authoritative events reconcile affected rows immediately through the outbox. One hour without a
relevant change publishes a freshness heartbeat that recomputes the same fold but cannot fabricate a state
change. Overdue reconciliation is stale; missing/gapped/integrity-unknown or authorization-incomplete source
truth is `STATE UNKNOWN`, not calm progress.

Scope is deliberately split across the existing two increments. I1.7 adds only the smallest ctower
Company/Project/checkpoint hierarchy and compact trustworthy Project Delivery projection needed for
source-of-truth dogfood and rebuild/restore proof. I2.4 adds authorized interactive row drill-down, broader
visualizations, trends, cost/time analytics, and a reusable cross-domain product surface. This separation
lets ctower observe its own delivery as soon as it becomes authoritative without pulling a rich analytics
product into the cutover or implying a third product increment.

## D22 — I1.5 browser boundary and thin five-surface closure (locked 2026-07-23, operator)

The operator approved the six-row I1.5 Gate-0 bundle. This entry preserves D1–D21 and supersedes only:
the still-unselected frontend stack; automatic text/context classification as an I1 requirement; the
CT-I1-005 Playwright path; nullable/source-less I1 risk; and the implication that Fleet/Analytics global
routes may be dead until I2.

1. **Browser stack.** ctower-web is a React 19 client-only SPA using React Router 7 Declarative Mode and a
   Vite static build under the repository's Node 24/pnpm toolchain. The private TLS edge serves the immutable
   static bundle and proxies the API/session paths on one origin. Production has no Node server, SSR,
   frontend authority/cache layer, handwritten API client, component framework, or service worker.
2. **Browser authentication.** The SPA receives no API bearer. A same-origin server-rendered no-script login
   exchanges the existing opaque operator credential for a record-backed 256-bit server session represented
   only by a `__Host-ctower_session` Secure/HttpOnly/SameSite=Strict cookie. Unsafe requests require a
   session-bound synchronizer token plus exact Origin/Fetch-Site checks. Idle expiry is 30 minutes, absolute
   expiry 12 hours, and Access-policy-protected commands require reauthentication within 10 minutes.
   Logout, session revoke, source-credential revoke/rotate, or principal disable invalidates authority.
3. **I1 omnibox.** Every submit first appends one durable thread event. I1 classification is the operator's
   explicit `discussion|create_ticket|link_ticket` choice, defaulting to discussion. Create/link and
   provenance are atomic and exactly replayable; one discussion event may later be promoted once. I1 has no
   autonomous Commander reply, probabilistic/keyword classifier, semantic matcher, browser thread ledger, or
   duplicate ticket ledger. The target may deepen classification only through a later reviewed contract.
4. **Browser tests.** `tests/e2e` is the sole Playwright source root; increment directories live below it and
   `pnpm run test:e2e` is the canonical non-mutating command. `tests/acceptance/increment-*` remains Python
   acceptance. CT-I1-005 owns activation of the browser suite; CT-I1-008 archives its evidence.
5. **I1 risk.** Current-episode risk is a Workflow-owned append-only assessment derived deterministically by
   the pinned I1 execution policy from typed immutable basis facts/evidence. Clients cannot submit the
   label/rule or patch risk. The I1 package emits `standard|elevated|critical` with explicit
   `UNASSESSED|STATE_UNKNOWN` states and policy/rule/input provenance. Priority is never an input.
6. **I1 five-surface shell.** Fleet and Analytics are real narrow read-only I1 bodies. Fleet renders I1
   control health contributors. Analytics renders only the frozen attention baseline/current sample,
   revision/cohort/digest/watermark, and provisional/unknown state. I2 deepens those routes; I1 does not
   expose runners/workspaces/budgets, broad KPIs/trends/cost, or writable state.

## D23 — CLI-first I1 and deferred browser realization (locked 2026-07-23, operator)

The operator authorized I1 as API plus protected CLI only. This decision preserves D22 and supersedes only
its browser implementation timing. Explicit durable intake intent/provenance and Workflow-owned risk remain
I1 API/CLI requirements. React/Vite, browser sessions and CSRF realization, routes/navigation, Playwright,
screenshots, browser QA, and the interactive Project Delivery drill-down are deferred to the explicit
`CT-I2-005` I2.4 browser sub-checkpoint. No placeholder UI, empty browser suite, or I1 browser claim is
allowed.

1. **I1 trust-spine proof.** I1.6 proves `capture -> frame -> verify -> close` through the public API and
   protected CLI. The server still evaluates every transition; capture records off-host acceptance, priority,
   custody, and source; frame freezes criteria/evidence/gate; verify records current-digest evidence and a
   protected verdict; close validates then resolves/closes. Synthetic, restore/reboot, failure, and
   forbidden-stage-name proof remain required.
2. **I1 cutover and Project Delivery.** I1.7 freezes, exports, imports, reconciles, rewires, and seals only
   API/CLI/Commander/runner-facing clients that exist in I1. Its read-only Project Delivery text projection,
   with optional deterministic JSON, shows checkpoint key/label, headline, outcome, owner, proven/declared
   coverage, watermark, freshness, unknown/degraded state, source IDs, and derivation reasons. It accepts no
   status mutation, manual override, ticket-count percentage, or second source of truth.
3. **Stable traceability.** `CT-I1-005` remains a stable deferred alias, not a deleted or renumbered item.
   `CT-I2-005` owns the first browser realization and the sole `tests/e2e` Playwright suite. API/CLI source
   contracts and their traceability remain authoritative in I1; browser-session traceability remains future
   authority rather than passing I1 evidence.

This sequencing does not weaken off-host acknowledgement, protected CLI spool behavior, six-lane/task-axis
semantics, typed intents, risk provenance, proof/gate requirements, restore, auditability, source-of-truth
cutover, no-dual-write, or `STATE UNKNOWN`/degraded behavior. It is reversible before I2.4 because no
browser artifact or route is introduced in I1; implementation begins later against D22's preserved choices.

## D24 — Development dogfood authority precedes disaster-safe promotion (locked 2026-07-25, operator)

The operator authorized a narrow development-only authority mode so ctower can dogfood reconstructible
ctower engineering work before CP3-D exists. This entry preserves D17, D21, and D23 and supersedes only
their implication that no single-writer cutover stage may exist before disaster-safe acknowledgement and
restore evidence. It does not mark I1.7 or I1 complete.

1. **Two authority milestones.** `development_single_writer` may eventually make ctower the sole active
   writer for an exact allowlist of public, low-value, reconstructible ctower engineering records.
   `disaster_safe` remains a later promotion that requires CP3-D off-host acknowledgement, external
   failure-domain recovery, key recovery, isolated destructive restore, and measured RPO/RTO evidence.
2. **The development cohort is permanently narrow.** Credentials and secret values, accounting, payments,
   production approvals or effects, incidents, client data, irreplaceable artifacts, and expensive
   sole-copy work are forbidden. Development health must say `CP3_D_NOT_PROVEN`,
   `EXTERNAL_FAILURE_DOMAIN_UNPROVEN`, and `RECONSTRUCTIBLE_ONLY`; uncertainty disables writes and renders
   `STATE_UNKNOWN`.
3. **One point of no return, no dual write.** Before a future development epoch commit, an incomplete
   import may be discarded and scoped legacy writers may be unfrozen after integrity proof. After commit,
   those writers never resume. Rollback is a compatible ctower build/restore or explicit read-only/spool
   mode, never a return to legacy mutation.
4. **Least privilege and derived delivery remain mandatory.** A future importer may create only typed
   ticket seeds, exact aliases, initial Commander custody, relations, and provenance/source links. It
   cannot write Proof, Workflow, delivery/effects, resolution, closure, or arbitrary status. Project
   Delivery remains read-only and fact-derived; in development mode I1.7 stays visibly blocked/degraded on
   the unproven CP3-D criterion.
5. **I1.7 is split for reviewability.** I1.7A adds this decision and truthful docs, strict cutover-health
   and Project Delivery contracts, generated client/CLI visibility, minimal append-only storage, a pure
   read-only projection fold, and online-only unspoolable migration command stubs. I1.7B implements the
   reviewed source selection, exporter/importer, alias/reconciliation path, and permanent legacy fence.
   I1.7C performs the development epoch and the issue-#1 API/CLI dogfood proof. An I1.7A stub must refuse;
   it cannot manufacture a successful phase receipt.

Rejected alternatives:

- Calling verifier-only acknowledged-durability evidence CP3-D: this would overstate the external
  failure-domain and restore boundary.
- Temporarily dual-writing or re-enabling legacy mutation after the epoch: this creates split-brain
  authority and an unsafe rollback.
- Landing the decision, importer, legacy fence, projection, and live dogfood event in one change: this
  makes the authority boundary too large to review independently.

## D25 — Persistent E2 shadow runtime before authority promotion (locked 2026-07-28, operator R2164)

The operator authorized the smallest supported persistent development runtime from current main, independent
of other PR ordering. This supersedes only the statement that acknowledged durability may run solely inside
verifier fixtures. D17, D21, D23, and D24 continue to govern production, disaster safety, and source-of-truth
promotion.

1. **Fixed shadow topology.** One persistent PostgreSQL 17 primary and one named physical ACK standby run on
   the same private VPS. The API and same-artifact control worker are user-supervised long-running services.
   PostgreSQL and HTTP bind only to loopback; no DNS, firewall, TLS, or external endpoint is activated.
2. **Honest acceptance mode.** `development_offhost_ack` may finalize shadow commands through Record's exact
   receipt/finalization protocol and the ordinary worker loop. Health always reports degraded reason
   `development_offhost_ack_cp3_d_not_proven`. The topology is not an independent failure domain and never
   proves CP3-D.
3. **No authority expansion.** The runtime authorizes no `development_single_writer` epoch, `i1_exit`,
   production/effects/incidents, secret/client/irreplaceable data, or legacy-writer rewire. Mission Control
   remains authoritative until the separately gated D24 milestone.
4. **Unprivileged, referenced, pinned operation.** Secret values live only in an allowlisted OS keyring.
   This unattended linger host uses one dedicated owner-only passwordless development collection so an exact
   unit can unlock it after reboot; that is an explicit shadow-only tradeoff, not a production secret-at-rest
   claim. User systemd units and strict config contain references and labels. A release manifest binds clean
   source, the exact approved standard-GIL CPython patch (3.14.6 primary, 3.13.14 sole fallback), wheel,
   generated contracts, migrations, packs, and predecessor; upgrade/rollback switches verified pointers
   without reversing accepted schema facts.
5. **Deferred evidence remains explicit.** TLS/external exposure, full telemetry, backup and key/restore
   drills, independent failure-domain ACK, real-host reboot evidence, production claims, and root release
   supervision remain later work.

Rejected alternatives:

- Calling the same-VPS ACK copy “off-host” or CP3-D evidence: it proves replay mechanics but not a separate
  host/failure domain.
- Passing credential values through unit files, environment files, arguments, or config: the existing Secret
  Service boundary is available and required.
- Running a verifier-only finalization command after each mutation: it strands ordinary CLI and synthetic
  work; finalization belongs in the supervised ordinary worker.

## D26 — Split persistent runtime from release lifecycle (locked 2026-07-28, Commander R2164)

The Commander split PR #60 after successive candidate generations exposed distinct defects in the same
bundled subsystem: a staged-then-renamed virtual environment left console-script shebangs pointing at the
deleted staging path, and rollback under an exhausted systemd start limit restored the predecessor pointer
without restoring API/worker availability. This supersedes only D25's inclusion of automated release
selection, upgrade, and rollback in the persistent-runtime candidate. D25's fixed shadow topology,
ordinary finalizer, health semantics, secret boundary, bootstrap, and honest authority limits remain.

Part A installs one verified runtime artifact directly at one fixed permanent path and executes an installed
entry point before the service units select it. It includes no staging rename, mutable release pointer,
release-triggered restart, automated upgrade, or rollback. Part B owns those release-lifecycle concerns in
a separate lineage and must not be inferred complete from Part A's running-service evidence.

## D27 — Fresh-start authority, minimal carry-forward, and the split I1 gate (locked 2026-07-29, operator)

The operator approved the authority shape and milestone meaning below. This entry preserves D21's derived
Project Delivery model and D24's narrow development cohort, no-dual-write rule, and disaster-safe
requirements. It supersedes D7's one-time open-item import, D17.3 and D23.2's required
freeze/import/rewire sequence, and D24.3–5's importer/fence phases. It also supersedes D24's statement that
development authority cannot mark I1.7 complete: that wording hid two different gates. A development
dogfood verdict may now complete the development Project Delivery pilot while full normative I1 remains
incomplete. The supersession removes bulk import from the active path and gives each completion claim one
unambiguous scope; it does not weaken CP3-D.

1. **Authority shape — fresh start plus minimal carry-forward.** Establish the ctower Company / Project /
   checkpoint hierarchy and the Project Delivery projection on the **fresh database**. Retain the archived
   legacy corpus as **signed read-only provenance**. Carry forward only an exact reviewed set of
   still-actionable items through ordinary generated API/CLI commands with stable legacy aliases. **Bulk
   legacy import stays dormant behind a separate future decision.**
2. **CT-I1-008 is the development dogfood go/no-go.** Its verdict may be `GO_WITH_LIMITS` while CP3-D is
   red. That verdict authorizes only the reviewed reconstructible ctower-project cohort and may mark the
   development Project Delivery pilot/I1.7 checkpoint complete; it does not claim disaster-safe durability,
   satisfy full normative I1 exit, or authorize Increment 2.
3. **Full normative I1 exit is a separate gate.** It remains `NO-GO` until CP3-D proves
   external-failure-domain acknowledgement, key recovery, isolated destructive restore, and measured
   RPO/RTO. CP3-D is red and required, never satisfied, waived, or optional because development dogfood
   passed.
4. **CT-I2-001 dependency meaning is fail-closed.** Where the backlog says CT-I2-001 depends on CT-I1-008,
   the dependency is satisfied only by the **full normative I1 exit** gate associated with the archived I1
   evidence—not by a development `GO` or `GO_WITH_LIMITS`. Therefore no I2 implementation is authorized
   while CP3-D is red.
5. **No implicit migration authority.** The legacy archive is provenance, not a writer, fallback, or bulk
   import queue. Each approved carry-forward item is created through the same strict authenticated command
   path as new work, records its stable legacy alias and source digest, and receives no imported proof,
   gate, delivery, resolution, closure, or arbitrary state. Any bulk importer, automatic corpus
   reconciliation, or legacy reactivation requires a later operator decision and new acceptance evidence.

**Reality at this decision:** the repository's I1.7A contracts, refusing migration stubs, and read-only
Project Delivery visibility do not themselves establish fresh-database authority, complete the reviewed
minimal carry-forward, issue a CT-I1-008 development verdict, or prove CP3-D. Those remain designed gates
until their exact evidence is accepted.

## D28 — Per-slot seat accountability on Project Delivery (locked 2026-07-30, operator)

The operator directed on 2026-07-30 that every qualifying stage of delivery carry a first-class
queryable seat, so the board is an accountability ledger rather than only a status display: who owns
each open slot now, and who signed each completed slot after the fact. This entry preserves D21's
derived Project Delivery model, D27's fresh-start authority and fail-closed CT-I2-001 dependency rule,
S1 contract-closure semantics (generic configured keys, no product-code roster), and INV-61/INV-62
evidence completeness and signing rules. It does not weaken CP3-D, dual-write prohibition, or minimal
carry-forward.

This decision is in the same family as open delivery-surface declaration work (#115) — declare
present/absent/unknown as explicit data rather than inferred shape — but it is a **separate** decision
and does not resolve or pre-empt that open question beyond that family note.

1. **Seat catalog is data.** Seats are members of a versioned configured **seat catalog**, the same
   class of configuration as the active checkpoint set S1/S2 establish. Membership, keys, labels, and
   order change through authenticated versioned configuration; product code, schemas, projections,
   packs, and tests never hard-code a fixed seat roster or branch on particular seat-key strings.
   Adding, removing, renaming, or reordering seats requires no product-code change and is proven by a
   mutation test of the same class as the S1/S2 checkpoint-set proof.
2. **Assigned seat.** Each qualifying-stage evidence slot MAY carry exactly one assigned seat key drawn
   from the active catalog revision. Assignment is forward-looking accountability for an open or pending
   slot. It does not move the Workflow graph, fill evidence, pass a gate, or rewrite headline-state
   derivation.
3. **Signing seat.** Completed slot Evidence records the signing seat supplied by the Evidence verifier
   assignment interval under INV-62. `Evidence.verifier_principal` remains the canonical signing
   principal; the assignment supplies seat context without a drifting free-text or duplicate principal
   field.
4. **Assigned ≠ signed is data.** When both seats are present and differ, both remain visible. The
   difference never silently overwrites either fact and never becomes an error that blocks the record,
   transition history, or projection rebuild.
5. **Unassigned is data.** A slot with no assigned seat reads as explicitly unassigned. Surfaces never
   guess a seat from stage key, group key, evidence kind, principal display name, ticket custodian, or
   silence, and never omit the unassigned state so a client must invent a default.
6. **Derivation.** Board, Ticket, and Project Delivery seat surfaces derive only from the configured
   catalog plus explicit assignment and Evidence facts at the source watermark — consistent with S2's
   configured-set-plus-facts rule for checkpoints (INV-59, INV-64).
7. **Sequencing and bounds.** This decision authorizes the SPEC model only (US-PD-04, AC-PD-07..09,
   INV-64, and the seat fields on AC-PD-01/03/05/06). Contract, fold, projection, and generated-client
   carriage are a separate implementation slice stacked after S2 (#118) on the same Project Delivery
   surface. No new environment variables or feature flags. D27 and CT-I2-001 remain fail-closed.

Non-normative example of catalog members a configuration might declare for today's crew (not platform
vocabulary): commander, eng-manager, engineer, designer, qa, tech-writer, release-manager, devops-sre,
cso, triage.

Rejected alternatives:

- Hard-coding today's crew names into product schema, fold branches, or normative SPEC vocabulary.
- Inferring a seat from stage key or ticket custodian when assignment is missing.
- Collapsing assigned and signing into one field that rewrites history on sign-off.
- Blocking the record when assigned and signing seats differ.
