# Project status

ctower is a public, docs-first pre-alpha project. Implementation has started with repository gates,
contracts, and compatibility evidence, but the runtime product is not implemented and cannot yet manage
real work.

## Available now

- The canonical system specification, architecture atlas, append-only decisions, and implementation
  roadmap.
- Authored JSON Schema contracts for bootstrap, telemetry, workflows, review plans, and supporting domain
  envelopes.
- Example versioned workflow, execution-policy, and gate-policy packs.
- A repository policy module with ownership, source-budget, generated-drift, and secret checks.
- A strict Python compatibility preflight with authored input/result schemas and a sanitized evidence
  writer.
- Twenty-seven compatibility tests measured at 97.05% branch coverage.
- Deterministic traceability from `contracts/traceability/sources.json` to
  `generated/traceability-index.json`, including generated-manifest drift checks.
- A low-operations MkDocs Material documentation site and pinned GitHub Actions workflow for GitHub Pages.
- Source-only SemVer and Release Please automation at the `0.0.0` development baseline.
- Coding, observability, and secret-handling standards.

These assets establish the contract for implementation. They are not a working control plane.

## Compatibility evidence, not a runtime decision

The 2026-07-19 preflight ran standard-GIL CPython 3.12.13, 3.13.14, and 3.14.6 in two environments:
isolated macOS on `x86_64` and immutable Linux containers on `arm64`. All six rows passed all ten required
observations. The exact input, result rules, and sanitized evidence table live under
[`contracts/compatibility/`](https://github.com/simjak/ctower/tree/main/contracts/compatibility).

This evidence does not select or pin ctower's Python runtime. Linux `amd64`, the future release-helper
wheel, and generated clients remain unexercised. There is no accepted project lock, `.python-version`,
fallback choice, or decision superseding D6.

GitHub Pages is the chosen public documentation UI because a static, searchable site can be built on every
pull request and published from trusted `main` without operating another service. Publishing that site
proves only that the documentation built and deployed; it does not prove a ctower runtime exists.

## Not available yet

- A running API or control worker.
- Durable ticket storage, workflow evaluation, leases, fencing, effects, or projections.
- A supported CLI, web interface, installer, container image, or hosted service.
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
