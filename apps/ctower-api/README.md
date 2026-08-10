# ctower-api boundary

Python composition root for the development walking slice. Its FastAPI handlers validate generated HTTP
models and call the public Access, Catalog, Knowledge, Work, Record, Proof, Workflow, Projections, and Attention
Interfaces for bootstrap, ticket create/read/comment, protected custody transfer, typed task commands,
assignment/audit queries, the project-scoped typed event feed, CompanyBundle validate/plan/apply/export,
explicit Workflow start,
server-policy-pinned proof commands, legal transitions, ownership-releasing proof-gated close, and the
read-only Board projection. The API also exposes explicit
`discussion|create_ticket|link_ticket` thread-first intake and one-time discussion promotion. Both intake
routes authenticate before reading a body, then enforce the same 524,288-byte streaming limit without
trusting `Content-Length`.
The separately composed native Inbox surface exposes message send, recipient-only delivery/read
acknowledgement, participant-only ticket promotion, recipient-scoped thread list, ordered thread read, and
per-message read-state. Its notification ingress accepts only recipient seat and text, derives the sender
from the authenticated Actor, resolves the recipient from the persisted seat registry, and groups messages
in the direction-independent thread for that principal pair. The request's idempotency key is the stable
notification delivery UUID, so retry returns the original result. Promotion atomically creates a P2 ticket from the thread head when no ticket is
named, or links an existing in-scope ticket when one is named. Send, acknowledgement, and promotion are
protected durable mutations. The reads consume only accepted disposable projection state and never advance
a cursor; unread and read-through derive from append-only recipient facts.
The Knowledge surface exposes explicit document add/list/get operations. Registration accepts either a
bounded direct snapshot or a stable static-source reference, persists the resolved snapshot as an immutable
fact, and authorizes project scope from the persisted project-seat authority. The development composition
mounts the kernel's bundled static-file Adapter; handlers never read arbitrary filesystem paths.
Durable decisions remain in the owning kernel Modules; the API never connects around those Interfaces.
The Request routes are the same thin composition: capture and six expected-version fact commands delegate
to Work, while list is accepted-only and read-only. Payloads cannot claim Actor, owner, source, number, or
state, and no ordinary Request import route exists.
The operator-only morning-digest route independently reads the injected Request and Ruling authorities and
passes their typed outcomes to the pure kernel fold. A source refusal becomes a named unknown scope in the
successful artifact; authentication, role, and malformed-date failures remain transport problems. The route
stores nothing and owns no scheduler or notification delivery.
Work and Proof implementations are injected into Workflow only as narrow readiness/current-proof
capabilities at composition. Board reads return only stored accepted-state projection rows; request handlers
never catch up the projection. One common mutation envelope asks Record to reconcile the exact command root and
returns either replayable `durability_pending` or the original semantic result as accepted; normal/default
configuration remains `pending_only`. The same artifact exposes `ctower-control-worker`, which owns the
fixed Routine scan and accepted-outbox projection loops. Authenticated health reports independent
contributors, and the optional Attention composition exposes canonical, acceptance-gated append-only
retry/tombstone poison recovery with exact command replay.
The development composition also exposes the four nightly dream-dispatch effects. Listing is filtered by
the authenticated principal's persisted Project scope; only an operator receives the operator-only fleet
effect. Consumption accepts only an output digest, refuses foreign-Project and non-operator fleet effects
before mutation, and records substrate-bound lane/model facts plus the Routine occurrence link through the
Runtime Interface. The same boundary exposes the online-only operator `dream-lane bind` ceremony: it
derives the principal from authentication and atomically appends one event plus one immutable lane binding;
non-operators and second bindings receive typed refusals.
The same composition exposes the five registered fleet-beat revisions and their immutable effects through
operator-only reads. The registration read includes exact UTC minute/hour marks and next fire time. Each
effect carries the full digest-verified prompt baked into the revision and the fixed `commander` target; the
API neither injects tmux input nor accepts a delivery claim. Server-side delivery custody remains absent
until a separately authorized lane-binding ceremony exists.
The artifact contains a closed first-party connector registry whose only admitted implementation is the real
GitLab v4 HTTP Adapter for the narrow GitLab Issue co-source. A strict Catalog v2 payload becomes an
immutable runtime binding plus an unresolved secret-reference name; deployment supplies the resolved token
directly to composition, never to Catalog or persistence. The control-worker entry point exports the active
bundle, resolves each declared runtime binding, and injects one independently pinned loop per active GitLab
registration, which the worker ticks once per worker tick. Each registration's durable opaque cursor
suppresses early work and bounds provider/event pages. The HTTP Adapter has no record-tier connection, and
the provider-neutral kernel sync service has no provider import. No other provider or dynamic plugin loading
is active.
The separately approved E2 composition exposes `ctower-development-api` and
`ctower-development-worker`. It resolves Secret Service references in-process, binds the API to loopback,
and adds Record's bounded ordinary durability finalizer to the same worker loop. Its
`development_offhost_ack` health is deliberately degraded as
`development_offhost_ack_cp3_d_not_proven`; it is never a production or authority-promotion composition.
The artifact also contains private fixed-shape object/KMS/backup Adapters and isolated-restore quarantine
composition for deterministic local CP3-C proof. They accept references and typed receipts, never
application-owned signing keys or arbitrary commands. Real off-host targets, system activation, synthetic
effects, production drills, and deployment remain deferred to CP3-D.
The common mutation envelope threads the authenticated principal into every Record reconciliation call, so
same-tenant principals may independently reuse the same command UUID without weakening exact replay.
Catalog receives the same injected generic object capability as Proof; API composition does not create a
second object store. Bundle validate/plan/export are read-only, while apply retains auth-before-validation,
Record-owned command/event/outbox durability, locked-base re-planning, and an atomic future-only pointer.
Commander apply is rejected before Catalog or object effects. The private immutable-object Adapter persists
receipt metadata beside ciphertext so a retry after an interrupted successful write can verify and reconcile
the same object without another KMS encryption or object PUT; ordinary exact command replay is resolved by
Record before that Adapter is called.
