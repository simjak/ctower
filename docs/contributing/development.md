# Development guide

ctower is built as a walking system: one complete, durable path before platform breadth. Contributions must
preserve that sequence and the distinction between authored semantics, executable contracts, and generated
outputs.

## Before changing code or contracts

1. Read the [architecture atlas](https://github.com/simjak/ctower/blob/main/ARCHITECTURE.md) and the
   repository constitution.
2. Identify the owning Module and its permitted dependency edges in `tools/checks/policy.toml`.
3. Confirm that the capability is current on the [availability page](../start-here/availability.md).
4. Define failure, restart, authorization, idempotency, and evidence behavior before adding a happy path.

Do not introduce a public extension interface for a single fake implementation. A Seam is earned only when
two real, independently useful adapters need the same contract.

## Repository authority

| Content | Authoritative home |
|---|---|
| Human-visible system semantics and acceptance criteria | The canonical record named by the repository constitution |
| Historical decisions and supersessions | The append-only record named by the repository constitution |
| Compact derived architecture views | `ARCHITECTURE.md` |
| Development sequence | The sole roadmap named by the repository constitution |
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

The verification host is reproducible without selecting ctower's product runtime. Python verification
dependencies are compiled with hashes in `requirements/verify.txt`; JavaScript dependencies use the frozen
`pnpm-lock.yaml`; remote pre-commit hooks use immutable commits; and CI checksum-verifies Node, pnpm, `just`,
Actionlint, and Gitleaks before use. Install the Python verification environment with
`python -m pip install --require-hashes -r requirements/verify.txt` and JavaScript dependencies with
`pnpm install --frozen-lockfile --ignore-scripts`. Do not add `.python-version` or `uv.lock`: the product
runtime remains unresolved, and these verification-host locks do not select one.

`just check` includes Actionlint, strict documentation, generated traceability, a scan of exactly the intended
Git tree, tests, types, formatting, and repository policy. `just verify` additionally executes every currently
required suite, enforces branch coverage, scans complete reachable Git history, and proves the tree stayed
clean. The local staged Gitleaks hook and both canonical gates invoke an already installed Gitleaks binary;
they never compile Go tooling or fetch a scanner while deciding whether a candidate passes. A pull request is
not ready merely because local hooks pass: required CI and independent review are authoritative.

To update verification dependencies, edit only the direct inputs, regenerate rather than hand-edit the
locks, and review the resolved diff. Use uv `0.11.3` and pnpm `10.20.0`:

```bash
uv pip compile requirements/verify.in --universal --python-version 3.13 \
  --generate-hashes --output-file requirements/verify.txt
pnpm install --lockfile-only --ignore-scripts
```

Any verification binary version change must update the upstream release checksum in
`.github/workflows/verify.yml` in the same reviewed change.

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
