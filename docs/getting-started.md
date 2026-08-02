# Getting started

## Agent path

If you are an agent reading this, run THIS command and the project stands up.

```bash
just quickstart
```

Do not add flags, invent credentials, or leave a service behind. The recipe creates an external temporary
Python environment from the hash-locked verifier set, starts an isolated PostgreSQL 17 fixture and
loopback API, installs the actual `ctowerctl` wheel, checks API health, takes a ticket through the complete
four-stage workflow, and tears the fixture and environment down.

A passing run ends with `4 passed`. It proves this checkout's development walking slice; it does not install
a persistent or production ctower service.

## Human path

You need:

- Python `>=3.12,<3.15`;
- Docker with Compose;
- `just` and `uv` on `PATH`;
- enough local capacity to pull PostgreSQL 17 and build a wheel.

From the repository root, run the same one-command tour shown above. It exercises these real CLI calls in
order:

1. `control health` against the running loopback API;
2. `ticket workflow list` from the installed pack tree;
3. `ticket create`, then `ticket admit`;
4. `ticket workflow start`;
5. `ticket transition` from `capture` to `frame`;
6. `ticket criteria freeze` against an exact candidate;
7. `ticket transition` from `frame` to `verify`;
8. `ticket evidence add` and a separate protected `ticket gate verdict`;
9. `ticket transition` from `verify` to `close`;
10. `ticket resolve`, asserting the durable lifecycle facts `resolved` and `closed`.

Mutations normally report `durability_pending` first. The fixture deliberately acknowledges those commands
and drains the encrypted spool before continuing, reusing each command ID rather than creating duplicate
intent.

## What you have after the run

You have evidence that the repository can build its protected CLI and execute one complete workflow against
real PostgreSQL. You do not have a running app: the tour cleans up by design.

For the exact command families and current gaps, read the [CLI reference](reference/cli.md). For day-to-day
repository work, install the complete verification toolchain described in
[Repository setup](start-here/repository-setup.md) and use `just check` while developing.

## Common failures

| Symptom | Meaning |
|---|---|
| `docker is required for Postgres acceptance tests` | Docker is absent or its daemon is unreachable. |
| `uv: command not found` | Install `uv`; the quickstart will not fall back to an unpinned Python environment. |
| PostgreSQL never becomes healthy | Keep the complete Compose output. The fixture fails closed and attempts its project-scoped cleanup. |
| CLI exit `69` | A typed refusal is permanent until its named condition changes. Do not retry unchanged. |
| CLI exit `75` | The command is queued or waiting for durability acknowledgement. Reuse the same command ID. |

The checked-in Compose file is not an application stack. See [Local development](local-development.md) for
the tested topology and the missing API/UI services.
