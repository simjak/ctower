# ctower-api boundary

Python composition root for the development walking slice. Its FastAPI handlers validate generated HTTP
models and call the public Access, Catalog, Work, Record, Proof, Workflow, Projections, and Attention
Interfaces for bootstrap, ticket create/read/comment, protected custody transfer, typed task commands,
assignment/audit queries, the project-scoped typed event feed, CompanyBundle validate/plan/apply/export,
explicit Workflow start,
server-policy-pinned proof commands, legal transitions, ownership-releasing proof-gated close, and the
read-only Board projection. The API also exposes explicit
`discussion|create_ticket|link_ticket` thread-first intake and one-time discussion promotion. Both intake
routes authenticate before reading a body, then enforce the same 524,288-byte streaming limit without
trusting `Content-Length`.
The separately composed native Inbox surface exposes exactly message send, recipient-scoped thread list,
and ordered thread read. Send is a protected durable mutation; list and read consume only accepted disposable
projection state, and read advances only that authenticated principal's disposable cursor.
Durable decisions remain in the owning kernel Modules; the API never connects around those Interfaces.
Work and Proof implementations are injected into Workflow only as narrow readiness/current-proof
capabilities at composition. Board reads return only stored accepted-state projection rows; request handlers
never catch up the projection. One common mutation envelope asks Record to reconcile the exact command root and
returns either replayable `durability_pending` or the original semantic result as accepted; normal/default
configuration remains `pending_only`. The same artifact exposes `ctower-control-worker`, which owns the
fixed Routine scan and accepted-outbox projection loops. Authenticated health reports independent
contributors, and the optional Attention composition exposes canonical, acceptance-gated append-only
retry/tombstone poison recovery with exact command replay.
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
