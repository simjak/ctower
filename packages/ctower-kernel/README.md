# ctower-kernel boundary

Trusted modular-monolith artifact. The development walking slice implements small Access, Catalog, Record,
Inbox, Knowledge, Integrations, Work, Proof, Workflow, Runtime, Projections, Attention, and generic Object Interfaces: authentication and
bootstrap authority; atomic Postgres command/event/outbox persistence; ticket lifecycle, comments, priority,
custody, assignment, blocker, relation, and typed-intent policy; universal component/bundle
validation/planning plus an atomic future-only Catalog pointer; server-pinned frozen criteria, digest-bound
evidence, protected verdicts and selective invalidation; explicitly pinned legal graph movement; declared
stage-entry review-dispatch intents whose
PR, proof lenses, routing-policy pin, independent-family rule, substrate consumption, and linked verdicts
remain visible on the ticket; proof-gated atomic resolve/close that also rejects incomplete dispatch joins
and releases every current-episode ownership interval; and a disposable six-lane
Board fold over accepted outbox records; native two-party inbox messages with append-only recipient
delivery/read facts and fact-derived unread state; immutable delivery attempts, poison, deduplicated Attention findings,
canonical acceptance-gated recovery dispositions; fixed Routine occurrences/jobs with event/result/outbox
lineage; four idempotent nightly dream effects whose consumption derives lane, crew, harness, model family,
effort, and tier from immutable substrate bindings and links the output digest to Routine custody; one
operator-authenticated, closed-registry ceremony that appends the canonical event and creates that immutable
binding exactly once;
five immutable fleet-beat revisions whose queued occurrences emit digest-verified full prompts for the
fixed DIRECTOR session; corrected digests serially replace only the tenant's active trigger while prior
revision/effect facts remain immutable; an operator/Commander retirement appends one immutable tenant-scoped
fact/event, transactionally removes the trigger, and prevents later registration from reactivating it; plus
operator-only routine/effect reads that grant no delivery or consumption authority;
independently attributable health; and a project-scoped typed event feed whose exact kind set is
derived from the authoritative event catalog's `project_feed` column, reusing the same `event_links`
subject join `ticket_audit` already proves rather than a second query shape.

Record is the lower append Interface and depends only on Telemetry. Work, Proof, and Workflow each own their
SQL implementation and depend downward on Record; Workflow imports neither Work nor Proof. Composition
injects their narrow readiness/current-proof capabilities into Workflow, keeping the repository dependency
graph acyclic. Record also owns the typed durability decision, RFC-8785/SHA-256 semantic command root,
subject-head dependency refusal, immutable named-standby acknowledgement, and fail-closed health snapshot.
Exact durability identity is `(tenant, principal, command)`. Accepted replay is authorized by a distinct
immutable finalization exactly bound to the complete acknowledgement receipt plus confirmation that the
same finalization was read from the named standby; merely primary-local acknowledgement/finalization state
remains pending. Subject serialization uses one global order: sorted advisory locks only for absent heads, sorted
`durability_subject_heads` row locks, then aggregate locks, all held through refusal or commit. Live health
uses two fixed-search-path, narrowly executable probes owned by a quarantined no-login statistics role;
its schema-CREATE and administration-assumption authority end after probe creation, unsafe pre-existing
authority is rejected, and NULL or malformed live evidence degrades with a typed reason. `ctower_svc`
does not inherit PostgreSQL monitor roles.
Its default policy remains `pending_only`. The approved persistent E2 shadow runtime may explicitly select
`development_offhost_ack`; its ordinary bounded finalizer uses the same exact named-standby evidence as the
verifier fixture while health remains `development_offhost_ack_cp3_d_not_proven`. It does not establish an
external failure domain or CP3-D. Projections can replace only disposable Board rows/cursors and
cannot mutate authority. Runtime materializes authored fixed-operation jobs and the approved dream/beat
effects; it does not execute external dream work or inject fleet prompts. The neutral Object port is shared
by injected Proof and Catalog capabilities; Proof retains
digest-bound inline/external object metadata, safe backfill, and durable erasure tombstones without owning
the generic protocol. Record owns immutable backup/anchor/inventory/restore evidence and exact
installation/report enablement policy. Review dispatch binds the emitted author model family and derives the
reviewer model family from the authenticated principal's immutable registration; it remains intent-only and
the kernel never launches the reviewer. The local recovery checkpoint does not activate production objects,
backups, executable effects,
or external targets; Catalog declarations do not activate Effects, synthetic
handlers, or the remaining I1/I2 runtimes.
CompanyBundle validate, plan, and export remain authenticated read operations, including for Commander,
while apply requires current operator/platform-administrator authority. Apply resolves exact
principal-command replay, locked base and plan equivalence, and unsupported removal/deprecation before
staging immutable payloads; an exact replay returns its stored result without consulting the Object port.
I1 additive and successor activation remains supported, but lifecycle removal/deprecation is a typed refusal
that leaves the prior active Catalog authoritative.

Thread-first intake accepts any project already declared in the tenant's Project Delivery hierarchy;
ordinary mutations pass through the shared project-mutation authority, which allows operators and otherwise
requires an active matching project-seat grant. Ticket creation and link validation use the
immutable `tickets.project_key` authority; `ticket_project_bindings` records import/intake provenance and is
never a fallback authority. Source aliases include project in their canonical identity; there is no
intake-only project ledger. Complete sorted durability-subject locks
precede thread/ticket locks, and only authenticated, unquarantined discussion events may be promoted. The
Record package facade keeps core authority types at `ctower_kernel.record` and groups inbound-thread command,
result, and policy types under the exported `ctower_kernel.record.intake` namespace instead of flattening
those leaf symbols.

Work also owns the Phase-1 Request aggregate. Record persistence atomically allocates one tenant-wide
permanent `R<number>`, records inbound provenance plus initial facts, and returns the existing honest
durability result without creating a Ticket. Priority, triage, owner, Ticket relation, blocker, and closure
evaluation are independent expected-version facts; operator state is derived. Accepted reads name their
Record watermark and distinguish unanswered projects from empty projects. The one-time ledger helper is
outside the kernel and has no Record connection.

The native morning digest remains in `projections/`. Its pure fold accepts typed Request and Ruling readings
plus their watermarks and unreached scopes. It emits one Europe/Vilnius artifact with record-derived open
decision briefs, prior-day Rulings and typed Request executions, then related Ticket timeline proof links.
It owns no persistence, source client, clock authority, renderer, scheduler, or notification transport.
Unavailable sources and unresolved relations remain explicit partial or unknown results; an authoritative
absent relation is empty.

Console Phase 1 is isolated in `console/`. `ConsoleViewer` is the small public Interface over a pure exact
grant decision, append-only PostgreSQL authority, encrypted output custody, and an injected read-only runtime
Adapter. Commander Actors and disabled or Commander-owned target sessions are absent. The authority rejoins the current
assignment and recorded work session, rechecks the complete current human/session/policy authority before a
first stream claim consumes the newest grant, and persists allowances, denials, explicit bounded suspension
facts, human-bound one-use grants, stream claims/closes, revocations, global switch facts, encrypted cursors,
reader accesses and one-use recovery facts, gaps, and live Adapter observations. `ConsolePolicy` has no defaults and enforces the
five-minute grant, thirty-minute continuous-view, four-second authority poll, 16 KiB chunk, 1 MiB/min
delivery/replay, and 256 KiB pending ceilings. The API owns the bounded pending queue so blocked ASGI sends
cannot stop authority polling. Per-allowance output and gap collection is single-writer across processes;
output and gap facts share durable source order, and truncation advances a source generation before a
numeric source cursor may recur. Each output object has a fresh AES-GCM data key wrapped under a referenced
key-encryption key; the service commits an access-attempt fact before invoking the dedicated
`console_output_reader`-owned recovery function, which consumes the access ID into an immutable recovery
fact and returns only the joined object once. Replay recovers one object per cycle and rechecks authority
before the next. It then decrypts only data returned through that custody path. The kernel imports no app, web,
CLI, tmux, or process implementation and contains no input authority.

Knowledge registers immutable org- or project-scoped document snapshots through its small public Interface.
Org writes require operator authority; project writes and reads reuse Record's persisted project-seat checks.
The static-file Adapter resolves only bounded UTF-8 Markdown below its injected scope root and returns typed
source records; composition decides whether to mount it. Authority facts retain the stable source reference
and resolved content, while list/get consume a disposable projection.

Native Inbox is a two-principal thread aggregate. Record atomically appends `thread.opened`,
`message.appended`, and `thread.promoted_to_ticket` facts; promotion either composes a Record-owned P2 ticket
creation from the immutable thread head under ordinary initial-custody policy or binds an existing in-scope
ticket, then writes one immutable link exposed from both the thread projection and the Board card. Ordered
messages and promotion links remain authoritative, while recipient unread/read cursors and list/read rows
are disposable and rebuildable. The notification ingress is a second, narrow command shape over that same
authority: it resolves sender from the authenticated Actor, recipient from the persisted seat registry, and
derives one direction-independent thread per principal pair. A stable delivery UUID is the existing command
idempotency key; it does not add a pair store, message kind, caller-supplied sender, or identity creation.

Integrations owns the provider-neutral two-method `IssueConnector` Interface and its PostgreSQL cursor/
custody/observation/delivery store. Its only composed implementation is the deliberately narrow GitLab Issue
co-source. A due tick processes at most one issue page and one project-event page under a leased, fenced
claim. New issues enter through ordinary external-untrusted Work intake, labels through BoardContext, and
changes through Record comments. An external issue state never changes ctower lifecycle. Only Record's
canonical proof-gated `resolve_close` event may request the API-owned Adapter to comment and close the
provider issue; an immutable event receipt and marker make replay converge. Cursor rows are usable only
while their exact Catalog component revision and digest remain active. The Module contains no provider
config, cursor interpretation, HTTP/credential handling, app import, or dynamic plugin framework.

There is no executable Extension Host in I1 or I2; that runtime remains deferred until a real use case and
two real Adapters earn its Seam. The kernel may depend on authored/generated contracts and allowlisted public
Module Interfaces, never on apps, runner/provider implementations, web, CLI, or mutable YAML state.
