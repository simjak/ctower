# First-class operator Requests specification

| Field | Value |
|---|---|
| Status | Proposed; specification only; no product behavior is authorized |
| Contract | [GitHub issue #397](https://github.com/simjak/ctower/issues/397) |
| Review gate | Independent cross-model architecture review of the exact candidate; CSO review only when the trigger test below fires |
| Engineering-manager model | GPT-5 (Codex runtime, high reasoning) |

This document is a subordinate proposal. It does not override the canonical
[system specification](https://github.com/simjak/ctower/blob/main/SPEC.md), append-only
[decision log](https://github.com/simjak/ctower/blob/main/DECISIONS.md), derived
[architecture atlas](https://github.com/simjak/ctower/blob/main/ARCHITECTURE.md), or non-normative
[implementation roadmap](https://github.com/simjak/ctower/blob/main/IMPLEMENTATION-ROADMAP.md). Before any implementation ticket activates, the
canonical specification must accept this aggregate and its invariants, an append-only decision must supersede
the current direct-intake assumptions, and the atlas and roadmap must be repaired to agree. Issue #397
authorizes this specification, not product code.

## Plain-language outcome

An operator can write a request once and immediately receive an honest answer about whether ctower has it.
The request gets its own permanent `R` number, can later fan out into zero or more execution Tickets, and
remains visible until its outcome is proven. Capture never waits for analysis, triage, or Ticket creation.
Accepted requests survive loss of the ctower host because they are server records acknowledged from a
separate failure domain, not uncommitted lines in a checkout.

## Current reality and scope

Today Mission Control's `tools/req` appends versions to `state/requests.jsonl`, allocates the next shared
`R` number by scanning that file, and renders `NEW|TRIAGED|WIP|BLOCKED|DONE`. ctower already has the useful
lower layers: strict intake and promotion operations, idempotent commands, project-scoped Actor authority,
atomic Record commits, off-host durability states, and read-only Board projections. Its current intake action,
however, creates or links a Ticket directly. ctower has no Request aggregate, Request number allocator,
Request-to-Ticket relation, Request closure rule, or Request list. Those are **NEW in #397**.

[Issue #95](https://github.com/simjak/ctower/issues/95) is the delivery warning: an adapter file or successful
unit call is not a wired channel. Each channel below must prove the real caller reaches ctower and receives an
exactly equal typed outcome. [Issue #185](https://github.com/simjak/ctower/issues/185) is the topology prior
art: one tenant/database holds configured projects with project-scoped principals and views; neither Request
storage nor migration may branch on today's project names.

This specification adds only:

1. one Work-owned, Record-persisted `Request` aggregate and its append-only facts;
2. one `create_request` action on the existing intake submit/promote rail;
3. Request triage, ownership, priority, relation, outcome, and closure commands on existing authority seams;
4. one Request read model in the existing Board/portfolio context; and
5. one bounded import and cutover from the current Mission Control ledger.

It does not add a service, primary surface, identity system, record client, provider, runtime behavior,
connector framework, compatibility API, dual writer, or shadow Request/Ticket pair. Work owns Request
semantics; Record owns atomic storage; Access resolves authority; the existing API and generated-client seams
carry strict payloads; TypeScript remains browser-only. Kernel authority still cannot import apps, providers,
web, CLI, bridge code, or record-tier clients.

## Logical model

```text
authenticated Actor + project + text + idempotency key
  -> inbound thread/event (transport and provenance)
  -> exactly one Request (intent and outcome accountability)
       -> zero or more required/optional fulfillment Ticket relations
       -> append-only triage, priority, owner, blocker, and closure facts
  -> Board/portfolio Request projection (read only)
```

`Request` is not a Ticket, inbox thread, workflow stage, Board row, or source alias. Its canonical identity is
a UUIDv7. Its operator reference is `R<positive integer>`. It records tenant, immutable project, content and
content digest, source/provenance, submitting Actor, current accountable-owner derivation, triage and priority
facts, Ticket relations, blockers, closure evaluations, event position, and durability state. Large or
sensitive bytes remain references; prohibited classes are refused before authoritative mutation.

The server derives the initial accountable owner from the resolved Actor when that Actor is an addressable
principal in the project; otherwise it assigns the project's Commander. A caller cannot claim submitter or
owner in a normal capture payload. Later owner assignment is an authorized append-only fact. The Request owner
is accountable for decomposition and outcome; the project Commander owns triage disposition and its Attention
finding. A Ticket's independent custodian remains accountable for that Ticket's execution.

A Request may have zero or more Tickets. Relations are append-only facts with `required|optional` purpose and
their own active interval. A fulfillment Ticket belongs to at most one accepted Request. Duplicate Requests
point to one same-project canonical Request instead of sharing its Tickets. Inbox remains transport: an
inbound event can be captured as discussion and promoted exactly once to a Request, or captured directly as a
Request in the same act. Request capture never creates a Ticket implicitly.

### Independent triage and derived operator state

Request triage is exactly `UNTRIAGED|ACCEPTED|DUPLICATE|REJECTED`, independent of priority and operator state.
Capture appends the current `P2` safety default, `UNTRIAGED`, and one unresolved Commander-owned
`request_triage_required` Attention finding. Only the project Commander disposes it:

- `ACCEPTED` requires a later priority assignment by a Commander or operator;
- `DUPLICATE` requires a reason and a non-self same-project relation to one non-`DUPLICATE` canonical Request;
  the target disposition is immutable, so the relation is acyclic by construction; and
- `REJECTED` requires a reason.

The Request list derives, rather than accepts, `NEW|TRIAGED|WIP|BLOCKED|DONE` in this precedence order:

1. `DONE` when the latest closure evaluation is valid for the current disposition, relation set, blockers,
   and evidence digest;
2. `BLOCKED` when a current Request blocker or required-Ticket blocker prevents the next outcome;
3. `WIP` when the Request is `ACCEPTED` and a required Ticket is actively executing or under review;
4. `TRIAGED` when a non-`UNTRIAGED` disposition exists but no higher state applies; and
5. `NEW` otherwise.

For `ACCEPTED`, closure requires a nonempty required-Ticket set and every required Ticket closed with current
Project success proof and no unresolved applicable blocker. A duplicate closes only when its canonical Request
is closed. A rejection closes on the authenticated Commander disposition and its reason; it does not fabricate
Project success. Any later relation, blocker, proof invalidation, or canonical-Request change invalidates the
prior evaluation, so a rebuilt projection may honestly move out of `DONE`. No mutable status field exists.

## Seven binding invariants

### 1. OR-01 — Capture is one act, capture-before-analysis, and burst-safe

**NEW in #397; composes with merged intake and durability seams.** An authorized project context, nonempty
text, and idempotency key are sufficient to capture a Request. Title, triage, analysis, priority decision,
owner choice, relation, Ticket, and Board refresh are not preconditions. The server validates project authority
and prohibited data, reserves the idempotency outcome, allocates the Request UUIDv7 and next tenant-wide
`R` number, and commits the inbound event, Request facts, source alias, command result, audit event, and outbox
as one accepted authority change. Analysis, triage, Ticket planning, and projection work happen after capture.

The allocator is a server-side Postgres sequence shared by every project in the tenant. Parallel distinct keys
receive distinct Requests and numbers; replay of one key and digest returns the exact original result; reuse of
the key with another digest refuses. Sequence gaps are allowed, but reuse and renumbering are not. The capture
critical path contains only bounded validation, the Record transaction, and the durability acknowledgement,
not model work, provider calls, Git, or projection catch-up.

The strict capture contract has a discriminated source. Native CLI/UI capture sends `source.kind=native` and
no source reference; the server derives the immutable alias from tenant, resolved Actor principal, and
idempotency key. Exact replay therefore resolves the same alias and a different digest still refuses. Only an
authenticated adapter/import capability may send `source.kind=external` with bounded kind/reference
provenance; Work binds it to the server-resolved Actor and project before reserving the globally unique source
alias. Browser text, provider identity, and caller-chosen native references never become source authority.

An accepted response names Request UUID, `R` reference, project, Record position, and `accepted`. Under the
cutover-RPO0 policy it is returned only after the commit has received the required external-failure-domain
durable acknowledgement. A server-observed off-host acknowledgement timeout returns `durability_pending`, not
success: the Request is excluded from effects and accepted projections and replay under the same key is safe.
A client transport timeout or disconnect may return no typed result at all and remains ambiguous; the UI keeps
the draft and the CLI/import spool keeps the encrypted entry, then reconciles/replays the same key. Editing
creates a new key. Neither client may display pending or no-response ambiguity as accepted.

### 2. OR-02 — Request owns intent; Ticket owns executable work

**NEW in #397; composes with merged thread-first intake, exactly-one promotion, and #381 triage.** There is no
1:1 Request/Ticket shadow and no automatic Ticket creation. Direct Request capture is the `create_request`
intake intent; a discussion event may be promoted exactly once to that intent. A Request stays valid with zero
Tickets while it awaits triage or decomposition and may later relate to multiple required or optional Tickets.
Ticket identity, custody, workflow, priority, Proof, and close authority remain unchanged.

Request triage uses the independent `UNTRIAGED|ACCEPTED|DUPLICATE|REJECTED` axis already specified for
connector intake, but applies it to Request rather than Ticket. Commander disposition, post-intake priority,
untriaged visibility, and Attention ownership follow the same authority shape. Ticket creation from an accepted
Request is a separate, explicit command; linking an existing Ticket requires same-tenant, same-project
authorization and expected versions on both subjects.

### 3. OR-03 — Request numbers and Ticket identities never collide

**NEW in #397; supersedes the Request-facing part of current `INV-71` while preserving UUIDv7 Tickets.** A
Request's canonical ID is UUIDv7 and its display reference is unique on `(tenant_id, r_number)`. The `R`
sequence is tenant-wide and project-independent, matching the one shared counter being replaced. Ticket IDs
remain instance-global UUIDv7 and never use, parse, or derive authority from `R` references.

At migration freeze, the allocator is advanced past the maximum `R` number in the entire sealed source ledger,
not merely the open subset. Imported Requests keep their original `R` labels, while the immutable source alias
also keeps `<project>-R<nnn>`. A duplicate label or source alias aborts reconciliation; an importer never
remints the row under a fresh `R` number. The R2848/R2896 reissue episode is therefore structurally impossible:
concurrent writers cannot scan stale checkout state, and recovery cannot make a previously issued number
available again.

Mission Control remains the sole portfolio `R` allocator until the OR-06 authority epoch. Before that epoch,
ctower Request capture is exercised only in a disposable verification tenant whose references have no
portfolio authority; no production Request endpoint, grant, spool drain, adapter, or UI control is present or
accepted. The cutover run enforces the old-writer fence, seals its high-water, advances the ctower allocator,
and imports and reconciles the open set; the authority epoch re-proves those facts and only then admits the
first portfolio capture. There is never an interval with two portfolio allocators or an inactive production
path waiting on a switch.

### 4. OR-04 — Accepted Request authority is server-held and recoverable

**NEW in #397; composes with merged Record transactions, cutover-RPO0, backup, and restore rules.** On
2026-08-09 at 12:45 EEST, `state/requests.jsonl` on origin and every working tree ended at R2845. The 89
uncommitted append-only rows carrying R2846 through R2893 had lived for two days in a shared checkout and
disappeared when autostashes were dropped. The only surviving copy was dropped stash object `f2b2179c`, from
which the rows were recovered with `git cat-file`; three collided reissues then had to receive R2894, R2895,
and R2896. At 13:10 EEST Git history proved that no commit had deleted the rows: they had never entered Git
history. Per-append commits reduce that tool's risk but do not make a checkout a record system.

The killing invariant is: **an accepted Request and its permanent `R` number never depend on a working tree,
Git commit, branch, push, stash, local JSONL file, client spool, or projection for existence or recovery.** They
exist only from the atomic server Record transaction plus the required off-host durable acknowledgement.

The Request event stream, number, source aliases, command outcomes, owner/triage/priority/relation/closure
facts, audit anchors, and projection positions are included in encrypted Postgres backup and signed restore
inventories. A restore in an effect-disabled isolated network must validate event chains, anchors, objects,
expected sources, allocator high-water, unique Request/source aliases, and a full projection rebuild before
reads are trusted. It then reconciles every accepted command and latest Request digest against the signed
inventory. Missing, gapped, duplicated, or unverifiable state fails closed and stays quarantined; silence,
client data, or a Board row cannot repair Record truth.

### 5. OR-05 — Every capture channel resolves one server Actor

**NEW in #397; composes with merged `INV-69`, `INV-70`, `INV-73`, generated clients, and protected spools.**
All ordinary capture channels call the same strict Request intake command and receive the same durability
states. The one-time migration bridge first uses that inbound rail, then the manifest-bound import operation
in OR-06 solely to carry frozen identity and state. No channel may claim Actor, submitter, owner, project grant,
or accepted state.

| Channel | Identity custody and pending behavior |
|---|---|
| Seat CLI | A protected project-seat bearer resolves one machine-plane Actor and version-pinned project grant server-side. The grant supplies project scope and capability; the payload supplies text and a client key. The encrypted spool retains pending commands and replays the same key. |
| UI send box | The private HTTPS edge resolves one human Actor from the existing OIDC session, human-role binding, and same-origin CSRF check. The browser holds no bearer or owner claim. A project selector is only a request for server authorization. Pending keeps the text, names the uncertainty, and retries the same key. |
| Mission Control import bridge | The bridge submits the source event as its configured Commander Actor and promotes it to Request as its configured operator Actor, matching the accepted import custody split. Deterministic keys, signed source manifest, and immutable owner provenance make the bridge auditable; it never impersonates the original owner. |
| Slack-originated operator text | No native Slack listener, token, or webhook enters ctower in this scope. The existing Mission Control/Hermes adapter may call the same private Request API as its configured bridge Actor. Slack workspace, user, message, channel, and thread identifiers are `external_untrusted` provenance, not ctower identity or authority. |

CLI, browser, adapter, runner, and import code never connect to Record-tier persistence. A refusal commits only
the ordinary typed command outcome permitted by canonical policy and creates no accepted Request.

The existing Mission Control/Hermes boundary must authenticate its source, enforce timestamp/nonce replay
bounds and strict text limits, exclude attachments in this scope, scan prohibited and hostile content, and
carry structural `external_untrusted` taint into ctower. ctower independently rechecks the adapter's exact
source/project grant, replay key, limits, prohibited classes, and taint. A forged source, replay, oversized
input, or prohibited class refuses before any authoritative or object mutation. Allowed-but-hostile or
structurally untrusted content may be captured for accountability under visible canonical quarantine, but it
cannot enter model analysis, Evidence, Proof, or effects until the canonical promotion policy permits it; it
never executes silently.

#### Request command authority

This feature adds no principal, credential, role, or project-seat scope. Authorization is the intersection of
the existing Actor plane, project, `capture|transition|evidence` grant where applicable, Request state/owner,
and the rules below. “Operator” is the existing portfolio operator authority; “Commander” is the exact
project Commander principal or bound human `commander`; “seat” means a non-Commander project-seat principal.

| Request operation | Exact authority |
|---|---|
| Native/external capture or discussion-to-Request promotion | Operator; matching Commander or seat with `capture`; bound human `operator|commander`; or exact source/project adapter grant. Viewer never. External provenance additionally requires the adapter capability. |
| Project Request read/list | Operator across configured projects with source-level checks; matching project principal with any active named scope; bound human `operator|commander|viewer` for named project keys. Bridge/service receives only its exact command reconciliation result. |
| Priority assignment | Operator; matching Commander with `transition`; or bound human `operator|commander`. Non-Commander seat, viewer, and ordinary bridge/service never. |
| `ACCEPTED|DUPLICATE|REJECTED` triage disposition | Matching project Commander with `transition` or bound human `commander` only. The manifest-bound import command below is a distinct operator authority, not triage impersonation. |
| Accountable-owner assignment | Operator protected placement or bound human project Commander. Project-seat scopes, viewer, caller payloads, and ordinary bridge/service never grant owner authority. |
| Create/link fulfillment Ticket | Existing Ticket capture authority plus Request `transition`; a non-Commander seat must also be the current Request owner. Both subjects must be same tenant/project and expected-version current. |
| Request blocker or closure evaluation | Operator; matching Commander with `transition`; bound human `operator|commander`; or current Request-owner seat with `transition`. The command requests evaluation; Record/Proof facts alone decide derived state. |
| Signed migration import | Operator only, bound to one accepted authority epoch, exact signed manifest/row digest, source inbound-event version, and unused deterministic operation key. Every other caller and every post-cutover call refuses. |

Missing, ambiguous, revoked, foreign-project, stale-version, wrong-state, or wrong-role authority refuses as
`project-scope-denied`, `request-capture-forbidden`, `request-transition-forbidden`,
`request-triage-forbidden`, `request-owner-forbidden`, `request-source-forbidden`, or
`request-import-forbidden`, as applicable, with zero Request/event/outbox mutation and zero foreign disclosure.
Ordinary capture and promotion schemas reject caller-supplied `r_number`, owner, triage, priority decision,
blocker, relation, and closure fields.

### 6. OR-06 — Cutover imports exactly the frozen open set, then removes the old writer

**NEW in #397; adapts the merged manibo import recipe but creates Requests, not Tickets.** Bulk migration stays
dormant until accepted CP3-D evidence and a separately accepted portfolio authority epoch permit it. The
current observed ledger count is diagnostic, never a migration denominator. The denominator is derived once
from the signed freeze artifact.

The cutover procedure is exact:

1. Validate the complete append lineage before selecting latest rows: each `R` has one creation lineage, every
   later row causally extends the prior history under the current schema, identity-bearing fields do not
   diverge, and project follows at most its authorized unbound-to-one-project transition. A second creation,
   truncated/forked history, collision, or inconsistent identity is quarantined and blocks cutover. Then prove
   every latest open row has one explicit configured project and reviewed owner mapping. Repair source facts by
   append-only updates before fencing; the importer never guesses.
2. Install an enforced, fail-closed source-writer fence before reading the denominator: stop all callers, make
   every `tools/req` mutator refuse, and place the exact ledger under an operator-controlled read-only
   filesystem boundary whose unknown state blocks progress. Only then hash/archive the complete JSONL bytes and
   sign a manifest containing source identity/digest, lineage proof, maximum `R`, exact open-ID set, per-row
   latest digest, status, project, owner, timestamps, and relationship data. Continuously recheck fence state,
   file identity, size, digest, and high-water at every batch and again at the authority epoch; any change aborts
   and quarantines the run.
3. Map each source owner to exactly one existing principal in that same project in a reviewed manifest, and
   preserve the source owner string as an immutable alias on that mapping. A missing, ambiguous, foreign-project,
   or inactive mapping blocks cutover. Provision or repair the canonical principal before a new freeze; never
   normalize, invent, or replace an owner with the Commander.
4. Advance the server sequence past the manifest's full-ledger maximum. Process strict serial batches of at
   most 25 rows. A deterministic UUIDv5 command key binds source digest, source identity, operation, and
   attempt. For each row the bridge submits discussion as its configured Commander, then invokes one dedicated
   signed-manifest import command as the portfolio Operator. That command alone may bind the original `R` and
   atomically create the Request with reviewed owner, priority/triage/blocker translation, original-owner
   provenance, source alias, command result, audit event, and outbox. It never impersonates the mapped owner and
   creates no Ticket. Any refusal or ambiguous result stops the batch and reconciles by the same operation
   key/source alias before retry. The import command is absent from ordinary schemas, refuses outside the exact
   epoch/manifest, and is removed with the cutover release after its audit result is sealed.
5. At every batch boundary prove that batch's frozen source delta and the cumulative frozen prefix through that
   batch each equal their accepted imported Request and distinct source-alias counts, including the same
   equalities per project. Also reconcile every processed source ID—not a sample—against exactly one Request
   UUID/source alias and compare `R`, project, resolved owner plus original-owner digest, content digest, mapped
   status facts, durability, and absence of an implicit Ticket. At completion prove the full frozen open
   denominator and every row. Require healthy spool state and a caught-up Board watermark.
6. Select a deterministic, manifest-seeded random sample of three Requests per batch (or every Request when
   the batch has fewer than three) as an independent check of the full reconciliation. Through the scoped
   public read, compare durability `accepted`, Request UUID and `R`, source alias, project, owner
   mapping/provenance, text digest, triage/state, timestamps, relations, and absence of an implicit Ticket.
   Record the proof with the batch manifest.
7. After complete count, full-row reconciliation, spot-check proof, and a final unchanged fence/digest/high-water
   proof, verify/remove the already-refusing Mission Control mutation entrypoints and activate ctower capture
   for the seat CLI and every then-existing adapter/automation caller in the same authority epoch. Later
   channels join ctower directly; none ever joins the sealed writer. Do not leave a proxy, fallback, dual write,
   import operation, or second allocator. Rollback restores ctower from its signed server backup and keeps
   capture unavailable or safely spooled; it never re-enables the old writer.

The manifest preserves the source status but does not grant it authority. `NEW` maps to `UNTRIAGED`. `TRIAGED`
maps to `ACCEPTED` only with a reviewed post-intake priority fact. `BLOCKED` maps to `ACCEPTED` plus an explicit
Request blocker and its source reason. `WIP` maps to `ACCEPTED` and derives `WIP` only when the manifest binds a
current same-project required Ticket that is actually active; otherwise it honestly projects `TRIAGED` with a
Commander-owned `request_execution_link_required` Attention finding. Relationship bytes are preserved in the
manifest. Relationship mapping is closed: `refines` is applied in a deferred expected-version pass only after
all target aliases exist and only for a same-project, non-self, acyclic target; `part-of-thread` becomes inbound
thread provenance rather than a Request relation; `merged-into|superseded-by` on a latest open row is an
inconsistent terminal lineage and blocks; and an unknown relationship kind blocks. A missing/closed or
foreign-project `refines` target remains signed source provenance with an explicit Attention finding rather
than becoming authority. Full-row reconciliation runs again after the deferred relation pass.

The complete sealed JSONL bytes remain under Mission Control's existing restricted archive custody and
retention; they are not copied into ctower Record, backups, objects, or migration artifacts. ctower stores only
allowed Request fields, the signed manifest's non-sensitive metadata/digests, and an external archive reference.
The full history is scanned before manifest acceptance; a prohibited historical byte remains only in the
restricted source archive and cannot be copied into a manifest field, Request, Evidence, log, or proof artifact.

The all-project count and sample include manibo rather than treating it specially. Project-specific names are
configured data; the migration algorithm has no project branches.

### 7. OR-07 — The operator list is a read-only, epistemically honest Board projection

**NEW in #397; composes with the merged #385 portfolio projection rules.** Requests appear as contextual
content in the existing Board/portfolio surface, not a sixth primary surface. The list shows `R` reference,
project, derived operator state, triage, accountable owner, current priority/default marker, age, required and
optional Ticket links, proof coverage, blocker, durability/freshness, and source kind. It supports project,
state, triage, and owner filtering/grouping. It has no status editor, projection repair control, local override,
or client-side authority inference; contextual authorized commands call Work through the server.

The #385 epistemic rules bind:

- an unread, unreachable, stale, or unauthorized project is not an empty project and contributes neither zero
  nor a fabricated row to totals;
- portfolio totals state `N/M projects answered` and aggregate only answered projects;
- a Request belongs to a project only through its immutable Record project fact, never text, owner spelling,
  source label, Ticket title, or current filter;
- unlinked, blocked, unknown, and durability-pending are distinct; unknown values render as a dash with an
  exact reason and freshness, never zero or `DONE`; and
- accepted rows rebuild solely from Record events at a named watermark. Pending commands may appear only in a
  separate local pending affordance and never in authoritative counts.

## Security boundary and CSO trigger test

The selected design adds **no new trust boundary**. It adds a Work aggregate and strict commands behind the
existing private HTTPS edge, one-Actor request rule, human OIDC/session/CSRF plane, machine project-seat bearer
plane, project grants, prohibited-data refusal, Record transaction, off-host durability, generated clients,
and read-only projection seams. Secrets remain references. The Request body confers no identity, owner,
project, Ticket, Proof, priority, triage, or close authority.

Before activating any build ticket, compare its exact design to this trigger test. Stop and obtain an
append-only security decision plus an independent CSO verdict on the exact candidate if it introduces any of:

- a native Slack webhook/listener, Slack token custody, public ingress, new credential, or new egress;
- a browser bearer, payload-claimed Actor/owner/project authority, or a second identity/custody record;
- a cross-project read beyond an existing operator role binding;
- direct Record persistence from UI, CLI, bridge, runner, connector, or provider code;
- retention of a prohibited data class, secret value, or unbounded external payload; or
- a change to the canonical durability, Record, Proof, protected-effect, or recovery boundary.

If none fires, ordinary independent architecture/security tests record `no-new-boundary` with the exact head;
they do not fabricate a CSO approval requirement.

## Layered delivery and testable acceptance

Each phase ends in a working, releasable layer. A later phase cannot weaken an earlier proof, and no dark path,
feature switch, parallel authority, or unfinished replacement is permitted. Pre-cutover conformance runs in a
disposable verification tenant; no portfolio Request implementation lands before the complete Phase 1
authority replacement is ready to land and activate as one candidate.

### Phase 0 — Canonical adoption; no build

Append a decision accepting Request and superseding direct Request-to-Ticket/source-reference assumptions;
update `SPEC.md`, `ARCHITECTURE.md`, and `IMPLEMENTATION-ROADMAP.md`; run the CSO trigger test; complete the
independent cross-model review; and activate stable CT tickets with explicit dependencies.

Acceptance: the four canonical documents agree; all seven OR invariants have ticket coverage and exact
acceptance tests; no product or generated file changes; canonical checks pass.

### Phase 1 — Smallest end-to-end authority replacement

Add Request facts and number allocation in Work/Record, the `create_request` intake action, strict HTTP
contracts and generated clients, protected CLI capture/read/list/triage/priority/owner/link/closure-evaluation
operations, the external Slack/Hermes adapter call, and the OR-06 import bridge. Reuse the existing transaction,
Actor, idempotency, spool, durability, and refusal seams. Do not land this production path until CP3-D, the
portfolio authority epoch, the signed freeze, import, reconciliation, old-writer fence, and first ctower
capture can complete as one authority-safe candidate.

Acceptance:

- 100 parallel unique captures plus duplicate-key replays yield one Request per unique key, unique permanent
  `R` numbers, exact replay outcomes, and no implicit Tickets;
- injected transaction, ACK, timeout, retry, and restart failures never expose pending as accepted, lose an
  accepted Request, or reuse an `R` number;
- Commander/operator/seat/project authority matrices and prohibited-class tests prove zero unauthorized
  mutation or disclosure;
- relation and closure tests cover zero/one/many Tickets, required/optional changes, blockers, proof
  invalidation, duplicate and rejection outcomes, duplicate self/cycle/race refusal, expected-version races,
  and rebuild equality;
- backup/restore verification reconstructs identical Request streams, allocator high-water, aliases, command
  outcomes, and projections in an isolated effect-disabled environment;
- the signed migration proves exact full/per-project counts, three-request batch samples, source alias and `R`
  uniqueness, exact manifest-bound owner placement, status translation, and zero implicit Tickets; and
- after the one authority epoch, the Mission Control writer refuses, the archive is read-only, the seat CLI and
  each existing adapter reach ctower end to end, and new capture allocates strictly above the sealed high-water.

### Phase 2 — UI channel and Board list

Add the private server-mediated UI send box and contextual Request list on the already-single ctower authority.
Keep the same command and Actor contracts; add no native Slack ingress.

Acceptance:

- CLI, UI, bridge, and Slack-originated adapter fixtures attribute the exact server-resolved Actor and project;
- an end-to-end probe from each real caller reaches the Request command and returns the exact server result,
  so an installed-but-uninvoked adapter fails acceptance;
- every channel proves accepted, pending, same-key replay, changed-draft/new-key, refusal, offline spool, and
  cross-project denial behavior;
- the list passes #385 answered/unanswered, stale, unavailable, unknown, unlinked, total, and rebuild fixtures
  at 375, 768, and 1440 CSS-pixel widths; and
- the exact-head trigger test records `no-new-boundary`, or the phase stays inactive until the triggered
  decision and CSO verdict are accepted.

## Traceability

`NEW` means issue #397 must first be accepted into the canonical documents and implemented by separately
activated stable tickets. Existing citations are composition points, not claims that Request already exists.

| Invariant | Classification | Merged mechanism or required proof |
|---|---|---|
| OR-01 | **NEW #397** | Intake HTTP idempotency/pending/accepted contract `contracts/http/openapi.yaml:191-220`; Work validation `packages/ctower-kernel/src/ctower_kernel/work/intake.py:80-112,128-216`; atomic intake commit `packages/ctower-kernel/src/ctower_kernel/record/_intake_sql.py:170-315`; off-host acceptance `SPEC.md:3748-3749` |
| OR-02 | **NEW #397** | Existing direct Ticket action is intentionally superseded for Requests: `packages/ctower-kernel/src/ctower_kernel/record/_intake_sql.py:502-518,598-650`; promotion contract `contracts/http/openapi.yaml:224-255`; independent triage composition `docs/specs/connectors.md:359-391` |
| OR-03 | **NEW #397** | Current source-reference/Ticket split `SPEC.md:1471`; UUIDv7 Ticket allocation `packages/ctower-kernel/src/ctower_kernel/record/identifiers.py:12-22`; new Request UUID/sequence/high-water and collision tests required |
| OR-04 | **NEW #397** | Record transaction/cutover pending enforcement `packages/ctower-kernel/src/ctower_kernel/record/transaction.py:401-513`; canonical backup/restore contract `SPEC.md:3738-3757`; exact 2026-08-09 Mission Control incident reproduced in OR-04 |
| OR-05 | **NEW #397** | One Actor and project grants `SPEC.md:1469-1473`; protected intake API `contracts/http/openapi.yaml:191-255`; new Request command and channel identity fixtures required |
| OR-06 | **NEW #397** | Current shadow/bulk-import prohibition `SPEC.md:1472`; existing intake source/project guard `packages/ctower-kernel/src/ctower_kernel/work/intake.py:203-216`; new enforced fence, signed freeze, manifest-bound Request import, full-row/count/sample reconciliation, and one-way cutover proofs required |
| OR-07 | **NEW #397** | Existing read-only epistemic fold `apps/ctower-ui/src/read/portfolioProjection.ts:20-46,97-185,229-322`; existing rendering `apps/ctower-ui/src/app/portfolio/page.tsx:85-140`; new Request projection/list and responsive fixtures required |

## Specification acceptance checklist

- [ ] The canonical documents adopt all seven invariants and supersede every conflicting direct-intake rule.
- [ ] Independent cross-model architecture review approves the exact digest.
- [ ] The CSO trigger test is recorded; any triggered boundary has an accepted decision and exact-digest verdict.
- [ ] Stable implementation tickets map every phase criterion to a named test and keep product scope inactive
      until their dependencies are accepted.
- [ ] No compatibility layer, dual writer, source-ledger fallback, second allocator, or sixth surface remains.

## Signed accountability

```text
SIGNED-OFF
  seat: engineer (hard-architecture specification)
  crew: engineer-r2902-requests-spec
  model: GPT-5 (Codex runtime, high reasoning)
  claim: This proposal defines the seven first-class Request invariants, the one-way migration, and testable layered delivery without authorizing product code.
  stood-under: Issue #397; canonical intake, identity, durability, restore, connector-triage, and portfolio-projection contracts; Mission Control's current request tool/import bridge and 2026-08-09 ledger incident.
  if-this-breaks: I own architecture errors or omitted failure modes in this candidate and will repair the subordinate spec before canonical adoption or implementation activation.
```
