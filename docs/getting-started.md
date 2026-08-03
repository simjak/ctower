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

## Onboarding a project

The quickstart works a ticket in an already-configured project. Onboarding a new one is a different,
Operator-only path, and it is worth knowing before you go looking for a command that does not exist.

There is no `project create`. A project is a `kind: project` resource in the CompanyBundle — the secret-free
YAML desired state checked in at `company/company.bundle.yaml` — published over the same authenticated
command API the UI uses:

```bash
ctl --base-url <url> company bundle validate company/company.bundle.yaml
ctl --base-url <url> company bundle plan company/company.bundle.yaml
ctl --base-url <url> company bundle apply company/company.bundle.yaml \
    --command-id <uuid> --expected-active-version <n> --plan-digest <digest from plan>
```

`validate` and `plan` are reads; `plan` is where a new project is visible as a `create` action on a
`kind: project` component, beside the checkpoint components that give it its starter checkpoints and name
each checkpoint's accountable seat. `apply` is a durable mutation and exits `75` with
`durability_pending` before the spool drains — that is the normal path, not an error.

Only an Operator may apply. A project Commander may author or propose a bundle revision but cannot apply
it, so onboarding cannot be self-served today. Whether it should be is
[issue #212](https://github.com/simjak/ctower/issues/212), an open operator decision; granting it would
require amending the specification, not just adding a command. The
[CLI reference](reference/cli.md#onboard-a-project) carries the full sequence, the real output, and the
exact specification rows.

## Common failures

| Symptom | Meaning |
|---|---|
| `docker is required for Postgres acceptance tests` | Docker is absent or its daemon is unreachable. |
| `uv: command not found` | Install `uv`; the quickstart will not fall back to an unpinned Python environment. |
| PostgreSQL never becomes healthy | Keep the complete Compose output. The fixture fails closed and attempts its project-scoped cleanup. |
| CLI exit `69` | A typed refusal is permanent until its named condition changes. Do not retry unchanged. |
| CLI exit `75` | The command is queued or waiting for durability acknowledgement. Reuse the same command ID. |

The checked-in Compose file publishes a database, not an application stack. See
[Local development](local-development.md) for the developer loop and the missing API/UI services, and
[Self-hosting](self-hosting.md) if you want an instance that keeps running.
