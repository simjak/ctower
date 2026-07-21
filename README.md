# ctower

ctower is an open-source control plane for durable work performed by humans and replaceable AI agents.
It keeps one authoritative, evidence-backed ticket journey from request through execution, verification,
release, production proof, retro, and closure.

Agent harnesses are useful execution environments, but their processes, terminals, and context windows are
temporary. ctower is designed to preserve the work: ownership, workflow position, decisions, attempts,
artifacts, evidence, effects, and the complete audit trail survive agent, model, machine, and process changes.

> [!IMPORTANT]
> ctower is currently a **pre-alpha development project**. One synthetic walking slice now implements local
> first-tenant bootstrap, durable ticket create/read/timeline, protected custody transfer, a thin online
> CLI, and a development-only proof-gated four-stage Workflow tracer over a generated client. All writes
> remain `durability_pending`; there is no supported installable, deployed, backed-up, or production-ready
> product today.

## What ctower is designed to provide

- Durable tickets with independent Kanban status and workflow stage.
- Versioned workflows that define legal stages, transitions, and failure routes.
- Versioned execution policies that select agents, models, environments, gates, limits, and escalations.
- A persistent Commander principal that leads work until verified closure while execution agents remain
  replaceable.
- Evidence-driven verification and bounded repair loops instead of status updates based on agent claims.
- Local or remote runtime adapters without giving an agent harness authority over the system of record.
- An operator attention queue that surfaces only decisions automation cannot safely make.

The first production workflow is a software factory, but the domain model is intentionally generic enough
for workflows such as accounting, operations, research, and compliance.

## Start here

- [Public documentation](https://simjak.github.io/ctower/)
- [System specification](SPEC.md) — canonical semantics, requirements, acceptance criteria, and KPIs
- [Architecture atlas](ARCHITECTURE.md) — compact derived system and infrastructure views
- [Decision log](DECISIONS.md) — append-only architectural history
- [Implementation roadmap](IMPLEMENTATION-ROADMAP.md) — dogfooding sequence under the specification
- [Contributing guide](CONTRIBUTING.md) and [coding standards](docs/contributing/CODING_STANDARDS.md)

The specification is authoritative. Exact machine contracts live in `contracts/`, concrete versioned
workflow and policy values live in `packs/`, and generated artifacts live in `generated/`.

## Use the repository today

Clone the repository and run the canonical verification gates:

```bash
git clone git@github.com:simjak/ctower.git
cd ctower
just check
just verify  # requires a clean committed tree
```

These commands validate the repository and the currently required synthetic walking-slice suites; they do
not deploy ctower or establish off-host durability. See the
[getting-started guide](https://simjak.github.io/ctower/getting-started/) for the current development
workflow, the historical compatibility evidence, and its unresolved runtime-selection gaps.

## Implementation path

1. Establish reproducible toolchains, required CI checks, and architectural boundary gates.
2. Build one durable ticket vertical and prove backup, restore, replay, and idempotency.
3. Add the CLI and thin Board/Ticket UI, then cut ctower's own backlog over without dual writes.
4. Add the generic workflow engine, durable runtime, Commander automation, and protected effects.
5. Use ctower to plan, implement, verify, document, release, and retro its own first production feature.

See the [implementation roadmap](IMPLEMENTATION-ROADMAP.md) for the phase exits and dogfooding maturity
model. Deferred integrations—including remote execution providers, reusable sandbox images, and runtime
catalogs—must earn a real interface after the local walking skeleton works.

## Contributing and security

ctower is being developed in public. Issues and pull requests are welcome, especially those that sharpen
the durability model, reduce operator attention, or prove a complete vertical path. Please read
[CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

Do not report vulnerabilities in public issues. Follow [SECURITY.md](SECURITY.md) for private reporting.

## License

Apache License 2.0. See [LICENSE](LICENSE).
