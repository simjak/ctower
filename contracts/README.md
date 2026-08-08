# Authored contracts

This is the only authored schema home. Contracts are strict, versioned, immutable after publication, and fail closed on unknown fields. Generated Python/TypeScript models and clients belong under `generated/`; applications do not hand-maintain parallel wire types.

The tree contains both contracts exercised by the current development walking slice and deferred L0 schemas.
The authored OpenAPI, first-tenant, event-envelope, and telemetry contracts drive deterministic Python and
TypeScript generation plus contract and acceptance tests. Both generated clients strictly validate
operation-specific success and problem responses at runtime; another schema's presence alone does not claim
runtime behavior. The one-use first-tenant body contract lives under `bootstrap/`, while its transport
contract is authored in OpenAPI and implemented by the current setup helper, API, Access, and Record
composition.

The Knowledge contract under `domain/knowledge/` defines strict org/project scope, stable source references,
direct-versus-source registration, immutable document snapshots, and add/list/get payloads. OpenAPI owns the
three public operations and their CLI metadata; deterministic generation produces the Python and TypeScript
models and clients used by the API and protected CLI.

The development-only CP-1 consumer subset keeps graph and transition authority under `workflow/`, owns its
execution, gate, and evidence policy schemas under the single `execution/` home, and owns the strict
current-proof/deferred-source manifest under `evidence/`. Workflow v2 adds declared stage-entry
review-dispatch intents, while the HTTP contract exposes their substrate consumption without accepting
caller-authored family labels, plus the bound model-family facts and ticket-visible verdict join. This
records control-plane intent only; it does not activate remote execution, images,
executable extensions, or off-host durability.

Routine v2 adds the four exact nightly dream packs and a strict dream-dispatch effect/read/consume HTTP
contract. Consumption carries only the output digest; the emitted effect owns model requirements and the
kernel copies executing-lane facts from substrate bindings.

The CP2 task-management contracts under `domain/task-management/` fix typed Work commands, five assignment
kinds, the six-lane Board view and watermark health, and a deterministic priority-aging selection policy.
The scheduling pack selects among eligible work only; it neither dispatches jobs nor advances Workflow.

The CP3-B Runtime contracts under `runtime/` define content-addressed Routine revisions, visible DST
offset decisions and outcomes, and fixed pending-only jobs. `runtime/routine-vectors.json` is the
deterministic digest and DST/refusal vector set; canonical occurrence and poison-disposition events remain
under the single `domain/events/` authority.

The I1.4 CompanyBundle contract under `company/` carries strict portable desired state: one tenant identity,
complete VersionedComponent envelopes, inline non-secret payloads, assignments, and secret-reference names.
Category schemas include the current configuration kinds, while generated `ctower_contracts` packages them
as a local-only runtime resource with network/path-escape `$ref` refusal. Contract presence does not
activate runners, executable effects, external targets, or production configuration.
