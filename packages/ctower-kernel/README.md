# ctower-kernel boundary

Trusted modular-monolith artifact. The development walking slice implements small Access, Record, Work,
Proof, and Workflow Interfaces: authentication and bootstrap authority; atomic Postgres
command/event/outbox persistence; ticket priority/custody policy; frozen criteria, digest-bound evidence,
protected verdicts and selective invalidation; and pinned legal graph movement plus proof-gated atomic
resolve/close.

Record is the lower append Interface and depends only on Telemetry. Proof and Workflow each own their SQL
implementation and depend downward on Record; Workflow does not import Proof. Composition injects
PostgresProof's narrow current-proof capability into PostgresWorkflow, keeping the repository dependency
graph acyclic. Catalog, Attention, Runtime, Effects, Projections, and the rest of I1/I2 remain deferred.

There is no executable Extension Host in I1 or I2; that runtime remains deferred until a real use case and
two real Adapters earn its Seam. The kernel may depend on authored/generated contracts and allowlisted public
Module Interfaces, never on apps, runner/provider implementations, web, CLI, or mutable YAML state.
