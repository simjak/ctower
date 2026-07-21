# ctower-kernel boundary

Trusted modular-monolith artifact. The development walking slice implements small Access, Record, Work,
Proof, Workflow, and Projections Interfaces: authentication and bootstrap authority; atomic Postgres
command/event/outbox persistence; ticket lifecycle, priority, custody, assignment, blocker, relation, and
typed-intent policy; frozen criteria, digest-bound evidence, protected verdicts and selective invalidation;
explicitly pinned legal graph movement plus proof-gated atomic resolve/close; and a disposable six-lane
Board fold with loud source/projection watermark health.

Record is the lower append Interface and depends only on Telemetry. Work, Proof, and Workflow each own their
SQL implementation and depend downward on Record; Workflow imports neither Work nor Proof. Composition
injects their narrow readiness/current-proof capabilities into Workflow, keeping the repository dependency
graph acyclic. Projections can replace only disposable Board rows/cursors and cannot mutate authority.
Catalog, Attention, Runtime, Effects, the background projection worker, and the rest of I1/I2 remain
deferred.

There is no executable Extension Host in I1 or I2; that runtime remains deferred until a real use case and
two real Adapters earn its Seam. The kernel may depend on authored/generated contracts and allowlisted public
Module Interfaces, never on apps, runner/provider implementations, web, CLI, or mutable YAML state.
