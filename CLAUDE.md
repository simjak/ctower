# ctower engineering constitution

Read `docs/internal/SPEC.md`, `docs/internal/DECISIONS.md`, `ARCHITECTURE.md`,
`docs/internal/IMPLEMENTATION-ROADMAP.md`, and the nearest boundary README before changing this repository.

## Engineering principles

- Do not preserve backward compatibility. Remove obsolete paths instead of
  adding compatibility layers, fallbacks, or migrations.
- Choose the simplest implementation that fully meets the current
  requirements. Avoid speculative abstractions, configuration, and
  indirection.
- Grow the system in layers. Start from the smallest version that works end
  to end, and add each new capability on top of a product that already
  works. Never trade a working product for unfinished complexity.
- Keep components modular and concerns clearly separated.
- Prefer established, well-maintained libraries when they reduce overall
  complexity or improve reliability. Do not reimplement common
  functionality without a clear reason.
- Lean on the dependencies already in the project before writing your own
  implementation or adding packages. Do not assume a library lacks a
  capability without checking its documentation and types.
- Make architectural decisions for the long term. Do not accept a stopgap
  that only works for now and is meant to be replaced later.

## Canonical sources

- `docs/internal/SPEC.md` is the current product, architecture, workflow, acceptance, and build contract.
- `docs/internal/DECISIONS.md` is append-only history. Never rewrite an accepted decision; supersede it with a new entry.
- `ARCHITECTURE.md` is the single derived terminal-safe atlas. It may explain but never override or extend
  `docs/internal/SPEC.md`; repair it immediately when the two diverge.
- `docs/internal/IMPLEMENTATION-ROADMAP.md` is the single non-normative sequencing proposal. It does not
  approve scope, activate backlog items, or authorize implementation; `docs/internal/SPEC.md` remains
  authoritative.
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

## THE SOFTWARE FACTORY IS LAW (operator, 2026-08-22 — fleet-wide, binding on every seat)

The full law lives in mission-control `AGENTS.md` §1b + `factory/{workflow,ticket,crew,skills-map}.md`.
The short form every crew in THIS repo follows:
1. **Every task is a TICKET** (a file in `tickets/` until ctower carries it) following the
   declared workflow: think → plan/design → implement → QA → review → docs → ship → release →
   QA-staging/e2e → QA-production → close, with loop-backs.
2. **No task proceeds without PLAN/DESIGN passing; no IMPLEMENT without its spec file.**
   Security designs must be structural/allowlist — denylist designs are rejected at design.
3. **The ticket hands over between seats** (custody episodes): author ≠ reviewer, builder ≠ QA.
   Commanders orchestrate only — never code, QA, credential mints, or release mechanics.
4. **Per-stage evidence slots block exit**; each stage's mandatory skill produces its evidence.
   Review ≤3 rounds, always. `skills_used` records skill@stage on the ticket.
