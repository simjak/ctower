# ctower-api boundary

Python composition root for the development walking slice. Its FastAPI handlers validate generated HTTP
models and call the public Access, Work, Record, Proof, Workflow, Projections, and Attention Interfaces for bootstrap, ticket
create/read, protected custody transfer, typed task commands, assignment/audit queries, explicit Workflow
start, proof commands, legal transitions, proof-gated close, and the read-only Board projection.
Durable decisions remain in the owning kernel Modules; the API never connects around those Interfaces.
Work and Proof implementations are injected into Workflow only as narrow readiness/current-proof
capabilities at composition. Board reads return only stored accepted-state projection rows; request handlers
never catch up the projection. One common mutation envelope asks Record to reconcile the exact command root and
returns either replayable `durability_pending` or the original semantic result as accepted; normal/default
configuration remains `pending_only`. The same artifact exposes `ctower-control-worker`, which owns the
fixed Routine scan and accepted-outbox projection loops. Authenticated health reports independent
contributors, and the optional Attention composition exposes canonical, acceptance-gated append-only
retry/tombstone poison recovery with exact command replay.
The artifact also contains private fixed-shape object/KMS/backup Adapters and isolated-restore quarantine
composition for deterministic local CP3-C proof. They accept references and typed receipts, never
application-owned signing keys or arbitrary commands. Real off-host targets, system activation, synthetic
effects, production drills, and deployment remain deferred to CP3-D.
The common mutation envelope threads the authenticated principal into every Record reconciliation call, so
same-tenant principals may independently reuse the same command UUID without weakening exact replay.
