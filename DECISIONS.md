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

## D28 — Per-slot seat accountability on Project Delivery, Board, and Ticket (locked 2026-07-30, operator)

The operator directed on 2026-07-30 that every qualifying stage of delivery carry a first-class
queryable seat, so the board is an accountability ledger rather than only a status display: who owns
each open slot now, and who signed each completed slot after the fact. This entry preserves D21's
derived Project Delivery model, D27's fresh-start authority and fail-closed CT-I2-001 dependency rule,
S1 contract-closure semantics (generic configured keys, no product-code roster), and INV-61/INV-62
evidence completeness and signing rules. It does not weaken CP3-D, dual-write prohibition, or minimal
carry-forward.

**S1** is the contract-closure increment (#117): it closes the open delivery-surface declaration
work by declaring present/absent/unknown as explicit data rather than inferred shape. **S2** is the
derived-fold increment (#118): it builds the configured-set-plus-facts derivation that checkpoint and
seat surfaces share. This decision is in the same family as S1 — declare present/absent/unknown as
explicit data rather than inferred shape — but it is a **separate** decision and does not resolve or
pre-empt that open question beyond that family note.

1. **Seat catalog is data.** Seats are members of a versioned configured **seat catalog**, the same
   class of configuration as the active checkpoint set S1/S2 establish. Membership, keys, labels, and
   order change through authenticated versioned configuration; product code, schemas, projections,
   packs, and tests never hard-code a fixed seat roster or branch on particular seat-key strings.
   Adding, removing, renaming, or reordering seats requires no product-code change and is proven by a
   mutation test of the same class as the S1/S2 checkpoint-set proof.
2. **Assigned seat.** Each qualifying-stage evidence slot MAY carry exactly one assigned seat key drawn
   from the seat-catalog revision that was active at seat-assignment time. The pinned catalog revision
   is recorded with the seat-assignment fact, so a later catalog revision that removes or renames the
   key leaves the historical seat-assignment fact intact and visible — never re-read as unassigned,
   never blocking; only new seat-assignments must draw from the active revision. Seat-assignment is
   forward-looking accountability for an open or pending slot. It does not move the Workflow graph,
   fill evidence, pass a gate, or rewrite headline-state derivation.
3. **Signing seat.** Completed slot Evidence derives/exposes the signing seat supplied by the Evidence
   verifier assignment interval under INV-62, resolved against the seat-catalog revision that was
   current at evidence time. `Evidence.verifier_principal` remains the canonical signing principal; the
   assignment supplies seat context without a drifting free-text or duplicate `signing_seat` or copied
   principal field.
4. **Assigned ≠ signed is data.** When both seats are present and differ, both remain visible. The
   difference never silently overwrites either fact and never becomes an error that blocks the record,
   transition history, or projection rebuild.
5. **Unassigned is data.** A slot with no assigned seat reads as explicitly unassigned. Surfaces never
   guess a seat from stage key, group key, evidence kind, principal display name, ticket custodian, or
   silence, and never omit the unassigned state so a client must invent a default.
6. **Derivation.** Board, Ticket, and Project Delivery seat surfaces derive only from the configured
   catalog plus explicit seat-assignment and Evidence facts at the source watermark. Each
   seat-assignment fact pins the catalog revision that was active at seat-assignment time, and each
   signing-seat fact pins the revision that was current at evidence time; derivation at the source
   watermark reproduces those pinned facts byte-identically on rebuild — consistent with S2's
   configured-set-plus-facts rule for checkpoints (INV-59).
7. **Sequencing and bounds.** This decision authorizes the SPEC model and the derivation, aggregate,
   and exit-evidence text it requires: US-PD-04; AC-PD-07..09; INV-64; INV-59 (amended to add the active
   seat catalog and seat-assignment facts); the seat fields on AC-PD-01/03/05/06 (the AC-PD-01 and
   AC-PD-04 seat clauses are I2-bound, qualified by their increment as AC-PD-03 is; the I1 exit-evidence
   list at SPEC.md:3770 is satisfied by the pre-seat portion of AC-PD-01); the per-slot seat
   accountability narrative section; the I1.7 CLI-projection narrative (including the bundled
   slot-coverage `filled / required` repair); the I2.4 interactive row-detail bullet; the Seat catalog
   and Project Delivery projection row aggregate boundaries; the Ticket detail paragraph; and the I2
   exit-evidence extension (AC-PD-02..09). Contract, fold, projection, and generated-client carriage
   are a separate implementation slice stacked after S2 (#118) on the same Project Delivery surface. No
   new environment variables or feature flags. D27 and CT-I2-001 remain fail-closed.

Non-normative example of catalog members a configuration might declare for today's crew (not platform
vocabulary): commander, eng-manager, engineer, designer, qa, tech-writer, release-manager, devops-sre,
cso, triage.

Rejected alternatives:

- Hard-coding today's crew names into product schema, fold branches, or normative SPEC vocabulary.
- Inferring a seat from stage key or ticket custodian when assignment is missing.
- Collapsing assigned and signing into one field that rewrites history on sign-off.
- Blocking the record when assigned and signing seats differ.

## D29 — Board card context, generalized Attention, and declared delivery surface (locked 2026-07-31, operator)

A build lane stopped at the escalation gate on 2026-07-30 rather than amend a canonical document to make
its own work pass: the Board card the operator view needs was not authorized by SPEC, 'needs a human'
had only one implemented source, and the delivery-surface declaration a card would read was stated for
skip predicates rather than for surfaces. On 2026-07-31 the operator chose **Option A — amend the SPEC**
and authorized exactly three bounded extensions: **(a)** extend the Board card with tenant display
identity, change/PR reference, labels, human-waiting, and delivery-surface availability; **(b)** generalize
the Attention projection beyond outbox-poison so 'needs a human' is a first-class consumable fact; and
**(c)** add delivery-surface declarations to checkpoint definitions. This entry writes that grant down; it
decides nothing further. It preserves D21's derived Project Delivery model, D24's narrow development
cohort and no-dual-write rule, D27's fresh-start authority and fail-closed CT-I2-001 dependency, D28's
seat model, and INV-34/37/57/59/61–64. It does not weaken CP3-D, the dual-write prohibition, or minimal
carry-forward, and it descopes nothing already required.

**Shorthand used here and in SPEC.** **#115** is the contract/projection issue that raised the escalation
(*"Every view receives the context needed to explain the work"*); **#116** is its CLI renderer child, which
this contract must precede. The **context set** is the Board card's five added members — tenant display
identity, change references, applied labels, human-waiting, delivery-surface availability — named as a set
so a criterion can quantify over them. A **finding** is one appended typed statement that a human need
exists; the **attention-kind catalog** is the versioned configured set its `kind` is drawn from; the
**label vocabulary** is the versioned configured set an applied label is drawn from. **Delivery-surface
availability** is what a surface reads from a checkpoint's declaration: declared-present, declared-absent,
or explicitly undeclared.

1. **The card carries five more facts, each from an explicit record.** Tenant display identity comes from
   the tenant's recorded display fact; change references from linked Change facts exactly as recorded;
   labels from applied-label facts; human-waiting only from a qualifying Attention finding;
   delivery-surface availability only from the qualifying checkpoint definition's pinned declaration. No
   member may be inferred from an identifier's spelling, a title, a branch or repository name, a lane, a
   stage or group key, a blocker type or age, a principal display name, or silence.
2. **Unavailable is stated, never omitted.** Every member is present with an explicit value — empty set,
   declared absence, no-qualifying-checkpoint, or `STATE_UNKNOWN` with its missing source — so a client
   never invents a default. This is the same standard D28 applied to unassigned seats. The card stays a
   disposable projection: the context set adds no writable field, no new authority, and no status patch.
3. **Configured sets are data, and facts referencing them are revision-pinned.** The label vocabulary and
   the attention-kind catalog are versioned configuration of the same class as the active checkpoint set
   and the seat catalog. Membership changes through authenticated versioned commands with no product-code
   change, proven by a mutation suite of the same class as the seat-catalog proof. Each applied-label fact
   pins the vocabulary revision active at application time and each finding pins the catalog revision
   active at append time, so a later revision that removes or renames a key leaves the historical fact
   intact and visible — never re-read as unlabeled or kindless, never blocking; only new facts must draw
   from the active revision. Normative product code, schemas, projections, packs, and tests hard-code no
   fixed roster and branch on no label or kind key.
4. **Human need is a typed appended finding, and the feed is its only source.** A finding carries kind,
   subject, reason code, owner, recommendation, alternatives, consequence/default, deadline, dedupe key,
   and source facts. Resolution, snooze, expiry, and cancellation are further appended facts with actor,
   time, and reason: resolution is data, and a need never ends by a row disappearing. Outbox-poison becomes
   one member of the kind catalog; AC-OPS-16's pass condition is unchanged and is not weakened. Board
   human-waiting and Needs You derive from this one feed under the same existing policy qualification, so
   the two surfaces cannot disagree and a blocker never coerces into a human need.
5. **Checkpoints MAY declare a delivery surface; undeclared reads as undeclared.** A checkpoint definition
   may declare its landing boundary, its non-production environments, and its externally effective outcome,
   each with identity or as an explicit absence. A field its pinned definition never declared is
   explicitly undeclared — `STATE_UNKNOWN`, neither presence nor absence — on every surface that exposes
   it, and it still satisfies no skip predicate and no entry item. AC-WF-27's skip semantics are unchanged,
   and AC-PD-03's I2.4 row-level placement of change/PR references stays exactly where it is.
6. **Increment binding.** All three extensions are I1 work inside the already-scoped generated API,
   protected CLI, Board/Ticket queries, and Attention module: they are a stricter representation and
   derivation rule over facts I1 already owns, adding no agent dispatch, effect, browser route, or sixth
   surface. Two boundaries are named rather than absorbed: browser rendering of every card fact remains
   I2.4 under the existing UX criteria, and change/PR references on the interactive Project Delivery row
   remain I2.4 under AC-PD-03. No I1 checkpoint, projection contract, or exit criterion moves increment,
   and no exit bar is satisfied by evidence gathered against pre-amendment text.
7. **Sequencing and bounds.** This decision authorizes the SPEC model and the narrative, aggregate,
   invariant, acceptance, increment-placement, and exit-evidence text it requires. The complete list of
   amended sites is: US-OP-10, US-OP-11, and US-PD-05; the Board-cards paragraph and the new
   `#### Board card context` narrative in the task-management foundation; the checkpoint-definition
   paragraph of the Project Delivery projection narrative (the `MAY declare` sentence); the new
   `#### Attention findings feed` narrative under *Human gate, Needs You, and resume*; the aggregate
   boundaries for *Project / delivery checkpoint definition* (amended) and *Attention item / finding*
   (amended) plus the new *Ticket label vocabulary* and *Attention-kind catalog* rows; the Attention row of
   the orthogonal state models table; INV-66 and INV-67 (appended, renumbering nothing); AC-TM-05
   (amended) and new AC-TM-07..08; the new `### Attention` acceptance section with AC-ATT-01..02; new
   AC-PD-10; AC-OPS-16 (amended only to name the poison kind as one catalog member); I1 included scope
   item 6; the new **Board-card-context increment placement** paragraph; and the I1 exit-evidence bullet,
   which gains the attention family so the new criteria are swept by an exit bar rather than orphaned.
   `ARCHITECTURE.md` is repaired in the same change as the derived atlas `CLAUDE.md` requires; it needs no
   grant because it may explain but never extend SPEC. No bootstrap backlog row is amended: CT-L0-008's
   exit evidence references the AC-TM family rather than a fixed list, so it carries AC-TM-07..08 as
   written. Contract, projection, API, and generated-client carriage is the #115 implementation lane with
   its #116 renderer child, which resumes on this authorization. No new environment variables or feature
   flags. D27 and CT-I2-001 remain fail-closed.

Rejected alternatives:

- Descoping the Board to what the pre-amendment contract could carry honestly, leaving a renderer to guess
  or make unrelated reads (the operator considered and declined this on 2026-07-31).
- Letting a build lane add the fields to a schema without amending SPEC first.
- Making `human_waiting` a derivation over blockers, lanes, stage names, or blocker age instead of a
  consumed Attention fact.
- A product enum of attention kinds, with outbox-poison as the model rather than as one member.
- Omitting an unavailable member, or serializing it as a bare null a client is free to interpret, instead
  of an explicit empty/absent/unknown value.
- Reading an undeclared delivery-surface field as an absence, or inferring the surface from stage names,
  lanes, or delivery facts.
- Moving AC-PD-03's I2.4 change/PR row placement onto the I1 Board card.

## D30 — The portfolio joins ctower: three projects, one record (locked 2026-08-01, operator)

The operator approved all seven clauses below on 2026-08-01 through the director, adopting the Commander
draft prepared for issue #185 and PR #189. This entry preserves D21's derived Project Delivery model,
D28's configured-seat and revision-pinning discipline, and D27's dormant bulk-import boundary. It supersedes
D24 and D27 only to the extent that either permitted a pre-CP3-D development writer/authority epoch or
treated the legacy corpus as frozen during shadow operation: CT-I1-008 may still record its narrow
development `GO_WITH_LIMITS`, but that verdict stops no legacy writer and makes ctower sole authority for
nothing. D24/D27's CP3-D protection and fail-closed CT-I2-001 dependency remain. Issue #152 remains a hard
gate only for a future multi-database topology, not for the approved single-database portfolio.

1. **Topology — one database, one tenant, three projects.** `manibo` and `bh-loop` join `ctower` as
   Project keys inside the existing tenant and database, using the project-scoped checkpoint and delivery
   model. No Project receives its own database or tenant. Project membership, labels, owners, and starter
   checkpoints are versioned configured data; product code contains no three-project branch or roster
   literal.
2. **Shadow/cutover boundary — coordination record, not sole authority.** The instance keeps the exact
   `SHADOW_ONLY_CP3_D_NOT_PROVEN` label. All three Projects may hold reconstructible tickets, custody,
   Evidence, and disjoint delivery boards. Ctower becomes sole authority for nothing until CP3-D closes and
   the operator separately accepts a portfolio authority epoch. Mission Control ledgers and applicable
   GitHub/GitLab records remain co-sources during shadow operation; no legacy writer is frozen. Bulk import
   stays dormant. The 115-item `manibo` backlog enters item by item through ordinary signed intake.
3. **Prohibited data classes — loud named refusal.** Intake and Evidence refuse credentials, tokens, or
   keys in any form; production customer data; PHI or any HIPAA-covered content; PII beyond staff names and
   work handles; and live incident indicators. Each refusal names its stable class and produces no mutation.
   The BH.Loop boundary permits references to D11 controls, GitHub/GitLab artifacts, and deidentified control
   IDs, but never patient or clinical content. The forbidden-data-class exporter model therefore extends to
   ticket intake and Evidence recording.
4. **Per-project grants — identity is the boundary.** Each Project has a configured Commander principal and
   project-seat credentials scoped to `(project, seat)` with an exact named subset of
   `capture|transition|evidence`. The operator issues and revokes credentials and append-only
   Project grants. Each grant pins the Project, seat-catalog, access-policy, and credential revisions and
   digests; access resolves those pins server-side on every call, and revocation refuses the next call by
   name. Custody gains a target-Project-grant input. A principal from one Project cannot mutate another
   Project's tickets, checkpoints, or Evidence; the refusal is named and changes no state.

   Authorization is exhaustive: only the operator may issue or revoke a project-seat credential or
   grant, or apply a portfolio CompanyBundle; any active matching grant may read its Project according to
   existing visibility rules; `capture` admits or links work and requests initial custody by an eligible
   configured Commander; `transition` performs ordinary typed Work mutations; `evidence` records ordinary
   allowed Evidence; and protected commands, owner surfaces, gates, effects, production, incidents, and
   authority epochs retain their stricter existing authorization and are never implied by these three
   scopes. Unknown, mismatched, foreign-Project, stale-version, and revoked credentials fail closed.

   The initial configured owners are `ctower` → `ctower-commander`, `manibo` → `manibo-commander`, and
   `bh-loop` → `bhloop-commander`; these are configuration values, not product vocabulary. Grant issuance
   and revocation remain operator-only.
5. **Stable work identity.** Source identity is project-scoped as
   `(tenant, project, source kind, source ref)`. The shared R-counter renders stable `<project>-R<nnn>`
   references. Ticket IDs remain instance-global ULIDs. Cross-project reuse and renumbering are forbidden.
6. **Verification — every clause has named proof.** Setup proves one tenant with N Projects. Isolation
   tests all six directed pairs—`manibo`↔`ctower`, `bh-loop`↔`ctower`, and
   `manibo`↔`bh-loop`—and each foreign mutation refuses by name with zero state change. Intake and Evidence
   test every prohibited class, including a PHI-shaped fixture refused by its exact class name. Grant tests
   cover issuance, exact scope subsets, revocation, and the revoked credential's named next-call
   refusal. QA proves three Project-filtered Board views render mutually disjoint rows.
7. **Sequencing is bound.** Stable work proceeds as identities and grant-aware custody (issue #192,
   CT-I1-009) → scopes, isolation, and each Project Commander's starter-checkpoint onboarding configuration
   (CT-I1-010) → ordinary item-by-item intake of `manibo`'s 115 items (CT-I1-011) → the project-scoped feed
   for issue #186 (CT-I1-012). This SPEC revision accompanies the decision. Implementation changes follow
   the normal two-round cross-model gates; no later step may be inferred complete from an earlier step's
   evidence.

Rejected alternatives, as settled by the approved clauses:

- Per-Project databases or tenants for this portfolio.
- Any pre-CP3-D writer freeze, sole-authority claim, or migration cutover.
- Bulk import of the `manibo` backlog or authority-bearing historical state.
- A hard-coded Project/seat roster, unpinned grant, implicit cross-Project access, or grant-derived owner,
  protected-command, effect, incident, or production authority.
- Accepting a prohibited class silently, under a generic error, or as Evidence bytes/metadata rather than
  refusing it by name.

## D31 — Two identity planes, one attributable Actor (locked 2026-08-02, operator R2728)

The operator ordered proper ctower authentication after the portfolio import chain. This decision preserves
D30's project-seat credential plane and D22's private same-origin session protections. It supersedes D23
only to move the authentication-only login/callback/session/logout/error routes and evidence into
`CT-I1-013`; all five browser product surfaces and their interaction evidence remain at I2.4.

1. Humans authenticate through discovery-driven OIDC modeled on Manibo's provider-agnostic auth modules and
   `wiki/systems/auth.md`; machines keep D30/#198's scoped project-seat credentials. The Manibo Commander
   recommends contract reuse without package extraction while both consumers are changing, so ctower
   preserves the pinned Manibo modules/behavior behind its Access Interface and shared conformance vectors.
   Extraction may be reconsidered for a third consumer or after measured non-drift; a new OIDC flow or
   provider fork is forbidden.
2. Provider bindings are versioned configuration authored in the secret-free `CompanyBundle`, including exact
   issuer/discovery/JWKS/audience/client and SecretRef inputs, the exact registered redirect URI, verified
   discovery domains, enabled state, and optional claim-selection metadata. The registry is a trust root with
   one owner: creating, enabling, disabling, or rotating an entry is an operator-only command, and a platform
   administrator holds no such authority unless also authenticated as operator. The redirect URI is pinned to
   the configured private HTTPS origin plus one fixed callback path and matched by exact string equality, so
   no configuration change alone can deliver an authorization code outside the private boundary. Adding,
   disabling, or rotating a provider requires no Python or TypeScript branch.
3. Browser OIDC uses Authorization Code plus PKCE S256, state, nonce, the pinned exact redirect,
   registered-endpoint SSRF confinement, and RS256 verification. Durable human identity is
   `(oidc, issuer, subject)`; email and token roles/groups/tenant/project/seat claims confer no local
   authority. Provider ID and access tokens are verified and then discarded; v1 requests no `offline_access`
   and stores no refresh token, and an entry naming either is refused at apply time. Exactly three provider
   egress call sites exist — discovery, token exchange, and JWKS fetch/rotation — and each declares its
   attempt count, wall-time bound, backoff, and typed terminal outcome. Unverifiable or expired key material
   grants no authority and performs zero mutation; cached keys are never accepted indefinitely and an unknown
   `kid` triggers at most one bounded refetch per cooldown window.
4. Human role vocabulary v1 is exactly `operator`, `commander`, and `viewer`, and all three are enumerated in
   the authorization matrix. Human project authority resolves from an operator-issued, append-only, revocable
   **human role binding** pinned to one principal, one role, its exact project keys, and the access-policy
   revision that interprets it. It is not a project-seat grant and confers no `capture|transition|evidence`
   scope; the two records are disjoint and neither confers the other's authority. Operator retains existing
   protected authority, Commander remains project/custody/policy bound, and viewer is read-only within the
   project keys its binding names and never aggregates the portfolio. Ambiguous, unprovisioned, disabled,
   expired, revoked, replayed, or foreign scope fails closed with no mutation.
5. UI uses the record-backed opaque Secure/HttpOnly/SameSite=Strict ctower session; direct human APIs use
   registered-provider Bearer JWTs; machine APIs use the unchanged project-seat Bearer credential. All three
   transports resolve the same typed Actor and durable principal used by commands, idempotency, custody,
   assignment, Evidence, verdict, effect, and audit attribution, and `INV-73` makes that a chokepoint rather
   than a description: a transport that introduces its own principal, custody, or attribution record is
   forbidden.
6. Tailnet/private HTTPS remains the network boundary. OIDC adds only exact provider-registry egress; it
   creates no public ctower ingress. Browser bearer secrecy, CSRF, expiry, reauthentication, revocation,
   redaction, and safe low-cardinality audit/metrics remain mandatory.
7. `CT-I1-013` depends on `CT-I1-012` and cannot pass without an independent CSO verdict on the exact digest.
   Exit reports fixed counters for reuse, both identity planes, the single Actor/custody model, all three
   roles, all three UI/API auth transports, all eight named auth refusal codes, all three bounded provider
   egress call sites, all eleven security proof groups, zero provider-specific product branches,
   discovered-versus-exercised registry entries, and the CSO verdict.
8. Every authentication denial refuses by a stable named problem code, never a bare 401/403:
   `auth-provider-unavailable`, `auth-exchange-invalid`, `auth-provider-unverifiable`,
   `auth-identity-unresolved`, `auth-session-invalid`, `reauthentication-required`, `auth-role-denied`, and
   the existing `project-scope-denied`. `reauthentication-required` is retained from D22 with its
   zero-reservation, zero-mutation property intact. Codes are deliberately coarse where a finer one would
   enumerate people or configuration, and each requires its own negative fixture and exact RFC 9457 snapshot.

Rejected alternatives are an OIDC implementation invented inside ctower, provider lists or role authority
hard-coded in product code, OIDC claims treated as custody/authorization, a browser-held API bearer, a
second human audit model, replacement of machine seat credentials, any auth-driven public exposure, a
provider registry or human role binding that anyone but the operator may create, enable, or rotate, a
redirect URI matched by anything looser than exact string equality, retention of provider refresh tokens or
an `offline_access` scope, unbounded or fail-open discovery/JWKS verification, and generic unnamed 401/403
authentication denials.

## D32 — The documentation gate is unskippable, and the landing boundary reads it (locked 2026-08-03, operator)

The operator observed on 2026-08-02 that `manibo` pull requests were merging with no documentation
artifact, and ordered through R2738 (P1) that ctower make the documentation gate mechanically
unskippable rather than a remembered process step — "that is the point of the migration." This entry
writes that grant down and decides nothing further. It preserves D21's derived Project Delivery model,
D28's revision-pinning discipline, D29's declared-surface and explicit-absence rules, and D30's portfolio
boundary. It does not weaken CP3-D, the dual-write prohibition, minimal carry-forward, or the
INV-19/INV-44 independence and waiver rules, and it authorizes no implementation by itself.

**What is already true, and what is not.** `engineering.software-factory@1` already declares
`documentation` as a `ship` stage that declares no skip predicate and therefore cannot be omitted at any
risk tier, with required slots `revision`/`truth-check`, a mandatory documentation-truth gate,
`sf.e07.review-documentation@1` as its only entry, and `sf.e08.documentation-preflight@1` requiring its
completion before `release-preflight` and `merge`. That package is I2 work behind full normative I1 exit,
so it governs no merge today. Three gaps let a documented-looking change through anyway, and this decision
closes exactly those three. It adds no stage, edge, group, gate, evidence kind, environment variable, or
feature flag.

1. **A docs revision must answer for the change that produced it.** The `documentation.revision` slot
   contract gains bound requirements, in the same class as `plan.criteria` and `implement.warm-gate`: the
   current candidate digest; the identity and revision of the documentation-generating command run that
   produced the artifact from that candidate; and the complete set of change-carried documented surfaces —
   each operator-visible behavior, API operation, CLI command, configuration key, and runbook step the
   candidate adds or changes — each with the documentation location that now describes it. A surface the
   candidate carries and the revision does not answer for fails the slot contract, and `documentation`
   does not complete. This is the machine form of "generated documentation for new functionality at PR
   time."
2. **A release carries its own docs fact.** `release-preflight` gains a second ordinary required slot,
   `release-notes`: `artifact-digest`, binding the release manifest digest, the complete included-change
   set, each included change's ticket identity and its current `documentation` completion reference, and
   the identity and revision of the release-documentation command run that produced the artifact. An
   included change whose documentation completion is missing, invalidated, expired, revoked, or
   `STATE_UNKNOWN` fails the slot contract, and `release-preflight` does not complete. The stage's signing
   slot stays `manifest` under `stage_owner`. `release-preflight` declares no skip predicate, so this fact
   is owed on every run; binding it at preflight is deliberately earlier than "before a release closes,"
   because a release is preflighted before it can be promoted at all.
3. **The landing boundary reads the record: one gate, two facts.** The required status check of issue #199
   is one check that resolves the ticket bound to the pull request and reports each fact of the
   **landing-boundary predecessor set** separately: every stage the ticket's own pinned Workflow graph
   places before the stage carrying the landing boundary, with every required slot of each resolved and
   current on the candidate digest the pull-request head resolves to. The set is derived from the pinned
   graph, never from stage-key strings, so the check adds no branch AC-WF-25 forbids; naming any package's
   members illustrates that derivation and never replaces it. In `engineering.software-factory@1`, linear
   into `merge`, the set runs from `intake` through `release-preflight`, and the two facts it carries at
   that boundary — review evidence and documentation evidence over preflight — are the operator's "one
   gate, two facts." The check is a pure reader: it writes no record state, mints no Evidence, and is not a
   second writer.
4. **Absence is a named refusal that changes nothing.** A missing, invalidated, expired, revoked, or
   `STATE_UNKNOWN` docs fact is reported by its stable name, alongside every other unmet fact, and the
   check is red — never green with a caveat in its body, never amber, never silently absent. Unknown is a
   failure, not calm. Inside the record the existing unfilled-required-slot refusal already covers both
   slots above with zero authoritative transition mutation and an exact unmet checklist; this decision
   adds no refusal row and no new reason code.
5. **Unskippable means no bypass exists.** The documentation fact is declared waivable at no risk tier.
   No label, comment, administrator merge, re-run, follow-up ticket, green CI run, or reviewer assertion
   that documentation exists satisfies it, and no protected operator waiver reaches it — the waivable
   scope INV-44 permits is the family-diversity placement rule, not this fact. The only path through the
   landing boundary is the recorded artifact.
6. **Increment binding and reality.** The two slot contracts are I2 carriage inside already-scoped work:
   CT-L0-004 already freezes the typed slot vocabulary and contracts generically, CT-I2-001 publishes the
   package, and CT-I2-006 evaluates its policy. The record-backed check is repository infrastructure for
   ctower's own repository, tracked by issue #199 and the R2738 ticket; it reads the record through the
   existing generated API/CLI and therefore does not wait on the package. No increment moves, no exit bar
   is satisfied by evidence gathered against pre-amendment text, and nothing here is described as live
   until its own acceptance evidence exists.
7. **Sequencing and bounds.** This decision authorizes the SPEC text it requires and no more. The complete
   list of amended sites is: US-OP-12 (new); the `release-preflight` row of the required-typed-evidence-
   slot table; the bound-requirement list under that table, which grows from four contracts to six; the
   new `#### Record-backed landing boundary` narrative in the delivery-sprint section; the Documentation
   and Release-preflight rows of the stage-contract projection table; AC-EVD-08 (amended); AC-REL-09
   (new); and INV-74 (appended, renumbering nothing). `ARCHITECTURE.md` is repaired in the same change as
   the derived atlas `CLAUDE.md` requires; it needs no grant because it may explain but never extend SPEC.
   No bootstrap backlog row is amended. Contract, pack, and check implementation is a separate lane
   stacked on the R2738 ticket and issue #199. D27, D30, and CT-I2-001 remain fail-closed.

Rejected alternatives:

- A second documentation stage or gate beside the one `engineering.software-factory@1` already declares —
  the repository forbids a second architecture truth, and the gate was never the missing part.
- Leaving `documentation.revision` free to be filled by a real but unrelated or superseded docs artifact,
  which is exactly the failure the operator observed.
- Recording the release documentation fact as a line item inside the release manifest instead of its own
  required slot, where no slot-completeness rule quantifies over it.
- Reporting the docs fact only in the check's body, as an advisory annotation, or as a separate optional
  check, so a green required check can mean "review passed, documentation unknown."
- A waiver, label, administrator override, or documentation follow-up ticket as a path through the
  landing boundary.
- Deriving the check's fact set by naming `documentation` and `risk-derived-review` stage keys instead of
  the pinned graph's landing-boundary predecessors.
- Accepting a green CI run, a reviewer's assertion, or the presence of changed files under `docs/` as the
  documentation fact.

## D33 — Work sessions become recorded facts (locked 2026-08-03, operator R2698-G5)

The operator authorized [#200](https://github.com/simjak/ctower/issues/200) as the next real product
increment: three operator surfaces — the ticket work timeline, the workspace session states, and the live
feed — each render an honest empty state naming the same missing fact, because ctower does not record that
work happened. This decision creates that fact. It preserves D27 fresh-start authority, D30's project
topology and prohibited-class barrier, INV-15's session-is-never-identity rule, INV-34's disposable
projections, and the existing canonical Record event log. It creates no second event authority, no
writable projection, no browser route, no provider or runtime event, no feature flag, and no environment
variable.

1. **A session is a Record fact, not an observed process.** A work session has its own durable ctower UUID
   and its own `session:<uuid>` append-only stream: one start fact, zero or more authored state facts, and
   at most one close fact. Process IDs, tmux names, panes, and vendor session handles are refused entry;
   [INV-15](SPEC.md#non-negotiable-invariants) is unchanged and a terminal capture is never promoted to a
   session.
2. **The authored lifecycle is closed.** A started session is `dispatched`; the only authored moves are
   `dispatched -> briefed -> working -> gated` and `gated -> working`. Every other pair, a fact on an
   unknown session, and any fact after close refuse by their own stable codes with zero mutation.
3. **Cost facts have two different owners.** Duration is Record-owned and derived from the committed start
   and close timestamps, so a caller cannot claim a cost the record does not already prove. Token counts
   are caller-supplied because only the harness observes them, and they are bounded, typed, strict external
   payload values like every other one.
4. **Sessions inherit every existing rule.** Project scope is applied in the Record query before a session
   is materialized; foreign ticket reads stay non-disclosing 404s and a foreign project page refuses
   `project-scope-denied`. D30 clause 3's five prohibited classes are checked over every caller-authored
   session field ahead of any row, event, or outbox byte.
5. **One authoritative type catalog.** Session membership, payload type, stream prefix, and permitted
   origins are metadata on the canonical Record event catalog. Every derived kind set — envelope schema,
   HTTP union, generated clients, CLI, SQL, tests — is derived from it, and a both-direction parity
   mutation proof refuses drift. Repairing the pre-existing omission of `migration.changed` from the
   authored envelope schema is part of this decision, because the guard that proves the rule found it.
6. **Sequencing and bounds.** This decision authorizes only the SPEC 1.14 amendments at INV-75, the
   recorded-work-sessions architecture narrative, AC-SES-01..04, and the I1 exit-evidence bullet;
   `ARCHITECTURE.md` and `IMPLEMENTATION-ROADMAP.md` are repaired as derived explanations. Backend
   Record/API/contracts/generated clients/CLI belong to #200. The three waiting operator surfaces swap to
   this source in their own lanes and are explicitly out of scope here.

Rejected alternatives:

- A session-specific kind enum in API, CLI, browser, query code, or tests that can drift from the catalog.
- Caller-supplied duration, or a duration inferred from anything other than committed Record timestamps.
- Treating a tmux name, PID, pane, or vendor session ID as session identity or as evidence a session exists.
- Synthesizing a session, a heartbeat, or a state from terminal capture, transport activity, or silence.
- A mutable session row whose state is updated in place instead of appended.

## D34 — The fleet-lifecycle policy package: close gate first (locked 2026-08-03, operator R2764)

Issue #252 and mission-control R2764 (director P1; record ticket `019fc841-344f-7ccc-8449-262a132d6ae2`)
turn the mission-control fleet's hygiene rules — today enforced by commander memory and paging crons only,
so nothing blocks — into a **versioned policy package**, `fleet-lifecycle@1`, evaluated by the **existing**
Execution Policy engine (CT-I2-006). This writes that decision down, superseding nothing (append-only).

**No parallel engine, no new mechanism.** The package is authored data under `packs/policies/lifecycle/`
that binds gates only to locations the pinned Workflow already declares ([INV-46](#non-negotiable-invariants)
— no new node or edge). Asserting a close-gate binding therefore adds no stage, edge, group, or gate
location, and adds no evidence kind; it uses the lifecycle evidence contract class.

**What it does.** On the administrative-close boundary of `engineering.software-factory@1`
(`sf.e15.retro-resolve-close@1`), close is denied unless three current facts hold for the episode — no
live bound crew session (`crew-session-still-live`), no worktree surviving a merged PR with merge-state
from the PR record, never branch ancestry (`worktree-outlives-merged-pr`), and the crew-log close entry
(`crew-log-close-entry-missing`). Episode binding (bound-crew from crew-log ticket/source-ref, bound-PR
from the evidence manifest), freshness (reference = max(resolution event time, latest bound-PR merge
time)), the explicit `no-crew-engagement` / `no-bound-pr` assertions for empty bound sets, and the
`substrate-unobservable:<probe>` refusal are defined in the SPEC text. The naming, WIP-cap, and
resource-ceilings policies are listed as spawn-side stubs (CommandGuard boundary, [INV-58](#non-negotiable-invariants))
and deliberately not designed. Coordination-files and liveness stay paging-only by design; the existing
paging tools become evidence sources, never parallel enforcement.

**What it does NOT do.** It authorizes no implementation by itself, blocks no close today, and does not
weaken CP3-D, the dual-write prohibition, minimal carry-forward, INV-19/44/62 independence, or the
documentation/landing-boundary work of D32. It preserves D27, D28, D30, D31, and D32. The SPEC change is
docs-only through the docs gate; engine evaluation rides CT-I2-006 in increment order, and the
mission-control reporter is a separate ticket when the pack lands.

## D35 — Assignment model visibility is substrate truth, not self-report (locked 2026-08-04, operator R2768)

Issue #257 and mission-control R2768 (record ticket `019fc8aa-02a8-714b-b899-481af3fcf7e4`) lock the model
and harness visibility story for assigned crews. A **seat** is the durable principal; a **crew** is one
engagement of that seat and never becomes a principal. This decision preserves D30's project-seat grant
model, D33's recorded work-session facts, D34's reporter/refusal discipline, INV-09 custody, INV-15 session
non-identity, INV-69 project grants, and INV-73's one-Actor model.

**Two-step anchor.** Before CT-I1-009/R2761 project-seat principal records exist, dispatch-time assignment
stamps come from mission-control `crew-log` plus Hermes gateway/provider logs through a bridge reporter.
After project-seat principals land, the same assignment stamp shape promotes to the seat principal/project
grant anchor. Historical bridge facts stay readable; the crew remains engagement identity and evented facts,
not a new principal object.

**Events, not a field.** The dispatch stamp is immutable. Later fallback or degradation appends
`model_changed` on the assignment with `from`, `to`, `observed_at`, `source`, and probe evidence. The
current effective model is a fold over those events; no implementation may overwrite a mutable model field
and erase the degradation that the operator needs to see.

**Substrate-reported only.** The only accepted sources are mission-control crew-log and Hermes
gateway/provider logs. Seat or crew self-report is refused, because a forced model can report itself as the
primary. The reporter uses the R2764/D34 pattern and fails loudly by exact name, including
`substrate-unobservable:<probe>`, rather than turning missing substrate into silence or green state.

**G5 seam.** Assignment stamps are dispatch-time facts. D33/#258 recorded work sessions are execution-time
facts whose merged code already records `ticket_id`, `seat_key`, `crew_name`, `harness_ref`, `model_ref`,
`worktree_ref`, and `branch_ref`. The exact durable join is the Work assignment key
`(ticket_id, assignment_kind, scope_ref, interval_sequence)` when it is carried end to end; until then the
cross-check uses the dispatch tuple under interval containment. A mismatch creates visible evidence and
rewrites neither side.

**R2765 parity.** Acceptance names both planes: `ctl ticket assignments` must show the dispatch stamp plus
append-only model-change history, and the Board card must show the assignment-visibility chip with current
model plus a degraded marker when the latest event differs from the dispatch stamp.

**R2781 harness independence.** Harness is an open enum on assignment stamps, `model_changed` events, and
session facts. `claude-code`, `hermes`, `codex`, and `qwen-code` are baseline known values, not the closed
universe. Unknown harness values are carried and displayed exactly as observed, included in cross-checks, and
never rejected or collapsed to `other`. This also names the Harness Independence invariant: no custody,
event, status, reporter, Board, CLI, Evidence, or session integration may assume one harness's session shape.
Reporter facts come from substrate-visible tmux/process metadata where authorized, crew-log, gateway logs,
and provider logs; they do not parse Claude Code, Hermes, Codex, Qwen Code, or future harness-private session
internals to infer custody, status, model changes, or costs.

Rejected alternatives:

- A mutable `current_model` assignment field that overwrites the original dispatch truth.
- A crew principal object separate from the seat principal/project grant model.
- Seat, crew, prompt, terminal, or model self-report as evidence of actual harness/model.
- A reporter that treats missing crew-log or gateway substrate as absent data rather than
  `substrate-unobservable:<probe>`.
- Implementing only CLI or only UI visibility and calling parity satisfied.
- A closed harness enum, an `other` harness bucket, or any harness-specific session/transcript parser hidden
  behind a generic reporter interface.

## D36 — D30 clause 5 corrected: Ticket IDs are UUIDv7, not ULID (2026-08-04, gh#210)

Issue #210 (found at digest `0c28bc203a55565dd9b193cb2b8f2422cd19d33f` during PR #195 review round 2)
flagged that `DECISIONS.md:1106` (D30 clause 5, as locked) reads "Ticket IDs remain instance-global ULIDs"
while `SPEC.md` states UUIDv7 in nine places (INV-06, INV-71, AC-PORT-06, and six others) and every
authored `format: uuid` JSON Schema contract agrees. Both document sides were correct on their own terms
— D30 was correctly left unedited as an accepted decision, and SPEC.md was correctly reconciled with the
authored contracts — but nothing recorded *why* the wording diverges, or which side reflects reality.

**The ruling fact is code.** No ULID generator, library, or schema pattern exists anywhere in this
repository. Every ticket, event, credential, session, run, and outbox identifier — Kernel-wide — is built
by one shared constructor:

- `packages/ctower-kernel/src/ctower_kernel/record/_uuid.py:12` — `def uuid7(now: datetime) -> UUID`,
  "Shared UUIDv7 construction for Record-owned identities," building an RFC 9562 UUIDv7 bit pattern from
  the supplied authoritative time plus 74 bits of `secrets.randbits`.
- Every Kernel module that mints a Ticket ID calls this constructor (or a local `_uuid7` copy of the same
  RFC 9562 shape) exclusively — for example `record/_ticket_sql.py:63`, `record/_intake_sql.py:516`, and
  `migration/_ticket_operation_sql.py:51` — and a repository-wide search for `ulid` (case-insensitive)
  across `.py`/`.ts`/`.tsx` finds zero generators, zero imports, and zero schema declarations; its only
  three hits are UI comments (`apps/ctower-ui/src/read/sources/seatNames.ts:6,10,21`) using "ULID" as
  loose prose for a long identifier, not a distinct encoding.
- Every ticket-identity JSON Schema — e.g. `contracts/domain/task-management/board-view.schema.json:48`
  (`"ticket_id": {"type": "string", "format": "uuid"}`) — declares `format: uuid`; none declares a ULID
  pattern.

**This entry preserves D30 in full and supersedes only clause 5's word "ULID."** Clause 5 is read going
forward as: *"Ticket IDs remain instance-global UUIDv7 values."* Clause 5's substantive property —
permanent, instance-global identity, with `(tenant, project, source kind, source ref)` staying the
separate project-scoped identity plane and no cross-project reuse or renumbering — is unchanged; only the
encoding noun was wrong, and it was wrong from D30's own lock date, not as of any later migration. No
identifier migration is approved, proposed, or implied. Closes gh#210.

Rejected alternatives:

- Editing D30 clause 5 in place — DECISIONS.md is append-only; an accepted clause is superseded, never
  rewritten.
- Changing SPEC.md, ARCHITECTURE.md, or any contract to say ULID — the code evidence above shows that
  would move every one of those documents away from implementation truth, not toward it.

## D37 — A published contract shape is immutable; version it instead of editing it in place (engineering clarification, 2026-08-04, gh#175)

This is an implementation-consistency clarification, not a new operator-locked product choice and not a
rewrite of D1–D36. `contracts/README.md` already says contracts are "versioned, immutable after
publication"; this decision operationalizes that sentence for `contracts/evidence/evidence-manifest.schema.json`
after gh#175 found it had not been followed, and fixes the mechanism so the next contract change cannot
repeat the same silent break.

**What happened.** PR #171's own branch commits already renamed `artifacts`→`criteria` and
`deferred_sources`→`deferred_capabilities`, and the squash-merge that landed as `25f07b3` went further
still — `deferred_capabilities`→`deferred_suites`, `criterionDisposition`'s required fields gained
`criterion_source` and dropped `applicability_reason`, and `criterion_key`/`owner` moved from a single
`stableKey` pattern to the source-typed `gatePolicyCriterionKey`/`acceptanceCriterionCode`/`ownerTicket`
patterns in use today. All of this happened under the one unchanged `$id` and `schema.const:
"ctower.evidence-manifest/v1"`. Zero consumers existed at the time (gh#175), so nothing broke in
production, but the version identifier never signaled that the contract had changed shape at all — the
next consumer would have inherited that ambiguity for free.

**Going forward.** A schema's `schema.const`/`$id` marks a published shape. Once a schema file is merged
to `main`, its normative shape — `required`, `properties`, `$defs`, and any `pattern`/`type`/`const`/`enum`/
`$ref` therein — is immutable. `title`, `description`, and `$comment` stay free to edit; they carry no
contract. An incompatible change (an added/removed/renamed required field, a narrowed or widened
`pattern`/`type`/`enum`/`const`, a retargeted `$ref`) is published as a new version: a new file
(`evidence-manifest-v2.schema.json`) with `$id` and `schema.const` bumped to `/v2`, mirroring the existing
`contracts/domain/migration/ctower-project-*-v2.schema.json` precedent. It is never expressed by editing the
`/v1` file's normative shape in place.

**Mechanism.** `tests/contracts/evidence/test_evidence_manifest.py::TestSchemaVersioningDiscipline` locks
the committed schema's normative shape to a recorded digest keyed by its declared `schema.const`. A future
edit to that shape without a matching new version and a new recorded lock fails that test by name, naming
the stale const and pointing at the `-v2.schema.json` precedent instead of another silent in-place edit.

**Does not build gh#174.** gh#174 (binding `verdict_id`/`candidate_digest` onto each `criterionDisposition`
row instead of a flat manifest-level `verdict_ids` array) remains queued behind this decision and is not
implemented here. This decision only ensures that when gh#174 lands, it is expressible as a `/v2` bump
under the mechanism above, not another change absorbed silently into `/v1`.

Rejected alternatives:

- Bumping `evidence-manifest` to `/v2` right now for gh#175 itself. Rejected: gh#175 confirms zero
  consumers exist, so there is no live shape to protect by forking the file today, and the current `/v1`
  shape is otherwise coherent and fully covered by `tests/contracts/evidence`. Documenting the discipline
  and locking it mechanically is the smaller change that still satisfies gh#175's acceptance.
- A schema-wide byte-identical lock (hashing the whole file, docstrings included). Rejected: it would force
  a version bump for prose-only edits, which is not what "incompatible" means and would make the lock
  something engineers route around instead of respecting.
- Bumping `schema.const` to `/v2` inside the existing `evidence-manifest.schema.json` file rather than
  publishing a new file. Rejected: it repeats exactly the defect this decision closes — a version string
  that changes without a discoverable diff between two files — and breaks the file-per-version precedent
  already established under `contracts/domain/migration/`.

## D38 — Project event feed reuses the ticket-audit read shape; no project-encoded cursor (engineering, 2026-08-05, gh#186)

CT-I1-012 (SPEC.md `INV-78`, [#186](https://github.com/simjak/ctower/issues/186)) is built against today's
Record read conventions rather than the design an earlier, never-landed attempt at this feature carried on
a stacked branch that was lost before reaching `main` (a squashed commit, `63dd169`, merged into a
since-deleted intermediate branch whose own head never became an ancestor of `main`). That attempt predates
several Record read paths this decision now reuses instead of re-deriving.

1. **The feed is a project-scoped variant of the existing ticket-audit query, not a new query shape.**
   `Record.ticket_audit` already unions every project-feed-eligible kind for one ticket through one
   `event_links` subject join (`link.subject_kind = 'ticket'`); the new `Record.project_events` runs the
   identical join scoped by `tickets.project_key` instead of one `ticket_id`, restricted to the catalog's
   `project_feed`-tagged kinds. No `aggregate-ticket` versus `linked-ticket` distinction is threaded through
   the SQL layer — `event_links` already carries that distinction for every eligible kind.
2. **Authorization is the existing project-grant refusal, not a project-encoded cursor.** `Record.project_events`
   calls the same `project_scope_refusal` (INV-69) that `Record.work_sessions.for_project` already calls;
   a caller without an active grant on the requested project refuses `project-scope-denied` before any row
   is read. The cursor itself is a plain `record_position` integer, identical to `ticket_audit` and
   `project_sessions` — it carries no project identity to protect, because every call re-evaluates the
   grant and re-applies the project predicate in SQL regardless of the cursor value presented.
3. **Feed membership is one boolean column, not a link-strategy enum.** `EventCatalogEntry.project_feed:
   bool` extends the catalog already introduced for `session_fact`; `project_event_kinds()` derives the
   feed's kind set by filtering that column, mirroring the existing session-kind derivation. Today's six
   `project_feed=True` kinds are exactly the six non-session branches of the existing `AuditEvent` union
   (`ticket.created`, `ticket.custody_transferred`, `ticket.comment_added`, `work.changed`,
   `workflow.changed`, `proof.changed`); the wire schema reuses those six existing named OpenAPI components
   (`TicketCreatedAuditEvent` etc.) under a new `ProjectEvent` `oneOf`, rather than declaring six duplicate
   schemas. Session and heartbeat kinds carry `project_feed=False` and remain absent pending
   [#200](https://github.com/simjak/ctower/issues/200).
4. **No new environment variable, flag, or writable authority.** The route is a read composed the same way
   `list_project_sessions` is composed; `ctowerctl project events` follows the existing `project delivery
   query` CLI home. This decision authorizes only SPEC.md `INV-78`, the "Project event feed" architecture
   narrative, and the CT-I1-012 I1-exit-evidence bullet at SPEC 1.15.

Rejected alternatives:

- Recovering the dangling `63dd169`/`fe510de` commits by cherry-pick. Rejected after attempting it: the
  base they were built on (`feat/185-scopes` at a pre-#197 commit) has since diverged from `main` on the
  same surfaces this feature touches — `SPEC.md` invariant numbering (their `INV-68` collides with today's
  unrelated `INV-68`), `DECISIONS.md` `D30` (their `D30` collides with today's unrelated `D30`), and every
  `generated/` file — producing a conflict-resolution patch larger and riskier than a fresh, small diff
  against today's actual Record conventions.
- A project-encoded opaque cursor (`v1:<project>:<accepted>:<record>`) binding the requested project into
  the cursor value itself. Rejected: no other project-scoped Record read in this codebase does this
  (`project_sessions` uses a plain integer); the grant check already re-runs on every call, so a
  cross-project cursor replay changes which project's rows a query returns, not whether the caller is
  authorized to see them — the authorization boundary is the grant, not the cursor shape.
- A strict "accepted-only" filter distinguishing durability-pending events from committed ones inside the
  feed query. Rejected: no existing Record read path (`ticket_audit`, `project_sessions`, `ticket_timeline`)
  applies such a filter — Postgres transaction visibility already means a row a read query can see is
  committed; "pending" in this codebase describes off-host acknowledgement receipts, not local commit
  visibility. Introducing a feed-only filter for a distinction no sibling read path makes would be
  speculative complexity the current requirements do not need.

## D39 — One narrow GitLab Issue co-source, without a connector framework (engineering, 2026-08-08, gh#346)

CT-I1-014 activates one configured GitLab feedback project as a standing issue co-source during
`SHADOW_ONLY_CP3_D_NOT_PROVEN`. This supersedes only the earlier broad deferral of source-host connectors
for this exact GitLab Issue path. Email, chat, GitHub ingestion, arbitrary GitLab objects, generic webhooks,
provider-general SCM abstractions, bulk import, and source-of-truth cutover remain deferred.

1. **The mapping uses ordinary authority.** One normalized GitLab issue becomes an
   `external_untrusted` ordinary intake with a stable `gitlab:<project_id>:<iid>` source reference, P2
   priority, configured Commander custody, title, body, labels, reporter, and HTTPS source link. An
   immutable relation joins issue, inbound thread, and ticket; it is the sole dedupe/custody chain across
   later configuration revisions. Provider changes append ticket comments. Provider closure is observed
   as a change but cannot resolve ctower work or manufacture proof.
2. **Ctower closure remains proof-gated.** Only the canonical project event produced by a successful
   `resolve_close` with lifecycle facts `resolved,closed` may deliver a marker-bound comment and close the
   linked GitLab issue. The event-bound immutable receipt plus provider marker makes retry converge without
   a duplicate comment or close storm. No GitLab label, state, comment, webhook, or operator action at the
   provider bypasses Workflow or Proof.
3. **Standing means bounded durable progress.** One due tick reads at most one GitLab issue page (maximum
   100) and one ctower project-event page (maximum 100), then advances an aware `updated_after`/page/event
   cursor pinned to the exact active Catalog component revision and digest. The next-poll time prevents a
   tight loop; failures use a bounded retry delay and count. Pagination and replay are explicit. No
   unbounded tailer, scan, queue, or per-integration process is introduced.
4. **The Seam is specific and internal.** The kernel owns a small GitLab-issue Adapter Interface and
   durable integration-store Interface; the API artifact supplies one real GitLab HTTP Adapter and the
   standing composition, while the same conformance suite exercises the real Adapter through an honest
   HTTP transport fixture and a deterministic fake. This follows D10's small-Interface/conformance shape
   without claiming a generalized public provider Seam or plugin framework from one real provider.
5. **Configuration is revision-pinned and secret-free.** The already-published
   `ctower.integration/v1` reference-only shape remains immutable under D37. The active shape is the new
   `ctower.integration/v2` file, containing only the HTTPS origin, numeric project, bounded import/poll
   settings, ctower project/custodian, label map, and an uppercase deployment secret-binding reference.
   Deployment resolves the token outside Catalog; resolved credential bytes enter no contract, durable
   row, exception, log, receipt, or telemetry.

Rejected alternatives:

- A webhook-first service or generic source-connector host. Rejected because a bounded cursor in the
  existing control worker is the smallest standing end-to-end product and does not create another ingress,
  queue, runtime, or extension authority.
- Treating GitLab `closed` as ctower completion. Rejected because it would let an external co-source forge
  the proof-gated lifecycle authority that ctower exists to protect.
- Editing `ctower.integration/v1` in place. Rejected by D37; the incompatible active shape is published as
  v2 and v1 remains byte-for-byte available to historical readers.

## D40 — Notification mirroring reuses native Inbox with a derived pair thread (engineering, 2026-08-08, gh#355)

Issue #355 activates one transitional transport from mission-control `tools/notify` into the native Inbox.
It preserves D31's one-Actor identity chokepoint, D35's seat-as-principal rule, INV-79's append-only delivery
facts, and the existing durable mission-control inbox during shadow operation. It authorizes no cutover,
credential provisioning, feature flag, browser surface, or new message authority.

1. **Rail 1 completes first.** The existing durable append remains unchanged and authoritative for its rail.
   Only after it succeeds does the adapter attempt ctower. A typed refusal, malformed response, unavailable
   endpoint, or client failure returns a visible `refused|unavailable` mirror outcome but cannot block or
   reverse rail 1.
2. **The request carries no sender authority.** Rail 2 contains recipient seat and text, with the original
   delivery UUID as its idempotency key. Ctower resolves the sender from the authenticated Actor and the
   recipient from the persisted project-seat registry. Unknown, ambiguous, unaddressable, and self seats
   reuse the ordinary recorded Inbox refusals and create no principal or event.
3. **Grouping is derived, not stored twice.** Ctower derives one opaque thread UUID from tenant plus the
   unordered pair of principal IDs. The first delivery opens that native thread and later traffic in either
   direction appends to it. The existing Inbox thread, messages, canonical events, command result, and
   outbox remain the only authorities; there is no pair map, bridge ledger, cursor, or writable projection.
4. **Replay is the existing command law.** Exact delivery-ID replay returns the original command result;
   changed semantics under that UUID refuse as `idempotency-conflict`. The new strict HTTP/generated-client/
   protected-CLI operation composes the same Inbox Interface and durability protocol rather than creating a
   second ingestion engine.

Rejected alternatives:

- Trusting `--from`, a sender field, crew name, or process label as identity.
- Keeping a mission-control pair-to-thread mapping file or a ctower bridge-specific store.
- Coupling both rails in one transaction or allowing rail-2 failure to change rail-1 success.
- Adding a cutover flag, environment variable, automatic seat creation, or a new notification event kind.

## D41 — Separate server-mediated Inbox promotion dogfood boundary (locked 2026-08-08, operator)

The operator permits one narrow exception to D23's no-I1-browser-artifact timing: `apps/ctower-ui` may
remain a separate, local shadow-instance dogfood server and expose one Inbox control over the already
authored `POST /v1/inbox/threads/{thread_id}/promotion` operation. This entry supersedes only D23's and
the prior I1 Inbox wording's blanket prohibition as applied to that exact non-product dogfood control. D22,
D23, D31, CT-I1-005, and CT-I2-005 still reserve every product browser route, browser authentication
surface, Playwright suite, and five-surface realization for I2.4.

1. **One existing command, no client authority.** The dogfood control may create a ticket from the immutable
   thread head or link an in-scope ticket only by calling the existing generated command endpoint. Its browser
   receives no API bearer, session, CSRF token, credential, actor, project, scope, custody, or authorization
   claim. A server action holds the existing server-side bearer and sends only `{}` or `{ticket_id}`; the API
   remains the sole authentication and authorization authority.
2. **The transport stays bounded and replay-safe.** The action creates one `Idempotency-Key` before its first
   attempt and reuses that exact key for every retry. `408`, `425`, `429`, and the declared transient `5xx`
   statuses re-enter the finite, deadline-bounded, capped full-jitter loop. A permanent problem document is
   terminal and its validated human `detail` is the only server-provided refusal copy the control renders.
3. **Copy names the real scope.** The `New ticket` rail affordance remains visibly disabled and names only
   its own unavailable capture path. Shared Inbox provenance copy names the server-authorized promotion path;
   it must not claim that no mutation path exists on the surface.
4. **The exception earns no product scope.** This separate Next.js dogfood server is neither `ctower-web` nor
   an I1 product route. It introduces no product session design, direct browser API client, record-tier
   connection, new command, contract, role, test-suite activation, capability flag, deployment promise, or
   CT-I1-005/CT-I2-005 evidence. It remains for low-value reconstructible shadow dogfood only.

Rejected alternatives:

- Treating the control as an early I2.4 browser product or a general exception for browser mutations. It is
  one server-mediated command on one explicitly separate dogfood boundary.
- Passing a bearer, session credential, CSRF token, or claimed authority fact to browser JavaScript, DOM,
  storage, URL, telemetry, or screenshots. The existing API authorization boundary is retained.
- Leaving a global read-only claim beside the working control, or enabling `New ticket` by association. Each
  rendered affordance must state only the capability it actually has.

## D42 — The dogfood exception activates one verification suite, and only that (engineering, 2026-08-08, gh#379)

D41 clause 4 disclaimed any `test-suite activation`, and the same candidate registered
`dogfood-inbox-promotion` as a `status = "required"` suite that `just verify` executes and counts. Both
halves cannot be true. The registration is the correct half — an exception that ships a working control
and then proves nothing about it is not a smaller commitment, it is an unverified one — so the contract
text is what is repaired. This entry preserves D41 and supersedes only clause 4's "test-suite activation"
disclaimer, and only for the one suite named here.

1. **One activated suite, named.** The exception activates exactly one required verification suite,
   `dogfood-inbox-promotion`, owned by `CT-I1-007`. It proves the dogfood boundary's own claims: the bounded,
   replay-safe transport, and the rendered copy clause 3 governs. No other suite changes status, and a second
   dogfood suite is a new decision, not a reading of this one.
2. **The rendered claim is proved in a browser, on the dogfood boundary only.** Clause 3 is about a sentence
   an operator reads, which is composed at render time from a frame component, a rail constant and a screen;
   reading those files proves nothing about the page. The suite may therefore build the separate dogfood
   server, serve it on an ephemeral loopback port against a local stub record source on another, and drive
   the rendered Inbox surface in a headless browser at the design bar's three widths. It reads: it never
   submits the promotion command from a browser, and it never addresses a running instance, an operator's
   port, or any credential.
3. **The product browser scope stays reserved.** `browser-e2e` stays deferred to `CT-I2-005`, and D22, D23,
   D31, CT-I1-005 and CT-I2-005 still reserve every product browser route, browser authentication surface,
   product Playwright suite, and five-surface realization for I2.4. A browser used as a read instrument
   against a non-product dogfood server is not a browser product, and this entry authorizes no browser
   evidence for any `CT-I1-005` or `CT-I2-005` obligation.
4. **The verification host declares its browser.** The suite's browser is the Chromium build pinned by
   `@playwright/test` in `pnpm-lock.yaml`, installed by the verify workflow before the gates run. A host
   without it fails the suite by name; it is never skipped, and a missing browser never passes quietly.
5. **Everything else clause 4 withheld is still withheld.** The exception still introduces no product session
   design, direct browser API client, record-tier connection, new command, contract, role, capability flag,
   or deployment promise, and remains for low-value reconstructible shadow dogfood only.

Rejected alternatives:

- Unregistering `dogfood-inbox-promotion` to make clause 4 true as written. That resolves the contradiction
  by deleting the verification, leaving a shipped control whose bounded transport and rendered copy no gate
  proves.
- Editing D41 clause 4 in place. `DECISIONS.md` is append-only; an accepted clause is superseded, never
  rewritten (D36).
- Activating `browser-e2e` or filing the render assertion under `tests/e2e`. That is the product browser
  suite `CT-I2-005` owns, and borrowing it would grant the I2.4 scope D41 disclaims.
- Asserting the rendered copy by reading `RecordFoot.tsx` and `rail.ts` from disk. A source-text search
  passes while the composed page still carries a retired claim, which is exactly the escape that produced
  this entry.
## D43 — Provider-neutral internal issue-connector seam, with GitLab-only product scope (engineering, 2026-08-08, gh#381)

Phase 1 of issue #381 supersedes D39 only where D39 made the internal Adapter, progress shape, and standing
composition GitLab-specific. D39's accepted GitLab product behavior, ordinary Work/Record authority,
proof-gated close rule, credential custody, and deferral of every other provider/product capability remain
in force.

1. **The internal seam is provider-neutral and exact.** Kernel Integrations owns strict normalized issue,
   opaque cursor, typed result/failure, registration, claim, custody, observation, and delivery-receipt
   values; a core-owned bounded retry executor; and one leased/fenced tick service. The complete adapter
   protocol has only `fetch_page` and `comment_and_close`. Provider transport, payload mapping, external
   identity, cursor codec, classification, and ambiguous-write marker reconciliation remain in the API-owned
   provider implementation.
2. **Registration is closed and revision-pinned.** The API composition root uses a static first-party
   registry that rejects duplicate adapter kinds and schema identifiers, verifies the parser's echoed
   Catalog key/revision/digest, resolves only declared runtime credential bindings, and composes every
   supported active registration independently. There is no import string, dynamic package, entry point,
   connector-supplied SQL, or public plugin surface.
3. **Generic persistence replaces provider-shaped execution state.** Migration 0055 preserves every 0054
   progress cursor/fence, immutable issue/thread/ticket link, normalized observation, and proof-close
   receipt before removing the GitLab-shaped tables. Core stores a bounded opaque cursor and exact
   `(tenant, registration, external_ref)` custody without interpreting provider identifiers or pagination.
4. **Product scope does not expand.** GitLab remains the only registered and accepted connector. GitHub,
   other source hosts, public connector APIs, webhooks, arbitrary provider effects, and dynamic plugins stay
   deferred. Adding another provider requires its own activated ticket and security review and must pass the
   unchanged shared conformance and real-PostgreSQL admission traces without editing the frozen core seam.

Rejected alternatives:

- Wrapping the D39 GitLab-specific core behind a generic facade. Rejected because it would preserve two
  execution paths, leave provider cursor and persistence semantics in kernel authority, and provide no
  credible second-provider freeze boundary.
- Treating an internal provider-neutral Interface as authorization for GitHub or a marketplace. Rejected
  because implementation structure does not activate product behavior, credentials, egress, or public
  extension authority.

## D44 — The dogfood Inbox boundary carries the send control, and its one suite drives it (engineering, 2026-08-09, gh#372)

Operator ruling R2882 made UI surfaces mutating with authority held server-side, and named chat-send as one
of the paths it unblocks. D41 permitted exactly one dogfood control and named the promotion endpoint; the
send box is the second control on the same separate `ctower-ui` boundary, over the same already-authored
Inbox rails. This entry extends that permission to `POST /v1/inbox/messages` and supersedes only the three
clauses named below. D41's authority model, D42's one-suite rule, D22, D23, D31, CT-I1-005 and CT-I2-005
are otherwise unchanged, and every product browser route, authentication surface and Playwright suite
remains reserved for I2.4.

1. **One more existing command, and still no client authority.** The send box calls only the authored
   `sendInboxMessage` operation. Its browser receives no API bearer, session, CSRF token, credential,
   actor, project, scope, custody, or authorization claim, and it submits exactly one value: the message
   text. The thread is bound into the Server Action from the route. The recipient is an identity, so it is
   read back from the server's own recipient-scoped projection at submit time rather than posted from a
   form — there is no recipient field a browser could edit. The sender is never sent at all; the API
   derives it from the bearer it validates and refuses an unaddressable principal by its own stable name.
2. **The transport is D41 clause 2, unchanged.** One `Idempotency-Key` is minted before the first attempt
   and reused for every retry; the declared transient statuses re-enter the finite, deadline-bounded,
   capped full-jitter loop; a permanent problem document is terminal and its validated human `detail` is
   the only server-provided refusal copy the box renders.
3. **Copy names both paths.** This supersedes D41 clause 3's single-path provenance sentence only: the
   shared Inbox provenance line now names the server-authorized send *and* promotion paths. It still must
   not claim that no mutation path exists on the surface, and the `New ticket` rail affordance remains
   visibly disabled and still names only its own unavailable capture path. The Feed composer gains
   nothing by association: it is a different capability with no authored command behind it, and it stays
   inert.
4. **Still exactly one activated suite, renamed to what it proves.** This supersedes D42 clause 1's suite
   *name* only. `dogfood-inbox-promotion` becomes `dogfood-inbox-controls`, owned by `CT-I1-007`, because
   one suite now proves both controls on this boundary. No second suite is registered, no other suite
   changes status, and `browser-e2e` stays deferred to `CT-I2-005`.
5. **That suite may submit the send box from the browser.** This supersedes D42 clause 2's never-submits
   restriction only for the send control, and only against the local stub record source. The claim the
   send box exists to make is that a typed message appears in the thread without a reload; that is a
   statement about one document's lifetime, and no source file and no server-side test can carry it. The
   suite therefore stamps the document, submits, and proves the stamp survived. It still serves an
   ephemeral loopback port against a local stub, never addresses a running instance or an operator's port,
   never holds a credential, and never submits the promotion form from a browser.
6. **Everything else D41 clause 4 and D42 clause 5 withheld is still withheld.** No product session
   design, direct browser API client, record-tier connection, new command, new contract, new role,
   capability flag, or deployment promise. This remains low-value reconstructible shadow dogfood.

Rejected alternatives:

- Posting the recipient from a hidden form field, the way the promotion control posts a chosen ticket ID.
  A ticket ID is a target the server re-authorizes; a recipient seat is an identity, and putting one on
  the wire from a browser would make the surface assert who a message is between. The extra loopback read
  is the cheaper honesty.
- Registering a second dogfood suite for the send control. D42 clause 1 requires a decision for that, and
  this is that decision saying no: a second `next build` and browser in the release gate would buy nothing
  the one suite cannot prove, and would double the slowest gate's cost.
- Leaving the round trip as one session's screenshot evidence with no gate behind it. That is exactly the
  contradiction D42 was written to repair — a shipped control whose central claim no suite proves.
- Keeping the suite named `dogfood-inbox-promotion` while it proves two controls. An identifier that names
  one of the things it covers is a stale name, and `DECISIONS.md` is superseded, never rewritten (D36), so
  the rename is recorded here rather than edited into D42.

## D45 — The dogfood send box tells a non-accepted answer from an accepted one (engineering, 2026-08-09, gh#372)

The independent review of the send box found it reading `durability_state` only to validate it: both
members were accepted, the discriminator was discarded, and every answer became a confirmed `just sent`
row with the draft cleared. D17 clauses 4 and 7 and the client-acknowledgement law in `SPEC.md` say the
opposite about one of those members — a `202`/`durability_pending` answer is explicitly *non-accepted*, stays
visibly unsent, and is safely replayable under the same command key. The answer carries the same message
identity, position and timestamp the accepted one does, so nothing but the discriminator distinguishes a
recorded message from one the record has not promised to keep. This entry records the cure and supersedes
only the two D44 clauses it changes; D41, D42, D22, D23, D31, CT-I1-005 and CT-I2-005 are unchanged.

1. **Three answers, three renderings.** An accepted answer draws the message row, marked `just sent`, and
   clears the box. A non-accepted answer draws no row at all: the typed words stay in the field, the line
   under the box says the server has not confirmed the message, and the button offers `Retry` rather than
   `Send`. A terminal problem document renders its own validated human `detail` and hands the words back.
   No control on this boundary projects an unaccepted command as record truth.
2. **The browser carries one more value, and it is not authority.** This supersedes D44 clause 1's
   "submits exactly one value: the message text" only. The browser also returns the answer it last
   received, and the server reads exactly one field out of it: the command identity of a send the record
   answered without accepting. That identity names a command; it claims nothing. The API re-authorizes
   every attempt from the server-held bearer, exact replay returns that command's original outcome, and a
   same-key different request is refused as a conflict. It is read strictly — a value that is not a UUID
   is refused before any read or command is made. The browser still receives no bearer, session, CSRF
   token, credential, actor, project, scope, custody, or authorization claim, the recipient is still
   resolved server-side, and the request body is still exactly `{"text","thread_id","to"}`.
3. **A retry of an unconfirmed send reuses its identity; an edit mints a new one.** This supersedes D44
   clause 2's minting sentence only. One `Idempotency-Key` is minted before the first attempt, reused by
   every bounded transport retry, *and* reused when the sender presses the box again on a message the
   record has not confirmed — retrying that message under a fresh identity would ask the record to keep
   two copies of it. Editing the words first makes it a different request, so it is a different command
   with a new identity: one key for two different requests is a conflict, not a retry.
4. **The one suite proves the non-accepted half too.** The `dogfood-inbox-controls` suite already proved
   that an accepted message appears without a reload; it now also submits on a thread the local stub
   answers `202` for, and proves at each width that no row is drawn, the draft survives, the sentence is
   on screen, and pressing the box again reaches the record under the same key. The transport fixture
   carried only an `accepted` response before this, so the otherwise-green suite could not fail. No second
   suite is registered and no other suite changes status.
5. **What this still withholds.** It adds no origin-scoped draft persistence: closing or reloading the
   document discards an unconfirmed draft and its identity, and the next send mints a new one. `SPEC.md`
   assigns that persistence to the product browser command path, which stays deferred to `CT-I2-005`; on
   this boundary the guarantee is bounded by one document's lifetime, and after a reload the screen still
   says only what the record says — the message is absent, not shown as sent. It grants no new command,
   contract, role, capability flag, product route, or deployment promise.

Rejected alternatives:

- Drawing the unconfirmed message as a greyed-out row with a `not confirmed` chip. It is the same row
  component the accepted state uses, in the place a reader has learned holds recorded messages, and it
  reduces "this may not exist" to a chip somebody has to notice. The words are the same information kept
  where the sender can act on them.
- Clearing the box and holding the draft only in server state until the sender asks for it back. The
  draft in the field *is* the retry affordance; a message nobody can see is a message nobody will retry.
- Minting a new identity on every press. That asks the record to keep two copies of one message whenever
  the first attempt did commit, which is the duplicate this whole path exists to prevent.
- Treating `202` as one more retryable status inside the bounded transport loop. It is not transport
  noise; it is the record's own answer about durability, the acknowledgement can outlast any client
  deadline, and retrying inside the loop would hide the one state the operator has to see.

## D46 — First-class operator Requests replace the ledger and its Request-facing direct-intake assumptions (locked 2026-08-09, operator R2903, gh#399)

The operator accepted the shape in [`docs/specs/operator-requests.md`](docs/specs/operator-requests.md)
after PR #398's independent exact-candidate review and the R2903 `GO`. `SPEC.md` 1.19 incorporates that
contract as `INV-81..87` and `AC-REQ-01..08`. This is Phase 0 governance only: it authorizes no product code,
endpoint, allocator, import command, UI control, adapter, credential, egress, or writer epoch by itself.

1. **Request is a distinct Work aggregate.** It owns captured intent and outcome accountability, has UUIDv7
   identity plus a permanent tenant-wide `R<number>` operator reference, and may relate to zero or more
   required/optional fulfillment Tickets. Ticket UUIDv7 identity, custody, workflow, Proof, and closure remain
   independent. Request capture and discussion-to-Request promotion never create a Ticket implicitly.
2. **Capture composes the existing authority and durability seams.** The project-seat CLI and private
   server-mediated UI send-box idiom resolve one existing Actor and call one strict `create_request` intake
   action. The atomic Record change includes inbound provenance, Request facts, allocator outcome, command
   result, audit, and outbox; accepted waits for the required off-host acknowledgement. Payloads claim no
   Actor, owner, project authority, priority, triage, relation, closure, or accepted state.
3. **The operator state is derived.** Independent Request triage is
   `UNTRIAGED|ACCEPTED|DUPLICATE|REJECTED`; `NEW|TRIAGED|WIP|BLOCKED|DONE` is a rebuildable read projection
   over current disposition, Ticket relations, blockers, and Proof. It is never a mutable status.
4. **Only the exact Request-ledger cutover earns a bulk path.** After accepted CP3-D evidence and a separately
   accepted portfolio authority epoch, an enforced old-writer fence seals the complete Mission Control
   ledger, advances the allocator past the full high-water, imports the exact open set through one
   operator-authenticated signed-manifest command, reconciles every row/count/sample, and removes both the
   old mutation path and import operation before the first portfolio capture. No Ticket/corpus importer,
   dual writer, proxy, fallback, or second allocator is authorized.
5. **The v1 exact design adds no new trust boundary.** Its two ordinary channels reuse the existing human
   role-binding and machine project-seat planes, private edge, prohibited-data refusal, Record transaction,
   off-host durability, generated clients, and projection seams, so the exact v1 architecture verdict is
   `no-new-boundary`. Slack/Hermes is explicitly outside v1. Before that later phase activates, a new
   append-only security decision must freeze adapter identity/custody, capability, ingress/egress, replay,
   revocation, taint, and limits; the operator must acknowledge it; and an independent CSO must approve the
   exact candidate digest.
6. **Stable work and sequence are closed.** `CT-I1-015` owns the one-candidate Request authority replacement
   and one-way ledger cutover; `CT-I2-011` owns the existing-identity UI channel and contextual Request list;
   `CT-I2-012` is inactive until the Slack/Hermes security dependencies above are accepted. Their named
   tests map every phase criterion. No product behavior is active because these stable IDs exist.

Exact supersession:

- **D27 clause 1 and clause 5** are superseded only for the sealed Mission Control Request ledger and
  OR-06's exact open-set import. Their ordinary-command minimal Ticket carry-forward, read-only provenance,
  and prohibition on a general bulk importer remain in force.
- **D30 clause 2** is superseded only where it says bulk import stays dormant: the Request-only import may
  activate after the same clause's CP3-D and separate-authority-epoch gates pass. Its shadow/co-source and
  no-pre-CP3-D-freeze rules remain in force.
- **D30 clause 4** is superseded only where `capture` was described as necessarily admitting/linking Ticket
  work and requesting initial Commander custody. The same active project grant may capture a Request without
  a Ticket or custody transfer; all server-side scope, revocation, and stricter-authority rules remain.
- **D30 clause 5, as corrected by D36**, is superseded only in its Request-facing assignment of the shared
  `R` counter to `<project>-R<nnn>` Ticket intake source references. After the Request authority epoch,
  `R<number>` is the tenant-wide Request operator reference; Ticket IDs remain instance-global UUIDv7 and
  source aliases remain separate project-scoped provenance. D36's UUIDv7 correction is preserved.

D39 clause 1's current GitLab Issue-to-Ticket product path, D40's notification mirror, and D41 clause 1's
existing Inbox create/link-Ticket promotion are not Request capture channels and are not silently repurposed
or removed by this decision. A provider or Inbox path joins Request authority only through its own activated
stable ticket and unchanged Request conformance contract; in particular, Slack/Hermes must pass clause 5.

Rejected alternatives:

- Treating Request as a Ticket alias, shadow pair, Inbox thread, workflow stage, Board row, or source
  reference. Each collapses intent accountability into execution or projection state and recreates direct
  intake under a new noun.
- Keeping Mission Control's JSONL writer as a fallback, proxy, dual writer, allocator, or recovery source.
  The 2026-08-09 loss/reissue class is killed only when accepted identity is server-held and cutover is
  one-way.
- Reusing the v1 `no-new-boundary` verdict for Slack/Hermes. That phase introduces adapter identity and
  credential custody outside the accepted planes and always requires the later security decision and CSO.
- Rewriting D27, D30, D36, D39, D40, or D41 in place. This ledger is append-only; the exact clauses above
  are superseded here and every unaffected clause remains readable history.

## D47 — Phase 0 changes governance artifacts, not product implementation (2026-08-09, PR #406 review)

The independent Terra review of PR #406 at candidate `1156b32251650df512e038ac032ae88fccd02836`
(`2026-08-09_2327--review-406-terra--governance-chain.status.md`) found one P1 contradiction: the accepted
Phase-0 clause prohibited generated-file changes even though the same canonical SPEC revision necessarily
regenerated the machine-owned SPEC digest in `generated/.generated-manifest.json` and extended the
acceptance-criterion ownership/denominator fixture for `AC-REQ-01..08`. The candidate could not truthfully
satisfy its own acceptance text.

This entry preserves D46 and supersedes only that Phase-0 change-set description. Phase 0 changes no product
implementation and authorizes no product behavior. Its exact work is the subordinate Request specification,
canonical adoption documents, and the deterministic generated traceability metadata and acceptance-criterion
ownership/denominator fixture required to keep that SPEC revision internally verifiable. Those generated and
test-fixture updates are governance traceability/ownership artifacts, not product implementation, and omitting
them would make the canonical revision drift from its manifest or acceptance denominator. `SPEC.md` 1.20 and
the amended Phase-0 acceptance clause carry this clarification in the same candidate. Every other D46 scope,
dependency, security gate, and no-product-activation statement remains unchanged.

Rejected alternatives:

- Leaving the generated manifest or acceptance denominator stale to satisfy the literal old clause. That
  would pass prose by breaking deterministic traceability and the repository's verification contract.
- Editing D46 in place. Accepted decisions remain append-only history and are superseded by a later entry.
- Treating governance regeneration as permission for product code, contracts, endpoints, runtime behavior,
  or compatibility work. Phase 0 remains canonical adoption only.

## D48 — A failed Request cutover stays fenced in `prepared`; it does not invent quarantine disposition (engineering, 2026-08-10, PR #412 round 1)

The first Request authority candidate declared a `quarantined` epoch state and migration event but provided
no command that could write either. Independent review correctly found that the contract promised a state
transition the product could never make. This entry supersedes only D46's inherited OR-06 failure wording;
the one-way fence, denominator, reconciliation, durability, and no-rollback requirements remain unchanged.

1. A drift or reconciliation mismatch persists its exact typed refused command result and leaves the epoch
   in `prepared`. That state is already fail-closed for every native Request mutation and import completion.
2. The epoch state machine has exactly `prepared -> completed`. It does not infer an operator disposition
   from a failed command, and therefore exposes no unwritten `quarantined` state or event.
3. Recovery is a new, separately authorized cutover decision or forward compensation while the old writer
   remains fenced. Rollback never re-enables it, and no client, projection, or local ledger repairs Record.

Rejected alternatives:

- Keeping dead schema/event members as a promise to add a writer later. The candidate must be complete now.
- Automatically quarantining on every refusal. Input, transient durability, and operator mistakes are not
  equivalent dispositions, and a trigger cannot honestly decide among them.
- Re-enabling native or legacy capture after failure. That recreates the split-brain window OR-06 removes.

## D49 — Agreements are immutable Ruling facts written by existing project seats (engineering, 2026-08-10, issue #401)

The Agreements ledger records a dated operator agreement without turning prose into mutable configuration
or introducing another identity plane.

1. Work owns one `Ruling` append policy and accepted-only read Interface. Record owns its canonical
   `ruling.recorded` event, command result, outbox, durability, and transaction.
2. A Ruling receives server time and UUIDv7 identity. Its operator words are encoded once as UTF-8 and
   stored byte-exact with a SHA-256 digest. Database `UPDATE` and `DELETE` use the accepted immutable
   control-fact refusal trigger.
3. The authenticated active project seat supplies tenant, Project, principal, and seat. The strict body
   contains only `verbatim` and an optional predecessor UUID. Unknown or non-seat identity refuses by
   stable code and cannot create a principal, mapping, alias, or grant.
4. A correction is a new same-Project Ruling that points old-to-new through `supersedes_ruling_id`; accepted
   reads derive the reverse citation and permit at most one successor. The prior words remain unchanged.
5. Listing and citation reads expose only off-host-accepted facts, deterministic server-date/ID order, and
   explicit requested/answered/unanswered Project scope plus the Record watermark.
6. V1 reuses the existing generated HTTP/client, encrypted spool, protected CLI, project-seat credential,
   PostgreSQL, and telemetry boundaries. The exact design records `no-new-boundary`; adding any adapter,
   principal class, credential custody path, ingress, egress, or browser authority requires a new decision
   and CSO review.

Rejected alternatives:

- Editing the old agreement in place. That destroys the exact words and citation history relied on by later
  reasoning.
- Letting callers name a Project or identity. Authentication already resolves the authoritative seat and a
  claimed value would create an impersonation/confused-deputy surface.
- Reusing Request or Ticket identity. Agreements are facts about decisions, not captured intent or
  executable work, and their stable citations must remain semantically distinct.
- Adding a generic principal, policy, or document abstraction. The existing seat domain and one cohesive
  ledger fully meet the current requirement.

## D50 — Decision briefs are Request-record projections answered by linked Rulings (engineering, 2026-08-10, issue #403)

Operator decision asks must be complete without allowing a caller, model, or digest renderer to invent the
facts presented for judgment.

1. The latest accepted active Request blocker with the exact key `operator-decision-required` marks one
   decision. No separate Decision aggregate or mutable brief record is added.
2. The accepted Request read builds the full brief from Request facts: a fixed plain ELI, the exact Request
   content as origin, three fixed outcome choices with bounded completeness scores, a recommendation chosen
   from accepted triage with its reason, and a fixed safe default with its reason. It also returns one
   ready-to-send rendering.
3. Request and query payloads have no fields for ELI, choices, scores, recommendation, safe default, or
   rendering. No model call, caller prose, or other call-time fact participates in the projection.
4. An answer is an immutable Ruling whose optional `request_id` is constrained to the same tenant and
   Project and whose root is bound to the exact latest accepted active decision blocker fact. Pending
   Rulings do not resolve accepted state. Accepted reads expose Request-to-Ruling and Ruling-to-Request
   links; every Ruling successor inherits both the Request and decision-occurrence relation.
5. An accepted linked Ruling removes only its exact decision occurrence from derived Request state. A later
   active marker is a new open occurrence that an older Ruling cannot resolve, and an inactive latest marker
   renders no brief. The append-only blocker facts stay intact, and every unrelated blocker keeps its
   authority.
6. The digest layer may consume the rendered brief through its own stable ticket. This decision adds no
   digest behavior, principal class, adapter, ingress, egress, browser authority, or trust boundary and
   records `no-new-boundary`.

Rejected alternatives:

- Accepting caller-authored brief fields. That would let a tainted caller rewrite the issue, choices, or
  recommendation shown to the operator.
- Generating the brief with a model at read time. That would make the same accepted Request render different
  judgment facts and would create an unrecorded source of authority.
- Writing a second Decision record. The Request already owns the need and the Ruling already owns the answer;
  another aggregate would duplicate state and create reconciliation work.
- Coupling digest delivery into this change. The digest has its own work item and consumes this stable read
  shape only after that item is active.

## D51 — The native morning digest is a disposable, epistemically explicit read-model (engineering, 2026-08-10, issue #402)

The morning digest composes existing accepted Request and Ruling facts without creating another authority,
store, scheduler, or delivery transport.

1. One pure kernel fold produces one artifact key for each Europe/Vilnius civil date. Its ordered sections
   are open Requests with the complete record-derived decision brief, the prior civil day's Rulings with
   their typed Request executions, and related Ticket timeline links with current proof counts.
2. Each independent source and rendered section carries `complete|partial|unknown`, a visible count, a
   nullable total, exact unreached scopes, and the relevant source watermark. Unread facts are `UNKNOWN`;
   authoritative absent links are empty; the projection never coerces failure to an empty answer, invents
   linkage, or drops visible rows.
3. The generated operator-only HTTP read and protected CLI text/JSON renderer are the complete ctower
   surface. Artifact identity and digest derive from canonical projection content. Neither route mutates
   Record, stores a projection, or queues a read in the encrypted spool.
4. Delivery remains outside the projection. The scheduled caller sends the exact rendered artifact through
   Mission Control's existing `tools/notify`: durable rail 1 completes first, and the existing authenticated
   bridge attempts rail 2 only where identity resolves. This candidate adds no sender claim, identity,
   adapter, Slack/Hermes path, or new egress.
5. The director alone owns the verified schedule switch and retirement of the interim cron. Shipping this
   read-model neither changes nor disables that schedule.

Rejected alternatives:

- Persisting a daily digest row. Requests, Rulings, Tickets, and Proof remain authority; the digest is
  reproducible disposable presentation.
- Treating a failed source as an empty section. That creates false calm and violates the portfolio
  projection's accepted epistemic rule.
- Matching Ruling prose to Request text. Executions require the accepted typed Request relation; semantic
  similarity is not an authority fact.
- Adding a transport or scheduler inside ctower. Existing notification rails and director-owned scheduling
  already supply those responsibilities without widening the trust boundary.

## D52 — GitHub Issues is the second narrow connector through the frozen Phase-1 seam (engineering, 2026-08-10, issue #429)

This decision supersedes only D39's GitLab-only provider scope and D43's deferral of GitHub product behavior.
D39's narrow issue-to-ticket/proof-close behavior and D43's provider-neutral authority split remain binding.

1. One statically registered GitHub Issues provider may poll one selected repository through the unchanged
   two-method connector Interface. The kernel authority, persistence schema, control worker, and shared
   conformance harness remain frozen; no webhook, pull request, dynamic provider, or public connector surface
   is authorized.
2. Catalog holds only a deployment private-key reference and non-secret App, installation, repository, and
   binding-revision identifiers. The trusted API composition path resolves the key only while signing an
   RS256 App JWT and caches only an opaque, short-lived installation token in process memory.
3. Token minting explicitly selects the immutable repository ID with exactly Issues write and Metadata read.
   GitHub egress is pinned to HTTPS `api.github.com:443`; redirects, destination drift, broader grants,
   unsupported auth, and webhook ingress fail closed.
4. Rotation changes the binding revision and invalidates cached tokens without old-key reuse. Revocation
   invalidates cache before the remote drill and leaves authentication closed. Secret-tainted values never
   reach observable output.
5. External identity is `github:<repository_id>:<issue_number>`. Repository rename does not change custody;
   pull requests are excluded; equal timestamps order by immutable issue ID; proof-gated comment and close
   reconcile through the existing exactly-once connector authority.

Rejected alternatives:

- Storing a standing installation token or private key in Catalog. Both violate reference-only custody.
- Adding GitHub branches to kernel connector authority. The accepted Phase-1 seam already admits the provider.
- Using webhooks or following provider redirects. Neither is needed for the narrow polling scope and both
  widen ingress or credential-egress exposure.
