# ctower-api boundary

Python composition root for the development walking slice. Its FastAPI handlers validate generated HTTP
models and call the public Access, Work, Record, Proof, and Workflow Interfaces for bootstrap, ticket
create/read/timeline, protected custody transfer, proof commands, legal transitions, and proof-gated close.
Durable decisions remain in the owning kernel Modules; the API never connects around those Interfaces.
The Proof implementation is injected into Workflow only as a narrow current-proof capability at
composition. Projections, health, and the control worker remain deferred.
