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
graph acyclic. Record also owns the typed durability decision, RFC-8785/SHA-256 semantic command root,
subject-head dependency refusal, immutable named-standby acknowledgement, and fail-closed health snapshot.
Exact durability identity is `(tenant, principal, command)`. Accepted replay is authorized by a distinct
immutable finalization bound to the replay-visible acknowledgement; merely local acknowledgements remain
pending. Subject serialization uses one global order: sorted advisory locks only for absent heads, sorted
`durability_subject_heads` row locks, then aggregate locks, all held through refusal or commit. Live health
uses two fixed-search-path, narrowly executable probes owned by a no-login statistics role; `ctower_svc`
does not inherit PostgreSQL monitor roles.
Its default policy remains `pending_only`; accepted behavior is exercised only by the verifier-owned local
PostgreSQL 17 primary/hot-standby fixture. Projections can replace only disposable Board rows/cursors and
cannot mutate authority. Catalog, Attention, Runtime, Effects, the background projection worker, and the
rest of I1/I2 remain deferred.

There is no executable Extension Host in I1 or I2; that runtime remains deferred until a real use case and
two real Adapters earn its Seam. The kernel may depend on authored/generated contracts and allowlisted public
Module Interfaces, never on apps, runner/provider implementations, web, CLI, or mutable YAML state.
