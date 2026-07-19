# Development guide

ctower is built as a walking system: one complete, durable path before platform breadth. Contributions must
preserve that sequence and the distinction between authored semantics, executable contracts, and generated
outputs.

## Before changing code or contracts

1. Read the relevant section of the canonical
   [system specification](https://github.com/simjak/ctower/blob/main/SPEC.md).
2. Check the append-only [decision log](https://github.com/simjak/ctower/blob/main/DECISIONS.md).
3. Identify the owning Module and its permitted dependency edges in `tools/checks/policy.toml`.
4. Confirm that the change belongs to the current implementation increment.
5. Define failure, restart, authorization, idempotency, and evidence behavior before adding a happy path.

Do not introduce a public extension interface for a single fake implementation. A Seam is earned only when
two real, independently useful adapters need the same contract.

## Repository authority

| Content | Authoritative home |
|---|---|
| Human-visible system semantics and acceptance criteria | `SPEC.md` |
| Historical decisions and supersessions | `DECISIONS.md` |
| Compact derived architecture views | `ARCHITECTURE.md` |
| Checkpoint and dogfooding sequence | `IMPLEMENTATION-ROADMAP.md` |
| Cross-process schemas | `contracts/` |
| Concrete workflow and policy versions | `packs/` |
| Generated clients, models, and indexes | `generated/` |
| Physical persistence implementation | `packages/ctower-kernel/` |
| Public guides | `docs/` |

Do not create a second specification, architecture atlas, roadmap, schema home, or live task board.

## Required gates

The repository uses the same commands locally, in hooks, and in CI:

```text
just check     warm, non-mutating checks
just verify    full verification, generated drift, suites, history scan, clean-tree proof
```

The accepted toolchain and lockfiles are still an L0 deliverable. Until they land, use the dependency-light
commands in the [getting-started guide](../getting-started.md) and do not invent local pins. A pull request is
not ready merely because local hooks pass: required CI and independent review are authoritative.

Architecture and quality policy mechanically checks ownership, legal dependencies, source size, function
size, complexity, nesting, generated drift, exceptions, secrets, and verification scope. Review separately
judges cohesion, deep Modules, naming, abstraction quality, and attempts to split files only to evade limits.
Read the complete [coding standards](CODING_STANDARDS.md).

## Documentation changes

Public guides live under `docs/` and are rendered with MkDocs Material. Canonical design documents remain in
the repository root and are linked rather than copied. Keep statements in current tense, distinguish proven
behavior from intent, and never include secrets, PII, private infrastructure, or machine-local paths.

Preview and validate documentation with:

```bash
mkdocs serve
mkdocs build --strict
```

Every authored public page must appear exactly once in `mkdocs.yml` navigation. A stale or overclaiming page
blocks release.

## Pull-request discipline

- Keep a change cohesive and scoped to one independently reviewable outcome.
- Add tests through public Interfaces; do not mutate persistence directly from acceptance tests.
- Update exact contracts and conformance tests in the same change as an interface.
- Never hand-edit generated outputs; run the declared deterministic generator.
- Add an expiring reviewed exception rather than a hidden ignore when a temporary budget waiver is necessary.
- Include user-visible docs and release notes when behavior changes.
- Obtain independent review; authors never approve their own candidate.

See [CONTRIBUTING.md](https://github.com/simjak/ctower/blob/main/CONTRIBUTING.md) for the public contribution
workflow and [Releases](releases.md) for versioning and publication rules.
