# Authored contracts

This is the only authored schema home. Contracts are strict, versioned, immutable after publication, and fail closed on unknown fields. Generated Python/TypeScript models and clients belong under `generated/`; applications do not hand-maintain parallel wire types.

The tree contains both contracts exercised by the current development walking slice and deferred L0 schemas.
The authored OpenAPI, first-tenant, event-envelope, and telemetry contracts drive deterministic Python
generation plus contract and acceptance tests; another schema's presence alone does not claim runtime
behavior. The one-use first-tenant body contract lives under `bootstrap/`, while its transport contract is
authored in OpenAPI and implemented by the current setup helper, API, Access, and Record composition.

The development-only CP-1 consumer subset keeps graph and transition authority under `workflow/`, owns its
execution, gate, and evidence policy schemas under the single `execution/` home, and owns the strict
current-proof/deferred-source manifest under `evidence/`. These schemas exercise only the four-stage local
fixture. They do not activate remote execution, images, effects, executable extensions, or off-host
durability.

The CP2 task-management contracts under `domain/task-management/` fix typed Work commands, five assignment
kinds, the six-lane Board view and watermark health, and a deterministic priority-aging selection policy.
The scheduling pack selects among eligible work only; it neither dispatches jobs nor advances Workflow.

The CP3-B Runtime contracts under `runtime/` define content-addressed Routine revisions, visible DST
offset decisions and outcomes, and fixed pending-only jobs. `runtime/routine-vectors.json` is the
deterministic digest and DST/refusal vector set; canonical occurrence and poison-disposition events remain
under the single `domain/events/` authority.
