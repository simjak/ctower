# Project status

ctower is a public pre-alpha project. The codebase contains a tested development slice, not a supported
control-plane product. This page distinguishes executable development evidence from verifier-only proof and
planned work so a visible package, schema, or directory is not mistaken for an available service.

## Capability matrix

| Capability | Status | What that means now |
|---|---|---|
| First-tenant bootstrap and durable ticket facts | Development fixture | The test topology exercises bootstrap, ticket creation/read/timeline, custody, assignments, priority, blockers, relations, and audit facts. It is not an installer or hosted service. |
| Workflow, Proof, and Board | Development fixture | The four-stage `ctower.trust-spine-four-stage@1` fixture, protected Proof flow, and read-only six-lane Board projection are exercised in development tests. They are not a general production workflow service. |
| Online CLI | Development fixture | `ctowerctl` supports bootstrap and ticket create/show/assign through the generated Python client. It has no offline spool and does not establish CLI/API parity. |
| HTTP/OpenAPI and generated clients | Development fixture | The authored OpenAPI has a broader development surface than the CLI, including Work, Proof, Workflow, Board, health, and outbox operations. It is not a stable supported external API. |
| Off-host acknowledgement | Verifier-only proof | The ordinary configuration is `pending_only`. A verifier-owned PostgreSQL primary/standby topology exercises acknowledged durability; that evidence is not a supported deployment, backup, or restore path. |
| Deterministic control loops and health vocabulary | Development fixture | Fixed Routine/outbox/projection loops and health reporting are tested. Routine names alone do not constitute a supported operational service. |
| Local CP3-C backup and recovery evidence | Verifier-only proof | Local/verifier evidence covers digest-bound object handling, backup and anchors, key recovery, isolated restore, rollback, and recovery evidence. It does not activate external targets, a supported deployment, or CP3-D production recovery. |
| Runtime compatibility evidence | Diagnostic only | The compatibility validator accepts a closed, sanitized external report. It does not choose a product runtime, create a lock, or establish a support promise. |
| Product installation, deployment, and recovery | Unsupported | There is no supported installable package, product Compose stack, container image, configuration contract, production backup/restore runbook, or production monitoring/incident path. |
| CompanyBundle, browser UI, runner, and agent adapters | Planned | These surfaces are intentionally deferred. Their schemas or boundary packages do not activate a user-facing capability. |
| Production release | Unsupported | Release automation currently creates source tags and notes only. No ctower runtime release has been published. |

Public API + protected CLI precede I1 source-of-truth cutover. Browser implementation, browser evidence,
and browser E2E first activate at CT-I2-005 / I2.4.

## How to interpret the labels

- **Development fixture** means executable code and tests exist in a controlled developer/verifier setup. It
  does not mean a supported product path exists.
- **Verifier-only proof** means a stronger property is exercised by an isolated test topology, not offered as
  an operator deployment.
- **Diagnostic only** means the artifact informs a later decision without satisfying it.
- **Planned** means the design may name a capability, but no reader should attempt to use it.
- **Unsupported** means no installation, operations, compatibility, or recovery promise is made.

## What to do next

- For a checkout and verification prerequisites, use [Repository setup](start-here/repository-setup.md).
- To understand what the full test gate does—and does not do—read
  [Exercise the development walking slice](getting-started.md).
- Before operational or integration work, read [What is deliberately unavailable](start-here/availability.md) and
  [Current operational boundary](operations/current-boundary.md).
- For the bounded local CP3-C checkpoint, read [Backup and anchors](operations/backup-and-anchors.md),
  [Key recovery](operations/key-recovery.md), [Isolated restore](operations/isolated-restore.md),
  [Rollback](operations/rollback.md), and [Recovery evidence](operations/recovery-evidence.md).

For binding requirements, use the [system specification](https://github.com/simjak/ctower/blob/main/SPEC.md).
For derived topology, use the [architecture atlas](https://github.com/simjak/ctower/blob/main/ARCHITECTURE.md).
For sequencing, use the [implementation roadmap](https://github.com/simjak/ctower/blob/main/IMPLEMENTATION-ROADMAP.md).
