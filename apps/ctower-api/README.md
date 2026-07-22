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
contributors, and the optional Attention composition exposes append-only retry/tombstone poison recovery.
Real backup, anchor, object, and synthetic effects, a production off-host target, and deployment remain deferred.
The common mutation envelope threads the authenticated principal into every Record reconciliation call, so
same-tenant principals may independently reuse the same command UUID without weakening exact replay.
