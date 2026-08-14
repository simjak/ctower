# Coding standards and merge gates

These standards are mandatory from the first implementation commit. Correct but structurally weak code receives `CHANGES_REQUESTED`.

## Deep Modules and Interfaces

A Module owns a substantial cohesive decision or authority and exposes one small explicit Interface. Hide implementation choices behind the Interface; do not expose storage rows, provider handles, framework objects, or persistence choreography. A new top-level Module must pass the deletion test: removing it would otherwise spread meaningful complexity across multiple callers.

A public Seam exists only when two real, independently valuable Adapters need the same contract. A fake alone does not earn a Seam. Adapter conformance tests are shared across every real implementation.

Forbidden by default:

- god objects, god functions, service-per-table, package-per-noun, and generic provider managers;
- catch-all `utils`, `common`, `helpers`, or `manager` modules;
- pass-through re-export layers and files split only to evade size limits;
- a `Factory` engine separate from the generic Workflow Module;
- private cross-Module imports or dependency edges absent from executable ownership policy.

## Source budgets

The Repository Policy Module uses language-aware parsing and emits warnings/failures at:

| Measure | Warn | Fail |
|---|---:|---:|
| Authored source or test file | >500 logical lines | >600 logical lines |
| Function or method | >40 logical lines | >60 logical lines |
| Cyclomatic complexity | >8 | >10 |
| Control-flow nesting | >2 | >3 |
| Public exports per Module | >15 | >25 |
| Public methods per class | >10 | >15 |
| Direct Module dependency fan-out | >8 | >12 |

Warnings require reviewer discussion; hard limits block merge. Migrations and tests are not blanket-exempt. Generated/vendor code, lockfiles, binaries, protocol captures, and golden snapshots use digest/drift/compile/size gates instead of authored LOC.

## One exact exception mechanism

All temporary waivers live in `tools/checks/exceptions.yaml`. Each entry contains exactly: ID, rule, path, temporary limit, owner, reason, ctower ticket, independent approver, creation date, and expiry no later than 30 days. An expired, malformed, unmatched, over-limit, or duplicate exception fails CI. Inline linter/type/coverage/secret ignores must cite the exact code and matching exception ID.

Cross-tenant/access/fencing invariants, forged proof, direct untrusted record-tier access, secrets, and generated drift are non-waivable.

## Python

- Type every authored function and method. Strict mypy plus the Pydantic plugin is authoritative.
- No unbounded `Any` on public Interfaces. External JSON remains tainted until a named strict validator returns a typed value.
- Every HTTP/event/bundle/catalog/spool/runner/checkpoint/evidence/provider/effect/telemetry payload is an immutable Pydantic v2 model with unknown fields forbidden.
- Frozen dataclasses are appropriate for internal immutable values that do not cross a process boundary.
- Ruff is the sole Python linter and formatter. Do not add competing formatter configuration.
- Use explicit transactions and public Interfaces. Do not leak psycopg rows or FastAPI objects into domain decisions.

The repository currently supports syntax from Python 3.12 through candidate 3.14. No exact
`.python-version` is allowed until the product-runtime compatibility gate selects and records one.

## TypeScript

TypeScript is browser-only and uses the generated API client. Required compiler behavior includes strict mode, unchecked-index safety, exact optional properties, explicit overrides and returns, exhaustive discriminated unions, unknown catch variables, and unused/fallthrough checks. ESLint blocks explicit `any`, floating promises, non-exhaustive switches, console/debug output, and unsafe type shortcuts. Prettier is the sole formatter.

Do not choose a frontend framework until its L0 decision. Browser view state never becomes domain authority.

## Dependency and ownership law

The direction is acyclic:

```text
contracts -> generated models/clients -> apps
packs -----^
ctower-api -> kernel public Interfaces
ctower-runner -> runner SDK -> generated runner contracts
ctower-web / ctowerctl -> generated clients
provider Adapters -> their narrow port + generated contracts
```

Kernel cannot import apps, provider implementations, runner, web, or CLI. Runner/provider/web/CLI/import/extension/config packs cannot import or connect to record-tier persistence. A new cross-Module dependency changes executable policy in the same independently reviewed change.

## Deterministic generated code

Authored schemas exist only in `contracts/`. `generated/.generated-manifest.json` records each generator, exact version, command, input digests, and output digests. Generated files carry a do-not-edit header. Full verification regenerates into a temporary directory, compares normalized bytes, validates schema references/operation IDs, and compiles/typechecks both clients. Hand edits, duplicate schema homes, missing outputs, or nondeterminism block merge.

## Observability and redaction

Every process boundary carries the generated strict `TelemetryContext`. Public Interfaces and real Adapter wrappers emit OpenTelemetry-compatible spans, low-cardinality metrics, and structured typed log records. Asynchronous durable work uses span links. Export failure never rolls back a Record transaction, but it makes completeness visibly unhealthy.

Never place prompts, secrets, user content, artifact bytes, bearer values, raw URLs with credentials, or high-cardinality identifiers in metric labels. Raw execution logs are content-addressed artifacts, not application logs. Protected effects, auth denials, gate/proof denials, incidents, rollbacks, stale fences, and reconciliation failures are retained at 100%.

## Tests and review

Tests use public Interfaces, never private implementation or direct database mutation. Module tests cover success, denial, idempotency, stale state, restart/rebuild, authorization, and relevant property/state cases. Acceptance tests use generated clients across real process boundaries. Authors never approve their own candidate; reviewer independence includes effective identity, session, workspace, provider, and isolation domain.

Authored Python starts at 90% branch coverage; TypeScript starts at 90% lines and 85% branches. Access, Record, Workflow, Proof, Runtime fencing, and Effects grant decisions target every decision branch. Coverage supports behavioral proof and never substitutes for it.

`just check` is the warm gate. It includes Actionlint, formatting, lint, types, repository and contract tests, strict documentation, generated drift, and exact intended-tree secret detection. `just verify` repeats it and adds a complete reachable-history secret scan, full repository policy, branch coverage, every currently required suite, and a clean-diff proof. Both are non-mutating and invoke an installed Gitleaks binary without network access or gate-time compilation. CI invokes these commands rather than maintaining parallel rule implementations.

`tools/checks/expected-suites.toml` is the only verification-scope manifest. Its active phase and ordered
backlog phases determine which suites are required. A current suite that is missing, has no executable
tests, is malformed, contains an unexpected skip, times out, or returns nonzero blocks verification.
Commands are argv arrays executed without a shell. Public API and protected CLI precede source-of-truth
cutover. Product browser implementation, browser evidence, and browser E2E remain deferred; a separate
development-only browser check may be required without activating the product-browser suite. A later suite
is reported as `not_yet_required`; it is never executed, represented by an
empty placeholder, or counted as passing. A backlog owner activates a suite by advancing this manifest in
the same reviewed change; the stable `just verify` command does not acquire a parallel suite list.
