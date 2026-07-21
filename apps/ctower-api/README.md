# ctower-api boundary

Python composition root for the development walking slice. Its FastAPI handlers validate generated HTTP
models and call the public Access, Work, Record, Proof, and Workflow Interfaces for bootstrap, ticket
create/read, protected custody transfer, typed task commands, assignment/audit queries, explicit Workflow
start, proof commands, legal transitions, proof-gated close, and the read-only Board projection.
Durable decisions remain in the owning kernel Modules; the API never connects around those Interfaces.
Work and Proof implementations are injected into Workflow only as narrow readiness/current-proof
capabilities at composition. Board catch-up is a development-request tracer over a separately privileged
projection connection; the background worker, accepted durability health, and production deployment remain
deferred.
