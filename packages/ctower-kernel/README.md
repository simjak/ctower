# ctower-kernel boundary

Trusted modular-monolith artifact. The development walking slice implements small Access, Catalog, Record,
Work, Proof, Workflow, Runtime, Projections, Attention, and generic Object Interfaces: authentication and
bootstrap authority; atomic Postgres command/event/outbox persistence; ticket lifecycle, comments, priority,
custody, assignment, blocker, relation, and typed-intent policy; universal component/bundle
validation/planning plus an atomic future-only Catalog pointer; server-pinned frozen criteria, digest-bound
evidence, protected verdicts and selective
invalidation; explicitly pinned legal graph movement plus proof-gated atomic resolve/close that releases
every current-episode ownership interval; and a disposable six-lane
Board fold over accepted outbox records; immutable delivery attempts, poison, deduplicated Attention findings,
canonical acceptance-gated recovery dispositions; fixed Routine occurrences/jobs with event/result/outbox
lineage; and independently attributable health.

Record is the lower append Interface and depends only on Telemetry. Work, Proof, and Workflow each own their
SQL implementation and depend downward on Record; Workflow imports neither Work nor Proof. Composition
injects their narrow readiness/current-proof capabilities into Workflow, keeping the repository dependency
graph acyclic. Record also owns the typed durability decision, RFC-8785/SHA-256 semantic command root,
subject-head dependency refusal, immutable named-standby acknowledgement, and fail-closed health snapshot.
Exact durability identity is `(tenant, principal, command)`. Accepted replay is authorized by a distinct
immutable finalization exactly bound to the complete acknowledgement receipt plus confirmation that the
same finalization was read from the named standby; merely primary-local acknowledgement/finalization state
remains pending. Subject serialization uses one global order: sorted advisory locks only for absent heads, sorted
`durability_subject_heads` row locks, then aggregate locks, all held through refusal or commit. Live health
uses two fixed-search-path, narrowly executable probes owned by a quarantined no-login statistics role;
its schema-CREATE and administration-assumption authority end after probe creation, unsafe pre-existing
authority is rejected, and NULL or malformed live evidence degrades with a typed reason. `ctower_svc`
does not inherit PostgreSQL monitor roles.
Its default policy remains `pending_only`; accepted behavior is exercised only by the verifier-owned local
PostgreSQL 17 primary/hot-standby fixture. Projections can replace only disposable Board rows/cursors and
cannot mutate authority. Runtime materializes only the three authored fixed-operation jobs; it does not
dispatch them. The neutral Object port is shared by injected Proof and Catalog capabilities; Proof retains
digest-bound inline/external object metadata, safe backfill, and durable erasure tombstones without owning
the generic protocol. Record owns immutable backup/anchor/inventory/restore evidence and exact
installation/report enablement policy. The local recovery checkpoint does not activate production
objects, backups, effects, or external targets; Catalog declarations do not activate Effects, synthetic
handlers, or the remaining I1/I2 runtimes.
CompanyBundle validate, plan, and export remain authenticated read operations, including for Commander,
while apply requires current operator/platform-administrator authority. Apply resolves exact
principal-command replay, locked base and plan equivalence, and unsupported removal/deprecation before
staging immutable payloads; an exact replay returns its stored result without consulting the Object port.
I1 additive and successor activation remains supported, but lifecycle removal/deprecation is a typed refusal
that leaves the prior active Catalog authoritative.

Thread-first intake is bounded to the already-declared `ctower` project in the tenant's Project Delivery
hierarchy because I1 has no separate actor-to-project grant authority. Ticket creation and link validation
use the existing immutable `ticket_project_bindings` authority for both migration and intake provenance;
there is no intake-only project ledger. Complete sorted durability-subject locks precede thread/ticket
locks, and only authenticated, unquarantined discussion events may be promoted. The Record package facade
keeps core authority types at `ctower_kernel.record` and groups inbound-thread command, result, and policy
types under the exported `ctower_kernel.record.intake` namespace instead of flattening those leaf symbols.

There is no executable Extension Host in I1 or I2; that runtime remains deferred until a real use case and
two real Adapters earn its Seam. The kernel may depend on authored/generated contracts and allowlisted public
Module Interfaces, never on apps, runner/provider implementations, web, CLI, or mutable YAML state.
