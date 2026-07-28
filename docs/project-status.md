# Delivery state

!!! note "Internal engineering record"
    This page is part of the [internal engineering record](internals.md). It uses internal checkpoint
    labels (`CP3-C`, `I1.7A`, `CT-I2-005`) that are sequencing identifiers from
    `IMPLEMENTATION-ROADMAP.md`, not product versions. For what ctower is and how to use it, start at the
    [Overview](index.md) and the [Quickstart](quickstart.md).

ctower is a public pre-alpha project. The codebase contains a tested development slice, not a supported
control-plane product. This page distinguishes executable development evidence from verifier-only proof and
planned work so a visible package, schema, or directory is not mistaken for an available service.

## Capability matrix

| Capability | Status | What that means now |
|---|---|---|
| First-tenant bootstrap and durable ticket facts | Development fixture | The test topology exercises bootstrap, ticket creation/read/timeline, custody, assignments, priority, blockers, relations, and audit facts. It is not an installer or hosted service. |
| Workflow, Proof, and Board | Development fixture | The four-stage `ctower.trust-spine-four-stage@1` fixture, protected Proof flow, and read-only six-lane Board projection are exercised in development tests. They are not a general production workflow service. |
| Protected CLI and encrypted spool | Development fixture | `ctowerctl`/`ctl` expose every authored CLI mapping through the generated client. Non-bootstrap mutations are encrypted and durable before send; Linux verification exercises real Secret Service. This is not a published operator package or off-host recovery path. |
| HTTP/OpenAPI and generated clients | Development fixture | The authored OpenAPI has 39 operations with explicit CLI/query-mutation/spool metadata. It generates strict client models, methods, replay registry, and runtime schema resources. It is not a stable supported external API. |
| CompanyBundle and Catalog | Development fixture | Strict validate/plan/apply/export and ticket comments are exercised against real PostgreSQL. Apply is atomic/idempotent and moves one future-only pointer; it does not activate runners, effects, or external targets. |
| I1.7A cutover visibility | Development fixture | Strict cutover-health and compact read-only Project Delivery contracts, generated reads, and a CP3-D-blocked fold exist. Migration commands are online-only refusal stubs. No legacy record is imported or fenced and no development epoch is committed. |
| Off-host acknowledgement | Verifier-only proof | The ordinary configuration is `pending_only`. A verifier-owned PostgreSQL primary/standby topology exercises acknowledged durability; that evidence is not a supported deployment, backup, or restore path. |
| Deterministic control loops and health vocabulary | Development fixture | Fixed Routine/outbox/projection loops and health reporting are tested. Routine names alone do not constitute a supported operational service. |
| Local CP3-C backup and recovery evidence | Verifier-only proof | Local/verifier evidence covers digest-bound object handling, backup and anchors, key recovery, isolated restore, rollback, and recovery evidence. It does not activate external targets, a supported deployment, or CP3-D production recovery. |
| Runtime compatibility evidence | Diagnostic only | The compatibility validator accepts a closed, sanitized external report. It does not choose a product runtime, create a lock, or establish a support promise. |
| Product installation, deployment, and recovery | Unsupported | A clean-wheel test proves the development artifact, but there is no published/supported package, product Compose stack, container image, production backup/restore runbook, or production monitoring/incident path. |
| Browser UI, runner, effects, and agent adapters | Planned | These surfaces remain deferred. CompanyBundle component declarations do not activate their runtime behaviour. |
| Production release | Unsupported | Release automation currently creates source tags and notes only. No ctower runtime release has been published. |

Public API + protected CLI precede I1 source-of-truth cutover. Browser implementation, browser evidence,
and browser E2E first activate at CT-I2-005 / I2.4.

I1.7B will implement reviewed source selection/import/reconciliation and the permanent legacy fence.
I1.7C will commit the narrow reconstructible-data development epoch and run the first API/CLI dogfood
target. CP3-D and disaster-safe promotion remain later blocking evidence.

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
