# ctower

ctower keeps the facts of long-running work alive when the person, model session, or machine doing the work
changes.

A ticket keeps one permanent identity. Custody says who is accountable now. A pinned workflow says which
stage is active. Evidence says exactly which candidate was checked before the ticket may close. Those facts
live in an append-only record behind typed, idempotent commands—not in a worker's memory.

## Take the one-minute tour

Start with [Getting started](getting-started.md). One command builds the real CLI, brings up a disposable
PostgreSQL database and loopback API, checks health, completes the four-stage workflow, and cleans up.

ctower is pre-alpha. The tour is a tested development slice, not an installer or production deployment.
Use synthetic data only.

## What ctower is good at

- retaining ticket identity across agent and session replacement;
- making custody transfer explicit, atomic, and auditable;
- refusing workflow moves whose declared preconditions are missing;
- binding evidence and verdicts to an exact candidate digest;
- deriving Board and delivery views from accepted facts.

## What it does not do yet

There is no browser UI, remote runner, external effect provider, general project/team administration,
production Compose stack, supported backup/recovery path, or production self-hosting guide. Declared packs
and generated clients are development artifacts, not proof that those surfaces are available.

## Read by task

| You want to… | Read… |
|---|---|
| See the working slice | [Getting started](getting-started.md) |
| Operate the implemented CLI | [CLI reference](reference/cli.md) |
| Understand tickets, custody, stages, and proof | [Concepts](concepts/index.md) |
| Understand the Compose boundary | [Local development](local-development.md) |
| Evaluate production hosting | [Self-hosting](self-hosting.md) |
| Build against the typed HTTP contract | [HTTP API reference](reference/http-api.md) |
| Contribute | [Development guide](contributing/development.md) |

Internal specifications, append-only decisions, checkpoint runbooks, and ticket plans remain in the
repository for maintainers but are excluded from this public site.
