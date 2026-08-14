# ctower

ctower is a control plane for work that outlives the process doing it.

A terminal can disappear. A model can be replaced. A provider can time out after accepting a request. The
identity, ownership, progress, and proof of the work should survive all three. ctower records those facts in
one trusted control plane and treats workers, browser servers, providers, and command-line clients as
replaceable edges.

!!! warning "Pre-alpha development surface"
    There is no published package, hosted service, or production deployment. The only installed runtime is
    a private, loopback-only development shadow for low-value reconstructible work. Browser surfaces are
    development-only and unsupported. The contracts can change between revisions.

## Start here

Use the documentation in this order:

1. [Concepts](concepts/index.md) explains the product model and which component owns each fact.
2. [Quickstart](quickstart.md) produces one working result through the installed CLI and a disposable
   PostgreSQL-backed API.
3. [CLI reference](reference/cli.md) and [HTTP API](reference/http-api.md) define the current command and
   operation surface.

If you are changing the repository, continue with [Repository setup](start-here/repository-setup.md) and
[Local development](local-development.md).

## The shape of the system

```text
request or conversation
          |
          v
       Ticket  <------ permanent identity and custody
          |
          v
      Workflow <------ immutable stage graph and pinned policies
          |
          v
        Proof  <------ frozen criteria, evidence, and verdicts
          |
          v
  Board / delivery <-- read-only projections with watermarks
```

Around that spine:

- **Routines** create repeatable occurrences but never claim their outcome.
- **Integrations** translate strict external payloads but never own Ticket lifecycle truth.
- **Runtime workers** receive leased work and return typed results without direct record persistence.
- **Knowledge** retains bounded attributable results, not raw private sessions.
- **Access** resolves project grants, credentials, and revocation before every protected operation.
- **Health and metrics** name their source watermark and render missing evidence as unknown.

See [The whole picture in one map](concepts/map.md) for the responsibility map.

## Available now

The repository's development slice demonstrates:

- Request capture, immutable Rulings, and a deterministic morning digest;
- Ticket capture, custody, assignment, prioritization, blockers, relationships, history, resolve, and close;
- a pinned four-stage Workflow with frozen criteria, candidate-bound evidence, and protected verdicts;
- Board, project delivery, Inbox, Knowledge, recorded-session, health, and operational reads;
- versioned company configuration through validate, plan, apply, and export;
- a generated HTTP surface and a closed protected CLI command set;
- bounded issue integrations for two source hosts;
- fixed recurring work definitions and typed runtime custody; and
- one private loopback shadow runtime plus a private read-only Console server foundation.

These surfaces are tested development contracts. They are not a supported external service or stability
promise. [Current availability](start-here/availability.md) separates development evidence from planned
product behavior.

## Planned layers

The accepted design adds, in dependency order:

- durable agent liveness, capacity, bounded recovery, and recovery drills;
- recorded project planning and deterministic daily work stacks;
- redacted session mining into revision-pinned knowledge;
- canonical Ticket movement, typed stall clocks, and complete worklist reads;
- a public catalog engine over private company content; and
- durable workspace records with runner-side materialization.

No planned item is an available command merely because it appears here. Its concept, first-use path, and
reference material ship with the implementation.

## Choose your path

| Goal | Next page |
|---|---|
| Understand Tickets, Workflows, Proof, and durable reads | [Concepts](concepts/index.md) |
| Run one complete disposable workflow | [Quickstart](quickstart.md) |
| Automate the current CLI | [CLI reference](reference/cli.md) |
| Generate or inspect an API client | [Generated clients and contracts](reference/clients.md) |
| Handle retries and refusals correctly | [Agent operating contract](agents/operating-contract.md) |
| Work on the repository | [Repository setup](start-here/repository-setup.md) |
| Understand the private installed boundary | [Self-hosting](self-hosting.md) |
