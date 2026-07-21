# Project status

ctower is a public pre-alpha project. The development-only local walking slice now exercises bootstrap,
durable ticket and Board facts, custody, an online CLI, a read-only Board projection, and the CP-1
proof-gated four-stage fixture. It is not a supported or deployed product and must not yet manage real
work.

## Delivery snapshot

I1.2 is merged: PR [#20](https://github.com/simjak/ctower/pull/20) integrated reviewed source
`78ec2a8` into `main` at `65718f5a` on 2026-07-21. It establishes the development-only CP2 durable Work,
Workflow, Proof, Board, assignment, priority, blocker, relation, audit, and projection-role boundary. The
next checkpoint is I1.3, acknowledged durability and disaster-safe operations. This snapshot records
delivery facts. The
[implementation roadmap](https://github.com/simjak/ctower/blob/main/IMPLEMENTATION-ROADMAP.md) is a
derived sequencing view; binding scope and exit semantics live in the
[system specification](https://github.com/simjak/ctower/blob/main/SPEC.md), with rationale preserved in
[DECISIONS.md](https://github.com/simjak/ctower/blob/main/DECISIONS.md).

## Available now

- The canonical system specification, architecture atlas, append-only decisions, and implementation
  roadmap.
- Authored JSON Schema contracts for bootstrap, telemetry, Workflow graphs, the CP-1 execution/gate/evidence
  policy consumer subset, evidence manifests, review plans, and supporting domain envelopes.
- Example versioned workflow, execution-policy, and gate-policy packs.
- A repository policy module with ownership, source-budget, generated-drift, and secret checks.
- Strict Python compatibility input/result schemas, frozen typed models, closed-world report validation,
  exact topology binding, and a sanitized no-follow atomic evidence writer. There is no public native
  execution seam; executable evidence is deferred to a future disposable runner or VM adapter.
- Compatibility tests with a hard 90% new-code branch-coverage gate.
- Deterministic traceability from `contracts/traceability/sources.json` to
  `generated/traceability-index.json`, including generated-manifest drift checks.
- A low-operations MkDocs Material documentation site and pinned GitHub Actions workflow for GitHub Pages.
- Source-only SemVer and Release Please automation at the `0.0.0` development baseline.
- A reproducible, fork-safe `release gate` with immutable verification inputs, generated-root exactness,
  required-suite accounting, and intended-tree plus complete-history secret scans.
- Coding, observability, and secret-handling standards.
- Checksum-ordered subset migrations for a Postgres 17 development fixture with separate migrator,
  service, and projection roles.
- One-use local first-tenant bootstrap that creates the tenant, disabled historical bootstrap principal,
  operator, durable Commander identity, vault references, event/outbox, and exact replay receipt atomically.
- Tenant-scoped ticket create/read/timeline with P0/P1/P2 policy, exact command replay, hash-chained events,
  transactional outbox writes, and explicit `durability_pending` results.
- Protected operator custody transfer with exact-current `from`, version CAS, gapless interval replacement,
  same-tenant eligible targets, concurrent one-winner behavior, and restart retrieval.
- A development-only generic Workflow evaluator for the staged `ctower.trust-spine-four-stage@1` fixture,
  with pinned legal edges and `activity_class`; plus Proof criteria freeze, content-digest verification,
  protected non-self verdicts, dependency invalidation, and proof-gated atomic resolve/close facts.
- Durable Work facts for assignment, P0/P1/P2 priority, blockers, relations, workflow/policy pins, and
  audit cursor retrieval; the development-only request tracer rebuilds a six-lane Board with loud source
  and projection watermarks.
- Work, Proof, and Workflow own their Postgres implementations above the lower Record append Interface.
  Workflow receives only injected Work-readiness and current-proof capabilities, and the executable
  repository graph rejects cycles. The projection role can replace disposable Board rows and cursors but
  cannot mutate authoritative facts.
- A thin online `ctowerctl` tracer over the deterministic generated Python client for bootstrap and ticket
  create/show/assign. Authority enters on stdin; offline mutations fail loudly as unsent.

These assets and the synthetic tracer establish the first executable vertical. They are not a supported,
deployed, or off-host-durable control plane.

## Compatibility evidence, not a runtime decision

The 2026-07-19 local preflight ran standard-GIL CPython 3.12.13, 3.13.14, and 3.14.6 in two environments:
unconfined macOS on Darwin `arm64` and immutable Linux containers on `arm64`. All six rows observed all ten
checks, but the report has been reclassified as noncanonical diagnostic evidence. The exact input, result
rules, and historical table live under
[`contracts/compatibility/`](https://github.com/simjak/ctower/tree/main/contracts/compatibility).

This historical diagnostic does not select or pin ctower's Python runtime. A contained runner with
attestable provenance, Linux `amd64`, the future release-helper
wheel, and generated clients remain unexercised. There is no accepted project lock, `.python-version`,
fallback choice, or decision superseding D6.

GitHub Pages is the chosen public documentation UI because a static, searchable site can be built on every
pull request and published from trusted `main` without operating another service. Publishing that site
proves only that the documentation built and deployed; it does not prove a ctower runtime exists.

## Not available yet

- A supported/deployed API, control worker, installer, container image, or hosted service.
- Off-host acknowledgement, backup/restore proof, outbox consumption, general workflow/runtime execution,
  leases, fencing, effects, or a durable projection worker. The current request-driven Board projection is
  development-only and does not establish accepted durability.
- A supported CLI, encrypted offline spool, or web interface.
- Local or remote agent execution adapters.
- An accepted Python runtime pin or stable compatibility promise.
- An installable package, deployable artifact, or production release. The current release automation is
  configured to create source tags and release notes only.

## Delivery path

```text
repository foundation
        |
        v
trusted control plane -> one durable ticket -> restore proof
        |
        v
CLI + thin UI -> source-of-truth cutover for ctower itself
        |
        v
workflow + runtime -> Commander automation -> protected release
        |
        v
ctower releases and retros its own feature
```

Dogfooding advances in five explicit levels:

1. **Repository gates:** every change passes ctower's own architectural and quality policies.
2. **Synthetic tickets:** the first vertical path uses disposable fixture data.
3. **Shadow import:** ctower reconciles a copy of its backlog without accepting writes.
4. **Hard cutover:** mutation freezes, data reconciles once, clients switch atomically, and the prior
   tracker becomes read-only. There is no dual-write period.
5. **Autonomous factory:** ctower carries its own feature through production proof and retro.

For exact phase exits, read the
[implementation roadmap](https://github.com/simjak/ctower/blob/main/IMPLEMENTATION-ROADMAP.md). For binding
scope and acceptance criteria, read the
[system specification](https://github.com/simjak/ctower/blob/main/SPEC.md).
