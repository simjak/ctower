# Crew Console specification

Crew Console is ctower's terminal window for one recorded live worker engagement. Its purpose is narrow:
let an authenticated person inspect exact terminal output and, in a later separately approved release, send
one explicitly confirmed command without treating a terminal process as product truth.

The private read-only server foundation is implemented today. It discovers eligible sessions, issues bounded
view grants, stores restricted output, and serves a durable event stream. The product browser panel, safe
terminal renderer, and terminal input are planned and unavailable.

For the implemented design, start with [Console view grants](../../concepts/console-viewer.md). For the exact
private deployment procedure, use [How to deploy and verify the Console viewer](../operations/console-viewer.md).
The current routes are listed in the [HTTP API reference](../../reference/http-api.md#console-viewer).

## Concepts

### Three windows, three kinds of truth

The operator experience has three cooperating windows. They may link to the same Project, ticket, worker, or
recorded session, but they never impersonate one another.

| Window | Purpose | Authority |
|---|---|---|
| **Chat** | Human-readable conversation with a registered recipient | Native Inbox messages and recipient-authored sent, delivered, and read facts |
| **ctower interface** | Plans, tickets, movement, proof, delivery, health, and workspaces | Accepted ctower records and rebuildable projections |
| **Terminal** | Exact live output and later bounded direct input | Console grants over one exact current runtime session |

Chat is never delivered by terminal injection. Terminal output never becomes a chat acknowledgement. A pane,
socket, host path, process exit, bridge receipt, or transcript cannot establish workflow movement, evidence,
completion, health, Workspace lifecycle, or work delivery. The deliberate exception is message state: an
accepted native Inbox recipient fact does establish that message's delivered or read state.

### Contextual placement, not a sixth destination

ctower has five product surfaces: Home, Board, Ticket detail, Fleet, and Analytics. Console remains contextual
inside that model:

- Fleet is the direct home for an eligible live worker session.
- Ticket detail may link to the same Console when the recorded session belongs to that ticket.
- Board movement uses accepted workflow transition facts, not terminal activity.
- Home and Analytics may link to recorded work but do not gain a Console destination.
- There is no top-level `/console` route.

The eventual browser panel is part of the product browser checkpoint. The existing private server routes do
not activate a product interface by themselves.

### Identity is a current join

A familiar process or terminal name is not enough to identify a session. Console eligibility joins all of
the following current facts:

1. tenant and Project;
2. a non-coordinator worker identity and engagement interval;
3. the recorded work session and runtime attempt;
4. runner identity and epoch;
5. the registered backend reference and its incarnation; and
6. the live backend's Project stamp.

An administrator allowance makes that exact join eligible; it is not a bearer credential. Discovery, grant
minting, renewal, stream opening, and stream polling re-evaluate the join. Missing, stale, foreign, renamed,
replaced, revoked, or ambiguous facts make the session absent or produce a typed no-disclosure refusal.

A Workspace may be linked as context, but its record remains independent authority. Console cannot derive a
Workspace from a host path, copy its mounts or credentials, close it, or turn process disappearance into
Workspace state. Likewise, a movement feed and Console may point to the same ticket while remaining separate:
accepted transition facts create movement; terminal bytes do not.

## Quickstart

There is no supported product Console to open yet. The implemented capability is a private verifier surface,
not a general installation or public service.

To exercise the read-only foundation safely:

1. Read [what is deliberately unavailable](../../start-here/availability.md) and use only disposable or
   reconstructible data.
2. Follow the [Console viewer deployment procedure](../operations/console-viewer.md) to configure the private
   HTTPS origin, register one existing read-only target, append an exact allowance, and prove the listener.
3. Use the [Console viewer API](../../reference/http-api.md#console-viewer) through an authenticated same-origin
   browser session. Do not put credentials in URLs or create a handwritten browser bearer client.
4. Verify expiry, revocation, replacement fencing, gap reporting, and the global kill switch before trusting
   the stream.

The expected result is a bounded server-sent event stream. It does not include a safe terminal renderer,
typing field, key forwarding, shell endpoint, session lifecycle controls, file transfer, or public access.
The older direct terminal reader is a separate development-only tool and is not evidence for this boundary.

## Reference

### Shipped read-only server contract

| Concern | Current behavior |
|---|---|
| Eligibility | One exact current-fact join; coordinator-owned target sessions and incomplete joins are ineligible |
| View authority | One server-held `ConsoleViewGrant` for one Actor, human role binding, browser session, Project, policy revision, and Console session |
| Lifetime | At most five minutes per grant, one stream claim, complete re-evaluation on renewal, and at most thirty minutes of continuous viewing |
| Browser boundary | One configured private HTTPS Origin, secure human-session cookie, matching CSRF cookie/header/persisted digest, no CORS authority, and no credential in the event URL |
| Output custody | Every chunk is RESTRICTED, durably cursor-addressed, and encrypted under a fresh per-object data key; only the dedicated audited reader can recover it |
| Stream bounds | At most 16 KiB decoded per chunk, 1 MiB delivered per minute, 1 MiB replayed per minute, and 256 KiB pending |
| Gaps | Truncation, an unprovable range, rate limiting, and a slow consumer append and signal a typed gap instead of silently skipping bytes |
| Runtime Adapter | Reads one registered existing log and live backend identity; it has no Record client, shell, pane write, key injection, generic process route, or fallback target discovery |
| Network | Literal loopback or Tailscale listener only; wildcard, public, hostname-default, proxy-header, and Funnel authority are refused |
| Containment | Expiry, session revocation, replacement fencing, and the global kill switch refuse new admission and close affected streams with a typed reason within five seconds |

### Future safe product viewer

The browser viewer must arrive through the existing five-surface product boundary. Before terminal input can
be considered, that viewer must prove all of the following on the deployed private product:

- only eligible sessions appear in Fleet or a linked Ticket detail;
- raw output is rendered as inert terminal content and cannot create HTML, script, navigation, clipboard,
  download, credential, or browser-origin authority;
- hostile ANSI, OSC, control, bidi, invisible, malformed, oversized, and split-sequence fixtures remain inert
  while gaps and uncertainty stay visible;
- reconnect, expiry, revocation, replacement, rate, and slow-consumer states match the durable stream facts;
- desktop and mobile layouts use the full real product frame and pass keyboard, screen-reader, contrast,
  focus, overflow, and every-control checks; and
- a private deployed run proves the exact browser, API, custody, Adapter, and listener chain rather than a
  component preview or mock response.

Visual placement within Fleet and Ticket detail remains a product design decision. A design candidate cannot
activate a route, grant, or input command.

### Future terminal input boundary

Terminal input is inactive. It requires a new authored contract, implementation ticket, complete product
viewer proof, and a fresh independent maximum-depth security verdict over the exact candidate digest. A
prior review of split paste and submit actions was withdrawn; it is not approval for implementation.

#### One confirmed line, one exclusive generation

The first input release uses one bounded whole-line action. One presentation confirms the complete effective
line and its terminating Enter together. Standalone paste, standalone submit, raw keys, multiline input,
interrupts, resize, file transfer, shell/session lifecycle, and alternate writable terminal paths are absent.

The server may mint a planned `ConsoleTypeGrant` only when all of these conditions hold:

- the current human is authorized for the exact Project and Console session;
- protected reauthentication is no older than ten minutes;
- the grant binds one Actor, role binding, browser session, Project, session incarnation, assignment interval,
  runner epoch, policy revision, full canonical line, byte count, and action;
- the grant expires within sixty seconds and permits one presentation and one use; and
- an exclusive writer lease names one clean input generation for that exact session.

Final admission compares and advances the input generation immediately before the registered Adapter action.
Another Actor, tab, writer, direct attachment, stale pending buffer, intervening input, changed runtime fact,
expired grant, or revoked authority invalidates the generation and injects zero bytes. If the system cannot
prove that the generation is clean and exclusively held, it refuses. The Adapter performs the accepted line
plus Enter as one guarded operation; no output-stream event can dispatch input.

#### Unicode and confirmation safety

The server, never the browser, derives the canonical input. The first vocabulary is one NFC-normalized UTF-8
line of at most 4,096 bytes. It rejects:

- CR, LF, NUL, C0/C1 controls, terminal escape/ANSI/OSC sequences, and Unicode line or paragraph separators;
- bidi formatting controls, zero-width and other default-ignorable code points;
- malformed or ambiguous encoding, multiline content, file payloads, secret values, and secret expansion;
  and
- any action outside the single whole-line command.

Confirmation presents the exact canonical line and a bidi-isolated escaped code-point/octet representation
derived by the server. The representation must match the bytes handed to dispatch. Editing the line withdraws
the grant and starts a new confirmation.

Raw input content digests are restricted data because short commands are enumerable. Ordinary product
surfaces expose only opaque command identities or keyed non-enumerable commitments. Exact bytes and raw
digests are recoverable only through the dedicated audited input reader.

#### Durable audit and final admission

Acceptance atomically records the command, canonical requested bytes, deterministic planned bytes, event,
outbox item, Actor, Project, worker engagement, Console session, grant, policy revision, and server time. Exact
input objects are envelope-encrypted under distinct data-key references before dispatch.

The authenticated final admission is a linearizable compare-and-set over the grant, command, runner epoch,
session incarnation, writer lease, and input generation. Duplicate delivery, competing workers, restart,
replay, or fencing can invoke the Adapter at most once. Requested, planned, Adapter-dispatch, and any later
harness-acknowledged bytes remain separate immutable facts.

An Adapter receipt means only that the registered Adapter observed an invocation result. It does not mean the
shell accepted, completed, or succeeded. A crash after admission without a provable receipt becomes
`state_unknown`, quarantines that input generation, and is never reinjected automatically.

#### Revocation and partial-input containment

Grant, session, Project, runner, and global revocation are checked at authorization and final admission. Any
revocation or expiry that could have contributed bytes to an unproved pending generation invalidates that
generation. No later command may execute it. Where a trusted reset cannot prove a clean generation, input
remains disabled for that session and the incident is visible; terminal silence or a new grant cannot clear it.

Every trigger, refusal, revocation, close attempt, quarantine, notification result, and explicit clear is an
append-only fact. The global kill switch stops grant minting and final admission, closes every view stream
within five seconds, preserves restricted audit objects, and leaves ordinary Ticket, Fleet, Workspace, and
Inbox reads available.

### Native chat remains separate

Chat uses native Inbox threads. A send creates one message under one idempotency identity. Sent, delivered,
and read are independent append-only facts; retries and recovery cannot duplicate or invent them. Terminal
input is never a fallback transport, and terminal output or worker activity never marks a message delivered or
read.

The product may offer an authorization-preserving link between Chat, a worker engagement, and a recorded
ticket or session. That link adds context only. It does not copy messages into Console, copy terminal bytes
into Chat, or create a second delivery ledger.

## Delivery order

Each stage is independently useful and contains none of the later stage's inactive routes or controls.

1. **Read-only server foundation — shipped.** Exact discovery, view grants, restricted output, bounded event
   streaming, private browser authentication, registered read-only Adapter, and containment are implemented.
2. **Safe product viewer — planned.** The contextual Fleet/Ticket panel, hostile-output renderer, responsive
   product proof, and deployed browser verification ship through the product browser checkpoint.
3. **Whole-line terminal input — blocked.** It begins only after the safe viewer is production-verified and
   the exact input candidate receives a fresh maximum-depth security verdict.

Native chat is a parallel capability and does not depend on terminal input. No feature flag, dormant writable
route, hidden bridge, direct terminal fallback, or compatibility layer may make a later stage reachable early.

## Acceptance blueprint

| # | Observable criterion | Status | Required proof | Accountable verifier |
|---:|---|---|---|---|
| 1 | Discovery exposes only exact current eligible sessions; stale, foreign, coordinator-owned, incomplete, renamed, replaced, and reused targets create neither visibility nor authority. | Delivered server foundation | Current-fact matrix, live identity fence, cross-Project and no-disclosure negatives | QA and architecture review |
| 2 | Only the control plane mints a view grant; it is one-stream, five-minute maximum, fully re-evaluated on renewal, and capped at thirty continuous minutes. Future type grants additionally bind one whole line, one clean generation, one writer lease, and one use. | View delivered; input blocked | Controlled-clock, concurrency, replay, reauthentication, generation, and zero-injection matrices | Security review and QA |
| 3 | The read release contains no writable browser, API, client, Adapter, or alternate terminal path, and every affected stream closes by expiry or within five seconds of revocation or fencing. | Delivered server foundation | Route/schema/bundle inventory, revocation recordings, immutable close facts | Security review and UI QA |
| 4 | A future accepted line is durably recorded before dispatch and one final compare-and-set permits at most one guarded invocation; cross-writer composition, stale input, replay, crash, and fencing cannot execute twice or under an unconfirmed line. | Blocked | Commit/admission/invocation/receipt crash matrix and byte-vector reconstruction | QA and independent audit review |
| 5 | Output and future input objects are RESTRICTED and separately encrypted; only dedicated audited readers recover them. The safe renderer keeps hostile output inert, and ordinary surfaces expose no enumerable input digest or exact bytes. | Output delivered; renderer/input blocked | Database privilege, custody, access-fact, hostile-render, and canary-leak suites | Security review |
| 6 | Event URLs carry no credential; chunks, delivery, replay, and pending data stay within their bounds; reconnect and every unprovable range produce an explicit gap without cross-session bytes. | Delivered server foundation | Exact-boundary stream, reconnect, restart, truncation, proxy, backpressure, and load suites | QA and operations review |
| 7 | Console is reachable only through the configured private HTTPS origin and literal private listener; unauthenticated, CSRF-invalid, cross-origin, expired-session, public, wildcard, Funnel, direct-process, and cross-Project paths disclose and mutate nothing. | Delivered server foundation | Listener/firewall/origin inventory and positive/negative private-network probes | Security and operations review |
| 8 | The safe product viewer ships after the server foundation; terminal input ships only after deployed viewer proof and a fresh exact-candidate security verdict; native chat remains independent. | Enforced delivery contract | Dependency, route, generated-client, bundle, release, and deployed-proof inventories | Engineering and release review |
| 9 | Chat creates exactly one native message and renders independent sent, delivered, and read states; retry, outage, and unread recovery create no duplicate or invented state. | Existing native capability | Inbox fact-state, idempotency, outage, and browser-state matrices | QA |
| 10 | Console stays contextual within the five-surface product, has no top-level route, matches an approved full-product-frame design at desktop and mobile widths, and passes keyboard, screen-reader, focus, and every-control checks. | Planned product viewer | Route inventory, full-frame comparisons, accessibility run, and product design approval | Design and UI QA |
| 11 | Terminal, pane, socket, host, and bridge observations establish no workflow, evidence, completion, movement, health, Workspace lifecycle, or work-delivery truth; accepted Inbox facts remain the sole exception for message delivery/read state. | Continuing invariant | Mutation and anti-inference fixtures with authoritative-record before/after comparison | Architecture review and QA |
| 12 | Global and per-session containment are append-only and exact-scope; viewer streams close within five seconds, and any future revoked or uncertain input generation is quarantined without reinjection while ordinary product reads remain healthy. | Viewer delivered; input blocked | Timed containment, pending-generation, restart-persistence, notification, and post-containment smoke evidence | Operations and security review |

Unrelated green tests, prose assertions, page-load-only screenshots, terminal transcripts, and mocked success
responses do not satisfy these criteria. Each proof records the exact candidate digest and verifies the named
changed property.

## Provisioning and recovery

The read-only foundation uses references to an existing private HTTPS origin, human identity provider,
project roles, versioned Console policy, registered read-only Adapter identity, and envelope-encryption keys.
No document, contract, event, log, fixture, or command contains a reusable credential or key value.

Future viewer and input releases must add every required policy value and secret reference through the same
reviewed configuration path. Missing custody, retention, reader, Unicode, writer-lease, generation, limit,
containment, or notification policy refuses publication. Infrastructure identities and permissions are
provisioned declaratively and reviewed before deployment.

Immediate read containment uses durable grant/session revocation or the global kill switch. Release rollback
also removes the affected routes and assets in the next release while preserving immutable audit and custody
facts. Future input rollback never re-enables a direct terminal writer, deletes audit history, retries an
unknown invocation, or clears an uncertain input generation without separately proven reset evidence.

## Deliberate non-goals

Crew Console does not provide a sixth product surface, browser IDE, file explorer, general shell API, raw key
forwarding, arbitrary control sequences, mouse forwarding, file transfer, session spawn/kill/restart, remote
desktop, public ingress, direct terminal attachment, transcript-derived product truth, or a compatibility path
to an older reader. New actions or trust boundaries require their own reviewed contract and proof.
