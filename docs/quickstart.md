# Quickstart

This tour gives you one working result without installing a long-running service. It builds an isolated
environment, starts a disposable PostgreSQL-backed API, drives the installed CLI, and removes everything it
created.

By the end, you will have seen a Ticket complete the proof-gated four-stage Workflow and you will have
queried the running API's health through the real command-line package.

## Prerequisites

You need:

- Git;
- Python 3.12–3.14;
- Docker with Compose;
- `just`; and
- `uv`.

Docker must be running. The acceptance fixture publishes PostgreSQL on a temporary loopback port and uses
temporary storage.

## Run it

```bash
git clone https://github.com/simjak/ctower.git
cd ctower
just quickstart
```

The recipe:

1. creates a guarded temporary directory;
2. creates a virtual environment with your selected Python interpreter;
3. installs the repository's hash-locked verification dependencies;
4. installs and launches the current API and CLI against a disposable database;
5. queries health through `control health`;
6. discovers the installed Workflow revision and its exact policy digests;
7. creates and admits a Ticket;
8. freezes criteria, records evidence and a protected verdict, then resolves and closes the Ticket; and
9. removes the virtual environment and database fixture.

A successful current run ends with:

```text
4 passed
```

The tests include refusal paths. Health may be reported as unknown when a contributor is deliberately not
configured in the disposable fixture; the important behavior is that unknown is returned as a typed answer
instead of being rendered healthy.

## What the workflow proves

The development Workflow has four stages:

```text
capture -> frame -> verify -> close
```

Each transition is declared. The move into the final stage and the Ticket's resolve/close operation require
proof bound to the current candidate. A wrong digest is refused and writes no partial state. The installed
CLI uses the same generated operation contracts as the API rather than a second command dispatcher.

This is repository evidence, not a hosted product. The tour does not retain a tenant, expose a network
service, install a browser application, or produce production durability.

## Choose a different interpreter

Every recipe defaults to `python3`. To use another compatible interpreter:

```bash
PYTHON=/path/to/python3.13 just quickstart
```

## Next

- [Concepts](concepts/index.md) explains the Ticket, Workflow, Proof, and durability vocabulary.
- [CLI reference](reference/cli.md) lists the complete current command surface and exit codes.
- [Local development](local-development.md) explains the database fixture and the warm and release gates.
- [Self-hosting](self-hosting.md) describes the separate private loopback runtime and its limits.
