# Crew console epic specification

| Field | Value |
|---|---|
| Status | Proposed; specification only; no product behavior is authorized |
| Contract | [GitHub issue #371](https://github.com/simjak/ctower/issues/371) |
| Review gate | Independent CSO approval of the exact candidate digest before any build ticket activates |
| Engineering-manager model | GPT-5 (Codex runtime) |

This document is a subordinate proposal. It does not override the canonical
[system specification](https://github.com/simjak/ctower/blob/main/SPEC.md), append-only
[decision log](https://github.com/simjak/ctower/blob/main/DECISIONS.md), derived
[architecture atlas](https://github.com/simjak/ctower/blob/main/ARCHITECTURE.md), or
non-normative [implementation roadmap](https://github.com/simjak/ctower/blob/main/IMPLEMENTATION-ROADMAP.md).
The canonical specification must accept any new contracts, invariants, acceptance criteria, and active build
tickets before implementation. Issue #371 requests this specification and a CSO verdict; it does not activate
product code.

## Outcome

An authenticated operator can open a contextual console in ctower, find an eligible live engagement by
**project -> seat -> crew**, observe its terminal with explicit freshness and gap state, and later send audited
text or chat without turning tmux, a browser socket, or a transcript into identity or Record truth.

The target environment is ctower's private-VPS deployment behind its existing private HTTPS origin. The
console is contextual content in Fleet and, when a recorded work session is ticket-linked, Ticket detail. It
does not add a sixth primary surface or a top-level `/console` destination.

## Evidence and current reality

- ctower is currently a pre-alpha shadow walking slice. The browser product, runner, live streams, and
  authoritative terminal controls described here are planned behavior, not current availability.
- The fleet substrate is one tmux server selected by `tmux -L mc`; a crew normally maps to an `mc-<crew>`
  session with pane target `<session>:0.0`. The current
  [`bin/mux`](https://github.com/simjak/mission-control/blob/main/bin/mux) owns the tmux syntax for listing,
  reading, logging, sending, and submitting. `send` uses an atomic bracketed paste and currently prepends one
  ASCII space; `submit` separately sends Enter. Its post-paste pane check is explicitly best-effort, not an
  acknowledgement.
- Mission Control has a
  [ttyd bridge precedent](https://github.com/simjak/mission-control/blob/main/tools/_ttyd_bridge.py): read-only
  and writable ttyd processes bind loopback, writable access uses an ephemeral capability path, and its audit
  records bridge lifecycle rather than every injected byte. It is evidence that a bridge is feasible, not an
  acceptable ctower authorization or audit boundary.
- The identity chain comes from the project/seat work in
  [#352](https://github.com/simjak/ctower/issues/352) and canonical `INV-69`, `INV-73`, `INV-75`, and `INV-76`:
  a seat is a durable principal, a crew is one engagement of that seat, a recorded work session is a fact,
  and a tmux name is transport metadata rather than identity.
- Chat must reuse native inbox threads from [#336](https://github.com/simjak/ctower/issues/336), delivery/read
  facts from [#363](https://github.com/simjak/ctower/issues/363), and the pending Mission Control bridge in
  [#355](https://github.com/simjak/ctower/issues/355). Terminal injection is not a chat fallback.
- Terminal input follows the durable effect shape proven by
  [#347](https://github.com/simjak/ctower/issues/347) and
  [#362](https://github.com/simjak/ctower/issues/362): ctower accepts and records intent, an authorized fleet
  adapter consumes it idempotently at the actual boundary, and a receipt records what was observed. A request
  is not a grant, and dispatch is not acknowledgement.
- The operator's standing rule is that nothing agent-facing receives internet exposure before a proven login
  gate. The ruling is recorded in Mission Control's
  [migration status](https://github.com/simjak/mission-control/blob/main/board/ctower-migration-status.md#L349),
  and canonical `CT-I1-013` narrows it further: login, session, and API routes remain private HTTPS reachable
  only across the tailnet, with no public ctower ingress.
- Mission Control's deployed
  [cadence v1.21 rule](https://github.com/simjak/mission-control/blob/main/board/checklists/cadence.md)
  requires every operator-facing serve to bind the configured tailnet address explicitly and uses a recurring
  `ss -tlnp` sweep to detect wildcard listeners, including third-party `docker-proxy` listeners. Phase 1 adopts
  that standing bind rule and sweep as deployment evidence rather than treating configuration prose as proof.

## Scope

This epic specifies:

1. an authorized, read-only terminal viewer with cursor, freshness, disconnect, and gap state;
2. bounded terminal text input and explicit submit, protected by a distinct per-session grant and durable
   audit;
3. session-contextual chat over native inbox delivery/read rails and #355;
4. project -> seat -> crew grouping derived from accepted identity and assignment facts; and
5. the private network, authentication, authorization, audit, transport, recovery, and release gates needed
   to make those capabilities safe.

It deliberately does not specify:

- a sixth primary surface, browser IDE, file explorer, arbitrary shell API, file transfer, session
  spawn/kill/restart, or general remote desktop;
- raw per-key forwarding, arbitrary terminal escape/control sequences, mouse forwarding, or browser-to-tmux
  attachment in the first typed-input increment;
- new custody, principal, project, seat, crew, work-session, chat-thread, or proof authority;
- public ingress, Tailscale Funnel, internet exposure after login, or a second browser authentication flow;
- transcript-derived assignment, completion, delivery, evidence, health, or acknowledgement;
- a ttyd capability URL exposed as the product authorization model;
- dual-written chat and terminal input, legacy fallbacks, or compatibility layers; or
- implementation before stable build tickets and their canonical dependencies are active.

## Identity and grouping

The display hierarchy is a projection, never an authorization shortcut.

| Level | Source of truth | Console use | Never inferred from |
|---|---|---|---|
| Project | Configured Project key and the authenticated Actor's active human role binding | First grouping and mandatory authorization boundary | repository path, tmux name, title, or request payload |
| Seat | Durable principal plus configured seat and assignment facts | Second grouping and accountable identity | crew-name spelling, model, pane title, or process owner |
| Crew | One observed engagement of the seat, with its assignment interval/stamp | Third grouping and operator-facing label | terminal content or a self-report |
| Console session incarnation | A strict reference joining recorded work session or runtime attempt, assignment interval, runner epoch, and backend handle | Exact resource to which view/type grants bind | tmux handle alone or an old session name reused later |

A proposed `ConsoleSessionRef` therefore contains tenant and project keys, seat principal, crew engagement,
assignment key and interval sequence, recorded session or runtime-attempt identity, runner identity and epoch,
and an opaque backend target reference. The backend reference may resolve to `mc-<crew>:0.0` in the first
adapter, but that value never enters a work-session fact and never grants authority. If any join is missing,
ambiguous, stale, foreign-project, or points at a different epoch, discovery shows `STATE_UNKNOWN` or the
request refuses by a stable code. It never guesses from the current tmux list.

The grouping projection may show an observed substrate-only crew before its durable session join exists, but
that row is explicitly **unbound** and offers neither view nor type. No first viewer can claim it.

### Console-visible session fence

A session is console-visible only when all of these facts agree at read time:

1. the durable seat is a non-Commander crew seat with a current assignment and recorded work-session or
   runtime-attempt join;
2. the live tmux session carries an `@project` stamp exactly equal to the durable project key;
3. an append-only `console_session_allowed` fact binds that exact project, seat, crew engagement, assignment
   interval, session incarnation, runner epoch, backend-target digest, and console-policy revision; and
4. no later session, runner, project, or global console revocation fact applies.

Commander-seat sessions are never eligible, even when their `@project` stamp matches and even when the human
opening the console has the `commander` role. The allowlist fact is eligibility, not authority: Access must
still mint an exact view or type grant for the human Actor. A missing, blank, changed, or mismatched
`@project` stamp; an absent or stale allowlist fact; a reused tmux name; a Commander seat; or an incomplete
identity join makes the session absent from console discovery and refuses a direct request. A general Fleet
roster may still show an unbound or `STATE_UNKNOWN` crew, but it exposes no console panel or output. The
adapter rechecks the stamp, allowlist, incarnation, and runner epoch before snapshot/replay and continuously
while streaming; a mismatch revokes the exact session and closes its streams within 5 seconds.

## The new security boundary

### Trust path

```text
private browser
  -> private HTTPS edge + OIDC session/CSRF
  -> Access resolves one Actor and human role binding
  -> project authorization
  -> exact ConsoleSessionRef authorization
  -> ConsoleViewGrant OR ConsoleTypeGrant
  -> durable command/outbox (typing only)
  -> authenticated fleet adapter + current runner epoch
  -> mission-control bin/mux
  -> tmux -L mc pane
```

The browser never connects to ttyd, tmux, the runner, or Mission Control directly. TypeScript only renders
strict generated contracts and submits commands; the trusted Python control plane authenticates, authorizes,
persists, and dispatches. The fleet adapter has no Record client and cannot manufacture grants or audit facts.

Every request first resolves exactly one canonical Actor under `INV-73`. A browser request uses only its
opaque secure session cookie and same-origin CSRF contract. Human project authority remains the one active
human role binding for that plane. Session grants are short-lived capability decisions derived from that
Actor, role binding, policy, and exact resource; they are not a third identity or authority record and confer
no custody, project-seat machine scope, or effect permission.

### Sole grant issuer

Only the trusted Access/control-plane issuer, acting under an operator-approved versioned console policy,
may mint either grant. The browser, runner, fleet adapter, tmux, and Mission Control may not mint, extend, or
transfer one. The adapter's only grant-related control-plane operation is the narrow authenticated admission
operation specified below; it provides neither Record-tier persistence access nor a grant-minting path.

### Distinct grants

`ConsoleViewGrant` and `ConsoleTypeGrant` are separate strict contract variants. Neither implies the other,
and no role receives either by merely existing. A person who needs both must pass both decisions.

Common grant fields are grant ID, Actor/principal and human-role-binding revision, tenant/project, exact
`ConsoleSessionRef` including assignment interval and runner epoch, policy revision, issuer decision,
not-before, absolute expiry, revocation state, maximum uses, and nonce. Payload claims cannot change them.

| Property | View grant | Type grant |
|---|---|---|
| Capability | Open/reconnect one output stream and fetch its bounded replay window | Execute one exact `paste_text` or `submit` command |
| Role floor | Read-authorized human in the exact project; policy may narrow further | Operator or project Commander only; `viewer` always refuses |
| Lifetime | At most 5 minutes; one concurrent stream for the exact grant and Actor/session/incarnation | At most 60 seconds; one presentation and one exact action |
| Reauthentication | Current valid browser session; at most 30 minutes of continuous viewing before a fresh authenticated policy decision | Protected-command reauthentication no older than canonical 10-minute freshness, followed by a fresh exact-command confirmation |
| Payload binding | Session/cursor bounds only | Action, canonical input-object digest, byte count, and submit policy |
| Side effects | None | Only the exact bound input action; no session lifecycle or shell authority |

A view-grant renewal re-evaluates Actor, human-role-binding revision, project scope, role, exact session
incarnation, assignment interval, runner epoch, policy revision, expiry, and revocation. Renewal cannot
create type authority. The total continuous viewing period is capped at 30 minutes, after which a fresh
authenticated policy decision is mandatory. Disconnect does not widen or transfer a grant. Reconnect after
grant expiry, role-binding revocation, session replacement, assignment change, runner fencing, or the
continuous-viewing cap requires the applicable new decision. One SSE connection is bound to one view-grant
ID and ends no later than that grant's absolute expiry; renewal mints a new grant and opens a new stream from
an authorized cursor rather than replacing authority underneath a live connection.

A type grant binds one exact action, input-object digest, and byte count. It can be presented once only, and
a new command requires a new grant. Grant minting requires protected reauthentication no more than 10 minutes
old and a fresh confirmation of that exact command; neither confirmation nor reauthentication is reusable as
command authority. Per exact Actor/session/incarnation, policy permits at most four `paste_text` and six
`submit` actions in any minute. Revocation refuses new dispatches immediately and closes an affected view
stream within 5 seconds. Any bound mismatch refuses with zero injection.

The authorization suite uses a controlled clock. It covers every view renewal, tab/concurrency,
role/project, assignment, runner-epoch, revocation, and expiry combination and proves zero extra output
disclosure. It also proves that type-grant replay, parallel use, reissue, stale policy, and delayed revocation
inject zero bytes at the exact expiry and revocation boundaries.

### Typed input and durable audit

Phase 2 does not stream browser keyboard events. It accepts two bounded actions:

- `paste_text`: canonical UTF-8 text within the CSO-approved byte limit; and
- `submit`: one explicit Enter action with no text payload.

Control characters, terminal escape sequences, NUL, file payloads, and secret-reference expansion are
refused unless a later canonical contract and CSO verdict names an exact safe action. Secrets are references,
never text typed through this console. The prohibited classes in `INV-70`, including credential material,
are detected and refused before any authoritative or object mutation and therefore before injection.

For every input that actually crosses into tmux, the durable audit answers **who typed what into which crew,
and when** without relying on a tmux log:

1. The browser gives the strict command one stable `client_command_id`. The server verifies Origin, CSRF,
   Actor, role/project authority, exact type grant, reauthentication, input policy, expected session
   incarnation, and idempotency.
2. In one authoritative transaction, ctower stores the accepted command, canonical requested bytes, and the
   exact planned injected bytes under the pinned adapter revision; appends `console_input_accepted`; and
   inserts the outbox item before responding or dispatching. The current mux plan therefore includes its
   leading ASCII space. Exact bytes use the protected object contract below while the append-only envelope
   remains hashable. The fact binds Actor, role-binding and grant revisions, project, seat, crew engagement,
   exact session/assignment/runner epoch, action, requested and planned byte counts and digests, server time,
   command ID, adapter/policy revisions, and causation.
3. The fleet consumer verifies its workload identity and current epoch, resolves the opaque backend target,
   and deterministically reproduces the stored injection-plan digest. At the final pre-mux boundary,
   immediately before any subprocess execution, it invokes the one authenticated durable adapter-admission
   operation keyed by `(grant_id, client_command_id, runner_epoch)`. That operation performs a linearizable
   compare-and-set from unconsumed to admitted, binds the stored injection-plan digest, and appends the
   admission fact. Only a newly admitted result permits the registered adapter action. The adapter uses this
   narrow operation but never Record-tier persistence or a grant-minting path.
4. A successful adapter invocation returns a strict receipt containing start/end times, backend-target
   digest, adapter revision, subprocess result, and the count, digest, and protected object reference for the
   exact **adapter-dispatch bytes handed to `bin/mux`**. Canonical requested bytes, deterministic planned
   bytes, adapter-dispatch bytes, and any separately specified harness-acknowledged bytes/digests remain four
   distinct audit fields. A receipt mismatch cannot be accepted as success.
5. ctower appends receipt, reconciliation, and terminal-state facts without mutating or deleting the accepted
   command, event, outbox, admission, or any prior fact. A crash between admission and receipt becomes the
   terminal machine state `state_unknown`; it is never automatically reinjected. Duplicate delivery,
   competing workers, adapter restart, or a fenced runner epoch must produce at most one mux invocation. A
   changed body conflicts; an expired, replayed, stale-epoch, or already-consumed grant injects nothing. The
   conformance oracle is the mux-wrapper byte log together with the complete command/audit chain.

The UI distinguishes `unsent`, `durability pending`, `accepted`, `dispatching`, `injected (unacknowledged)`,
`acknowledged`, `refused`, `expired`, and `state unknown`. A zero exit status from `paste-buffer` or
`send-keys` supports only `injected (unacknowledged)`. `acknowledged` requires the harness command ID/ACK from
the canonical runner protocol. Where the harness cannot provide it, acknowledgement remains unsupported;
pane echo, silence, prompt changes, and transcript text never upgrade the state. Requested, planned,
adapter-dispatch, and harness-acknowledged fields must be reconstructable by command ID across the complete
crash matrix.

### Restricted exact-byte custody

Audit rows and protected input objects are append-only and survive grant/session revocation. Every exact
input object is envelope-encrypted with a distinct per-object data-encryption-key reference. Exact-byte reads
use only the dedicated `console_input_audit_reader` authorization path, and every attempted reader access
appends a reader-access fact. Ordinary Fleet, Ticket, Inbox, logs, URLs, error bodies, telemetry, screenshots,
and exports expose metadata and digests only.

Before Phase 2 publication, an operator/CSO-approved versioned policy names the retention period,
jurisdiction and classification, legal-hold and crypto-erasure behavior, permitted readers, and export
approval path. Console-policy and Phase 2 publication both refuse if any value is missing; implementation
supplies no default. The custody proof recovers exact bytes through an authorized reader, denies an
unauthorized reader, verifies append-only access logging, exercises expiry and erasure behavior, and proves
that a canary secret appears in no ordinary surface.

### Output confidentiality and truth

All pane output is **RESTRICTED**, runner-untrusted forensic material. It may contain credentials, customer
data, hostile control sequences, or prompt-injected links, and terminal content can never downgrade that
classification or become Record truth. Phase 1 is disabled for `bh-loop` and every project classified for
customer, regulated, or higher-sensitivity content; a later operator/CSO-approved policy revision and fresh
CSO verdict are required before either can receive a `console_session_allowed` fact.

Output uses the same custody family as exact input. Each raw output object is envelope-encrypted with its own
data-encryption-key reference. Ordinary Fleet and Ticket projections/timelines, Inbox, logs, URLs, error
bodies, telemetry, screenshots, notifications, and exports expose only chunk/object metadata, byte counts,
digests, cursors, classification, and gap state. Content is available only through the dedicated
`console_output_reader` path embedded in the contextual console panel or through its separately authorized
forensic-read operation. That path requires the exact Actor/project/session/grant decision above, and every
stream open, reconnect, replay request, and forensic object read appends an access fact with Actor, policy,
session incarnation, cursor/object range, purpose, time, and outcome. Revocation never deletes output or
reader-access facts.

The browser receives only bounded base64-encoded chunks and renders decoded bytes as inert terminal text.
Executable HTML, ANSI/OSC commands, terminal hyperlinks, image/file escapes, and automatically followed
links are stripped or quarantined before rendering and cannot create browser navigation or execution. The
versioned console policy supplies raw-output retention and crypto-erasure, permitted reader roles, redaction
and quarantine rules, and export approval; policy publication refuses a missing value. The viewer consumes
the canonical Runtime raw-log path: restricted raw bytes remain content-addressed and retention-limited,
while safe metadata and cursor/gap facts persist before broadcast. Structured events remain the control
protocol.

The tmux adapter may use `capture-pane` for an initial snapshot and the existing `pipe-pane` log as a byte
source, but it must turn observations into ordered chunks with a durable cursor before sending them to a
browser. It must show a bounded `log_gap` whenever it cannot prove continuity. A capture or log file is never
promoted to success, evidence, assignment, delivery, or health.

## Streaming transport decision

| Option | Strengths | Costs and boundary risk | Disposition |
|---|---|---|---|
| Server-Sent Events (SSE) plus HTTPS commands | One-way by construction; browser-native reconnect and event IDs; ordinary same-origin session/CSRF controls; simple read-only first slice | Input needs a separate POST; binary/ANSI bytes require a strict encoded chunk; proxy buffering, per-origin connection limits, replay bounds, and backpressure need tests | **Choose for phases 1-3.** Output uses SSE; phase 2 input stays a durable HTTPS command rather than a socket write |
| WebSocket | Low-latency full duplex; matches the canonical runner's ordered duplex concept; efficient if later interaction truly needs many bidirectional frames | Larger auth/origin/reconnect/fencing surface; easy to couple input to connection state or bypass durable commands; explicit flow control and cursor recovery still required | Defer unless measurements show SSE + POST misses an accepted latency or load target; even then input remains the same durable command protocol |
| ttyd-class bridge | Mature terminal emulation and direct PTY/tmux interaction; Mission Control proves loopback launch and read-only attach are practical | Its capability URL and bridge-lifecycle audit do not resolve canonical Actor/project/session grants or record injected bytes; direct writable PTY access permits unaudited control sequences and makes connection state look authoritative | Do not expose as the ctower product surface. Reuse only implementation lessons or terminal rendering code behind the authorized adapter boundary |

SSE is selected because the first increment is intentionally one-way and the second does not need a duplex
transport: typing is an auditable command, not ephemeral socket traffic. The build must measure end-to-end
chunk latency, reconnect recovery, memory per stream, maximum concurrent streams, proxy buffering,
backpressure, and bounded replay before reconsidering WebSocket. A transport change cannot change grant,
audit, idempotency, cursor, or acknowledgement semantics.

### Phase 1 SSE limits

SSE is a server-authorized read channel, never a bearer channel. Its URL contains no grant, session,
capability, cursor content, or other credential material; the server resolves the opaque secure browser
session and exact view grant. The response is exact-origin with credentialed CORS disabled,
`Cache-Control: no-store`, proxy buffering disabled, and compression disabled.

The limits are fixed for Phase 1:

- one concurrent SSE connection per view grant and per exact Actor/session/incarnation;
- one grant and stream last at most 5 minutes, with no in-place lease substitution;
- at most 16 KiB of decoded output bytes per chunk;
- at most 1 MiB of output delivered per grant in any rolling 60 seconds;
- a replay window containing at most 1 MiB and at most the preceding 60 seconds; and
- at most 256 KiB of unsent pending data per stream.

Crossing the delivery-rate or pending-data cap closes the stream with a typed `rate_limited` or
`slow_consumer` terminal event and a labelled gap cursor; it never drops bytes invisibly or expands memory.
Cursor loss, malformed event data, unavailable output custody, or an unprovable range produces a labelled
gap and requires a new authorized snapshot/replay decision. Expiry closes the stream at the grant's exact
absolute deadline; session/global revocation closes it within 5 seconds. Reconnect cannot reuse an expired or
revoked grant.

## Private-network and direct-path proof

The console origin binds only the configured loopback or tailnet address, never `0.0.0.0`, `::`, or an
unspecified/default host. This is the console instance of Mission Control's standing cadence v1.21
tailnet-bind rule. Every deploy archives an `ss -tlnp` listener inventory proving the expected process and
exact address, and the already-deployed recurring sweep searches both seat-owned and third-party listeners
for wildcard or newly published console ports. A wildcard listener, public A/AAAA route, Tailscale Funnel,
unexpected Caddy origin/host, firewall drift, or new console port fails the deploy or pages as a blocking
security defect.

The same proof pack contains Caddy, firewall, DNS, and Tailscale/Funnel inventories, an allowed private
same-origin probe, and public-network and foreign-project negative probes. The tmux socket and `bin/mux` are
reachable only by the registered adapter workload identity. A route/schema/bundle and process-boundary
inventory proves that the browser, web handlers, ttyd, generic process endpoints, and unregistered workloads
have no direct path. Tailnet reachability never substitutes for OIDC session, CSRF, project, session, or
grant authorization.

## Runaway and misuse containment

Containment is versioned policy backed by append-only facts, not an in-memory flag:

- An operator-only `console_kill_switch_activated` fact stops all view/type grant minting and renewal,
  revokes every live console grant, closes every stream within 5 seconds, disables adapter admission, and
  leaves ordinary Fleet, Ticket, and Inbox operation available. Recovery requires a later
  `console_kill_switch_cleared` fact that names the resolved incident and approved policy revision; process
  restart cannot clear it.
- A `console_session_revoked` fact binds one exact `ConsoleSessionRef` and cause. It immediately refuses new
  grants and adapter admission for that incarnation and closes only its active streams within 5 seconds.
  Assignment change, `@project` mismatch, session-name reuse, runner fencing, output-rate breach, or policy
  revocation emits this fact rather than relying on connection loss.
- Adapter identity/epoch failure, injection-plan/receipt mismatch, unexplained mux invocation, or suspected
  duplicate injection quarantines the runner, revokes every console session/grant on that runner, disables
  type issuance for it, and appends an incident before repair or reuse.
- Three denied or cross-project grant attempts by one Actor in any 5 minutes append a 15-minute
  Actor-scoped issuance suspension and notify the operator. Every prohibited-data detection, output-custody
  denial, audit-object read, unexplained terminal byte range, or gap beyond the replay proof appends a
  security finding with the containment outcome.

Every activation, automatic trigger, grant/session revocation, stream-close attempt/result, quarantine,
suspension, notification attempt, and clear action is an immutable audit fact carrying Actor or containment
principal, scope, reason, policy revision, incident/finding ID, server time, and affected grant/stream IDs.
Operator notification is attempted at most three times within 5 minutes; exhaustion appends a visible
`notification_delivery_failed` fact and does not relax containment.

## Incremental delivery

Each phase is a complete, independently releasable capability. There is no dormant writable route, hidden
feature flag, or dark-shipped bridge in an earlier phase.

### Phase 1 — read-only viewer

Prerequisites are the accepted identity/session join and explicit session-allowlist fact, canonical browser
auth boundary, Runtime cursor/log-gap contracts, registered fleet adapter, approved full-frame mockup, the
tailnet/direct-path proof, published containment matrix, and CSO approval of the exact Phase 1 candidate.

- Fleet groups authorized rows project -> seat -> crew. Ticket detail may link to the same panel when the
  session fact names that ticket.
- Opening the panel obtains an exact view grant, then receives an initial labelled snapshot and ordered SSE
  chunks with cursor, watermark, freshness, connection, retention-window, and gap state.
- The panel is the dedicated RESTRICTED output-reader path. Ordinary surfaces expose metadata/digests only,
  and `bh-loop`, regulated projects, Commander seats, untagged/mistagged sessions, and sessions without the
  exact allowlist fact have no console-visible session.
- The delivered assets, OpenAPI, generated client, server routes, and adapter contain no type command, writable
  ttyd bridge, input field, or input grant.
- Revocation, project/assignment changes, runner fencing, session replacement, expiry, and cursor loss close
  the stream and become explicit state.

### Phase 2 — typed input

Prerequisites are phase 1 production verification and an additional CSO verdict on the final type-grant,
input-policy, audit-retention, and incident-response contracts.

- The composer supports bounded `paste_text` and explicit `submit`, each as a protected, idempotent command
  tied to a one-presentation, at-most-60-second type grant, 10-minute-or-fresher protected reauthentication,
  and a fresh confirmation of the exact command.
- ctower persists exact requested and deterministic planned content atomically before dispatch, then appends
  admission and the exact adapter-dispatch content handed to `bin/mux`. Harness-acknowledged content remains
  a separate field and exists only when the canonical runner protocol supplies that acknowledgement. No
  command that reaches adapter admission lacks Actor, project, seat, crew, session, grant, policy, and time
  attribution.
- Cross-project, stale-incarnation, stale-epoch, viewer-role, revoked, replayed, mismatched, forbidden-data,
  rate-limit, and adapter-unknown cases dispatch zero bytes.
- The UI never calls injection “delivered” or “acknowledged” without the corresponding canonical fact.

### Phase 3 — chat

Prerequisites are phase 1, the native inbox and recipient fact rails from #336/#363, and an accepted and
shipped #355 bridge. Phase 2 is not a dependency: chat must not require terminal type authority.

- The contextual send box creates a native inbox message in a thread linked to project, seat, crew
  engagement, and, when known, recorded work session/ticket.
- Sent, delivered, and read are separate append-only facts. The UI displays their exact state and never
  derives read from terminal output or crew activity.
- #355 owns bridge delivery/cutover. A message uses one rail at a time under its accepted stage; no terminal
  injection fallback or untracked dual write exists.

For every phase, the operator receives a durable notification when its build ticket is filed and a separate
notification only after the phase is production-verified. “Merged” is not “shipped.”

## Acceptance and proof contract

The issue-level acceptance maps as follows: A1 is covered by CC-02 through CC-07 and the CSO verdict; A2 by
CC-01; A3 by CC-08. These criteria become implementation authority only after incorporation into canonical
SPEC and activation of stable build tickets.

| ID | Testable criterion | Exact proof artifact | Accountable verifier |
|---|---|---|---|
| CC-01 | Two projects, at least two non-Commander seats, and at least three crews group only from accepted project/seat/assignment/session facts; only exact `@project`-matching sessions with current `console_session_allowed` facts are console-visible; Commander-seat, unbound, untagged, mistagged, ambiguous, renamed, removed, and reused tmux-session fixtures never create visibility, identity, or authority | Projection/eligibility fixture matrix, live-tag/source-watermark snapshot, allowlist and tag mutation tests changing the exact console surface without product-code changes, Commander-session absence, cross-project read denial | QA plus Engineering Manager |
| CC-02 | Only Access/control-plane policy can mint grants; view grants last no more than 5 minutes, permit one SSE stream for one exact grant and Actor/session/incarnation, cannot substitute a lease under a live connection, and force a fresh decision after 30 continuous minutes; type grants last no more than 60 seconds, bind one action/digest/count, require fresh exact-command confirmation, present once, and enforce four `paste_text` plus six `submit` actions per minute | Controlled-clock matrix covering issuer bypass, renewal, tab/concurrency, role/project, assignment, runner epoch, reauthentication/confirmation, replay, parallel use, reissue, stale policy, delayed revocation, stream-at-expiry, expiry boundaries, and exact RFC 9457 snapshots; before/after output and mux-byte comparisons prove zero disclosure/injection | CSO plus QA |
| CC-03 | Phase 1 has no writable browser, API, client, adapter, or ttyd path, and every stream stops at its lease deadline or within 5 seconds of authority, allowlist, project-stamp, incarnation, runner, session, or kill-switch revocation | Route/schema/bundle inventory diff, static boundary test, controlled-clock expiry and per-scope revocation/fencing recordings, immutable revocation/stream-close audit query | CSO plus UI QA |
| CC-04 | Every accepted action atomically stores command, event, outbox, requested bytes, and deterministic planned bytes; one linearizable admission CAS keyed by `(grant_id, client_command_id, runner_epoch)` binds that plan at the final pre-mux boundary; admission, receipt, reconciliation, and terminal facts append without mutation; duplicate delivery, competing worker, restart, and fencing invoke mux at most once, while admission-to-receipt crash terminates `state_unknown` without reinjection | Complete commit/admission/invocation/receipt crash matrix, duplicate/same-key-different-body and competing-worker tests, mux-wrapper byte log, and audit reconstruction by command ID with distinct requested/planned/adapter-dispatch/harness-acknowledged vectors including mux's leading space | QA plus independent audit reviewer |
| CC-05 | Every input and output content object is RESTRICTED, envelope-encrypted, and bound to a distinct per-object data-key reference; only its dedicated input/output reader can recover it and every access attempt appends a fact; ordinary Fleet/Ticket projections, Inbox, logs, URLs, errors, telemetry, screenshots, notifications, and exports expose metadata/digests only; Phase 1 refuses output-policy or Phase 2 input-policy publication when any custody value is missing | Policy-schema refusal tests; authorized output/input recovery, unauthorized denial, append-only reader-access, expiry/erasure; hostile-output safe-render corpus; canary-secret ordinary-surface scan; `bh-loop`/regulated-project console absence | CSO |
| CC-06 | SSE carries no bearer material, one stream cannot outlive its exact grant, decoded chunks are at most 16 KiB, delivery is at most 1 MiB per rolling 60 seconds per grant, replay is at most 1 MiB/60 seconds, and pending data is at most 256 KiB; reconnect resumes without duplicate display, while rate, slow-consumer, malformed, cursor-loss, and unprovable-range cases close with a typed result and visible bounded gap without cross-session bytes | Controlled-clock SSE URL/header/cache/compression suite; exact-boundary chunk/rate/replay/pending tests; reconnect/restart/proxy-buffer/backpressure/load suite with cursor/object audit and responsive browser recording | QA plus SRE |
| CC-07 | No console route is reachable from the public interface, wildcard listener, or Tailscale Funnel; each deploy and recurring `ss -tlnp` sweep proves exact loopback/tailnet binds and alerts on new seat or third-party wildcard listeners; only the registered adapter identity can reach tmux/`bin/mux`; unauthenticated, CSRF-invalid, cross-origin, expired-session, and cross-project requests disclose nothing and mutate nothing | Archived deploy and recurring `ss -tlnp` inventories; listener/firewall/Caddy/DNS/Tailscale inventory; route/schema/bundle and process-boundary direct-path proof; public-network/foreign-project negative probes; auth/CSRF/Origin browser contexts; same-origin private positive probe | CSO plus SRE |
| CC-08 | Phase order is enforced: viewer ships without input; type ships only after viewer and its new CSO verdict; chat ships on #336/#363/#355 without requiring type or falling back to it | Dependency graph assertion, per-phase API/bundle inventory, release facts and production smoke recordings | Engineering Manager plus release verifier |
| CC-09 | Chat creates exactly one native message and renders independent sent/delivered/read states; retries, bridge outage, and unread recovery do not duplicate or invent state | Inbox/recipient-fact state matrix, bridge idempotency and outage tests, browser recording | QA |
| CC-10 | The console remains contextual within the locked five-surface product and matches an operator-approved 1:1 full-platform-frame mockup at desktop and mobile widths | Route inventory, full-frame reference and side-by-side screenshots, keyboard/screen-reader/accessibility run using every visible control | Designer plus UI QA; operator approves taste |
| CC-11 | Terminal bytes, pane state, socket state, chat delivery, and bridge receipt never satisfy workflow, evidence, completion, health, or delivery truth | Mutation/anti-inference tests and Record state diff across deceptive transcript fixtures | Engineering Manager plus QA |
| CC-12 | Appending the global kill-switch fact stops grant issuance/renewal and adapter admission and closes every stream within 5 seconds; per-session revocation closes only the exact session streams; threshold-triggered Actor suspension and runner quarantine follow the fixed incident matrix; every trigger/revocation/close/notification/clear remains append-only while queued input drains/refuses without duplicate injection and ordinary Fleet/Ticket/Inbox stays healthy | Controlled-clock containment matrix, staged global/per-session/runner rollback exercise, pending-command matrix, immutable revocation and notification audit query, restart-persistence check, and post-containment smoke evidence | SRE plus CSO |

Every proof records baseline and candidate digests and verifies the named changed property directly. A green
unrelated suite, page-load-only screenshot, prose assertion, tmux transcript, or mock response does not
satisfy a criterion.

### Deployed-environment end-to-end blocker

Before any phase is called shipped, UI QA uses the candidate in the private deployed environment with two
real project-scoped human bindings and separate authenticated browser contexts. The run must open an allowed stream,
prove a foreign project absent, interrupt and recover the stream, rotate or revoke a grant, replace/fence the
session incarnation, remove its allowlist or `@project` stamp, trigger the exact rate and slow-consumer caps,
exercise per-session revocation and the global kill switch, and observe the required gap/closure and audit
states within the stated deadlines. The run also proves Commander-seat and `bh-loop` sessions absent and
archives the deploy plus recurring `ss -tlnp` listener evidence. Phase 2 additionally types a unique canary,
retries across a forced disconnect, proves one injection and its complete audit chain, exercises explicit
submit, and proves a viewer and foreign project inject zero bytes. Phase 3 proves sent -> delivered -> read and
a bridge outage/recovery against the real rails. This deployed E2E is a hard blocker, not an optional smoke.

## Provisioning and release

No plaintext secret or reusable token is added. The build needs these configured references and owners:

| Need | Environment | Provisioner/owner |
|---|---|---|
| Existing private HTTPS origin, tailnet listener/firewall policy, and explicit absence of public/Funnel routes | Test and production-like private VPS | SRE; independently checked by CSO |
| Existing OIDC provider registry, human role bindings, browser-session and CSRF configuration from `CT-I1-013` | Deployed E2E and production | Operator provisions authority; SRE provisions secret references |
| Operator/CSO-approved versioned console policy with issuer; session allowlist; RESTRICTED output class and ineligible project classes; safe-render/quarantine; exact chunk, delivery-rate, replay, pending-byte, TTL, revocation, input-rate, role, retention-period, jurisdiction, legal-hold/crypto-erasure, permitted-reader, export-approval, containment-threshold, and notification values | Test and production | Operator applies accepted configuration after CSO verdict; publication refuses any missing value |
| Registered fleet-adapter workload identity, allowed project/target scope, runner protocol and adapter revisions | Test and production | Platform administrator/SRE; ctower stores references and revisions only |
| Envelope-encryption key references and dedicated `console_output_reader` plus `console_input_audit_reader` policy for restricted content objects | Test and production | SRE provisions key references; CSO approves access and retention; operator grants readers |

There is no feature flag. Each phase ships by adding only its approved contracts/routes/assets after its
dependencies pass. The release inventory proves that later-phase capabilities are absent. Immediate
containment appends the global kill-switch fact; release rollback additionally removes the phase's
routes/assets on the next release. Neither path deletes append-only audit, rewrites message facts, exposes
ttyd, or falls back to direct mux calls. Pending input is deterministically drained if already injected or
refused if it has not crossed the adapter boundary.

## CSO adjudication and phase boundary

The prior candidate received an approve-with-conditions verdict. Its sole-issuer/view-lease bounds,
type-grant bounds, linearizable final admission, truthful append-only audit semantics, and restricted exact
input-byte custody were folded first. The Phase 1 residuals are now normative too: RESTRICTED output custody
and safe rendering, exact session eligibility, standing tailnet/direct-path proof, fixed SSE abuse bounds,
and append-only containment. They are decisions, not implementation latitude. The amended exact digest still
requires CSO delta re-adjudication before a Phase 1 build ticket activates.

Two questions remain **open by design**, each blocking only its own later phase:

3. **CSO-Q3 — Input vocabulary:** Approve the UTF-8/size policy, `paste_text` and `submit` actions, prohibited
   control characters, multiline/paste handling, and whether any later interrupt/control-key action deserves
   its own grant class. This blocks Phase 2 typed input, not Phase 1.
9. **CSO-Q9 — Chat correlation:** Approve what terminal/session metadata may be attached to native inbox
   messages without leaking output or creating a second transcript authority. This blocks Phase 3 chat, not
   Phase 1.

Any adverse answer changes this proposal through the canonical process and requires a new exact-digest CSO
verdict. Phase 1 may proceed only after CSO approves this exact Phase 1 candidate and its prerequisite
canonical contracts/deployed proof. Phase 2 cannot begin while Q3 is open; Phase 3 cannot begin while Q9 is
open. Neither open question authorizes a fallback path or blocks an otherwise approved Phase 1 viewer.

## Engineering-manager checklist disposition

1. **Outcome:** Named above for the private-VPS target environment.
2. **Acceptance:** CC-01 through CC-12 are observable pass/fail criteria.
3. **Proof and owner:** Every criterion names an exact artifact and accountable verifier.
4. **Deployed E2E:** Required as a hard blocker for each releasable phase.
5. **Provisioning:** Every required configuration/secret reference and owner is listed; raw secrets are absent.
6. **No dark ship:** No flag; each phase's route/schema/bundle inventory proves later capabilities absent.
7. **Scope/non-goals:** Bounded explicitly, including no sixth surface and no direct ttyd/tmux product path.
8. **Security boundary:** The first five CSO conditions and all Phase 1 Q4-Q8 answers are normative above;
   Q3 blocks only Phase 2 and Q9 blocks only Phase 3.
9. **Design gate:** A 1:1 full real-platform-frame mockup, responsive variants, operator approval, and UI QA are
   required before build.
10. **Rollback:** Grant revocation, route removal, pending-command disposition, audit preservation, and smoke
    proof are specified.
11. **Delta verification:** Proofs compare exact baseline/candidate digests and the changed property.

## Sign-off

```text
SIGNED-OFF
  seat:      engineering-manager
  crew:      em-r371-q-pass
  model:     GPT-5 (Codex runtime)
  claim:     #371 now gives concrete normative Phase 1 answers for output custody, session eligibility, private-network proof, SSE abuse bounds, and containment while leaving Q3/Q9 scoped to their later phases.
  stood-under: exact console candidate; original and delta CSO adjudications; canonical SPEC/DECISIONS/ARCHITECTURE/ROADMAP and root README; Mission Control cadence v1.21 tailnet-bind/ss-sweep evidence; CC-01..CC-12 testability review
  if-this-breaks: re-summon engineering-manager crew em-r371-q-pass on issue #371 / PR #373 before implementation proceeds
```
