# ctower engineering constitution

Read `SPEC.md`, `DECISIONS.md`, `ARCHITECTURE.md`, `IMPLEMENTATION-ROADMAP.md`, and the nearest
boundary README before changing this repository.

## Canonical sources

- `SPEC.md` is the current product, architecture, workflow, acceptance, and build contract.
- `DECISIONS.md` is append-only history. Never rewrite an accepted decision; supersede it with a new entry.
- `ARCHITECTURE.md` is the single derived terminal-safe atlas. It may explain but never override or extend
  `SPEC.md`; repair it immediately when the two diverge.
- `IMPLEMENTATION-ROADMAP.md` is the single non-normative sequencing proposal. It does not approve scope,
  activate backlog items, or authorize implementation; `SPEC.md` remains authoritative.
- Do not create another architecture/diagram file, competing roadmap, or ticket-state mirror.

## Hard boundaries

- Python: trusted control plane, runner, CLI, release helper. TypeScript: browser only. No Go/Rust without a new measured Seam decision.
- No exact `.python-version` until CT-L0-007 compatibility evidence and append-only D6 supersession are accepted.
- `contracts/` is authored; `generated/` is machine-owned and must match its manifest.
- Kernel authority never imports apps, providers, web, CLI, or record-tier clients.
- Runner, provider, web, CLI, extension, and YAML packs never connect to record-tier persistence.
- Every external/process payload is strict and typed. Secrets are references, never values.
- Modules expose small public Interfaces and hide cohesive complexity. No god objects, catch-all utility modules, pass-through services, or package-per-noun design.
- Product behavior is out of scope until its stable CT ticket and dependencies are active.

## Required gates

Run `just check` while developing and `just verify` before review. Verification-host dependencies are
hash/checksum locked in `requirements/verify.txt`, `pnpm-lock.yaml`, immutable hook commits, and the verify
workflow; these locks do not choose ctower's unresolved product runtime or permit `.python-version`/`uv.lock`.
The warm gate includes Actionlint and exact intended-tree secret detection. The release gate additionally
scans complete reachable history and proves currently required suites, branch coverage, and a clean tree.
Both gates invoke an installed Gitleaks binary without gate-time network access or compilation. Never weaken a gate with an
inline ignore; use one exact, independently approved, maximum-30-day exception in
`tools/checks/exceptions.yaml` when the rule is waivable.
