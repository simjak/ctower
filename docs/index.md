# Durable work, not durable terminals

ctower is an open-source control plane for work performed by humans and replaceable AI agents. It is
designed to keep the ticket, workflow, policy, evidence, and audit trail authoritative even when an agent
process, model, context window, sandbox, or machine disappears.

```text
request -> ticket -> workflow -> execution -> evidence -> gates -> release -> retro -> close
                 durable authority          replaceable workers
```

## Why ctower exists

Agent harnesses are excellent execution environments, but a terminal session is not a task-management
system. Chat histories and process-local queues make it difficult to answer basic operational questions:

- Who owns this outcome now, and who owned it before?
- Which workflow stage and Kanban state is the ticket in?
- What was attempted, rejected, repaired, reviewed, and released?
- Which evidence is current for the exact candidate being promoted?
- Can work resume safely after a runner, host, or model disappears?
- Which decision truly needs operator attention?

ctower addresses those questions with a durable control plane and a complete ticket history. Runtimes
execute work through narrow adapters; they do not become the authority for work state.

!!! warning "Pre-alpha status"
    ctower now has one development-only local walking slice: first-tenant bootstrap, ticket
    create/read/timeline, protected custody transfer, and a thin online CLI. Writes remain
    `durability_pending`; no runner, web application, supported deployment, off-host acknowledgement, or
    production release is available. See [Project status](project-status.md).

## Navigate the project

- [Getting started](getting-started.md) explains what can be validated today.
- [Core concepts](concepts.md) introduces tickets, workflows, policies, agents, gates, and effects.
- [Development guide](contributing/development.md) explains source ownership and contribution gates.
- [System specification](https://github.com/simjak/ctower/blob/main/SPEC.md) is the canonical source for
  product and system semantics.
- [Architecture atlas](https://github.com/simjak/ctower/blob/main/ARCHITECTURE.md) provides compact system,
  infrastructure, and flow diagrams.
- [Implementation roadmap](https://github.com/simjak/ctower/blob/main/IMPLEMENTATION-ROADMAP.md) defines the
  walking-skeleton and dogfooding sequence.

The documentation site explains the project. It does not duplicate or supersede the canonical design
documents in the repository root.
