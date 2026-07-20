# ctower-kernel boundary

Trusted modular-monolith artifact. The development walking slice implements small Access, Record, and Work
Interfaces: authentication and bootstrap authority; atomic Postgres command/event/outbox persistence; and
ticket priority/custody policy. Catalog, Proof, Attention, Runtime, Effects, Workflow, Projections, and the
rest of I1/I2 remain deferred.

There is no executable Extension Host in I1 or I2; that runtime remains deferred until a real use case and
two real Adapters earn its Seam. The kernel may depend on authored/generated contracts and allowlisted public
Module Interfaces, never on apps, runner/provider implementations, web, CLI, or mutable YAML state.
