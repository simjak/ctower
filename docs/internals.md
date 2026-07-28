# Advanced and internals

!!! warning "This section is the internal engineering record"
    Everything linked from this page is written for the people building and verifying ctower, not for
    someone integrating with it. It is audit material: capability matrices, verification evidence, bounded
    operational checkpoints, and the canonical design and decision sources.

    It is preserved deliberately and in full. It is placed here — behind the product documentation rather
    than in front of it — because reading it first gives a misleading impression of what is available. If
    you want to know what ctower is and how to use it, start at the [Overview](index.md) and the
    [Quickstart](quickstart.md).

## Delivery state and boundaries

| Page | What it records |
|---|---|
| [Delivery state](project-status.md) | The capability matrix: what is a development fixture, what is verifier-only proof, what is diagnostic, planned, or unsupported |
| [What is deliberately unavailable](start-here/availability.md) | The explicit do-not-attempt list |
| [Current operational boundary](operations/current-boundary.md) | What the checked-in Compose file is and is not |

The vocabulary those pages use is deliberate:

- **Development fixture** — executable code and tests exist in a controlled developer or verifier setup. It
  does not mean a supported product path exists.
- **Verifier-only proof** — a stronger property is exercised by an isolated test topology, not offered as a
  deployment.
- **Diagnostic only** — the artifact informs a later decision without satisfying it.
- **Planned** — the design may name a capability; no reader should attempt to use it.
- **Unsupported** — no installation, operations, compatibility, or recovery promise is made.

Checkpoint identifiers such as `CP3-C`, `CP3-D`, `I1.7A`, and `CT-I2-005` are internal sequencing labels
from `IMPLEMENTATION-ROADMAP.md`. They are not product versions and they are not release names.

## Verification

| Page | What it records |
|---|---|
| [Repository setup](start-here/repository-setup.md) | Prerequisites for the gates |
| [Exercise the development walking slice](getting-started.md) | What the full gate does and does not prove |
| [Observability](operations/observability.md) | Health vocabulary and redaction rules |
| [Secret handling](security/secret-handling.md) | Secret-reference discipline |

## Bounded recovery checkpoints

These describe local, verifier-only evidence. None of them is an operator runbook, an installation path, or
a production recovery service.

- [Backup and anchors](operations/backup-and-anchors.md)
- [Key recovery](operations/key-recovery.md)
- [Isolated restore](operations/isolated-restore.md)
- [Rollback](operations/rollback.md)
- [Recovery evidence](operations/recovery-evidence.md)
- [ctower-project cutover](operations/ctower-project-cutover.md)

## Canonical sources

These four files are the authority. This documentation site explains them; it never overrides or extends
them. Where this site and a canonical source disagree, the canonical source wins and the site is a defect.

| Source | Role | Mutation rule |
|---|---|---|
| [`SPEC.md`](https://github.com/simjak/ctower/blob/main/SPEC.md) | Current product, architecture, workflow, acceptance, and build contract | Reviewed revision; contradictions removed rather than accumulated |
| [`DECISIONS.md`](https://github.com/simjak/ctower/blob/main/DECISIONS.md) | Operator decisions and rationale | **Append only.** An accepted decision is never rewritten, only superseded by a new entry |
| [`ARCHITECTURE.md`](https://github.com/simjak/ctower/blob/main/ARCHITECTURE.md) | Derived terminal-safe atlas | Updated with `SPEC.md`; never creates requirements or a second architecture truth |
| [`IMPLEMENTATION-ROADMAP.md`](https://github.com/simjak/ctower/blob/main/IMPLEMENTATION-ROADMAP.md) | Non-normative sequencing proposal | Does not approve scope, activate backlog items, or authorize implementation |

`SPEC.md` is also a code-generation input: `generated/.generated-manifest.json` records its digest, so
editing it without regenerating fails `just check`.

## Contributing

[Development guide](contributing/development.md) ·
[Coding standards](contributing/CODING_STANDARDS.md) ·
[Documentation policy](contributing/documentation.md) ·
[Releases](contributing/releases.md)
