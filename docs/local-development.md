# Local development

This page is the working loop for changing ctower on your own machine: the gates you run, the database the
tests use, and the exact Compose file behind it.

There is no long-running local application to start. ctower's local development model is a checkout plus
disposable fixtures — every database in this loop is created for a run and destroyed after it.

## Before you start

Install the toolchain in [Repository setup](start-here/repository-setup.md). The short version is Git,
Python `>=3.12,<3.15`, Docker with Compose, `just`, `uv`, and — for the complete gate — Node 24,
pnpm 10.20.0, Actionlint, and Gitleaks.

Every recipe below runs from the repository root.

## The loop

```bash
just quickstart
```

Run this first, before you change anything. It builds a throwaway environment from the hash-locked verifier
set, drives one ticket through the whole four-stage workflow against real PostgreSQL, and removes
everything it created. A passing run ends with `4 passed` and takes about a minute on the maintainer
toolchain. If this fails on a clean checkout, fix your toolchain before you debug your change.

```bash
just check
```

This is the warm gate you run while editing: formatting, lint, types, the documentation build, workflow
lint, version mirrors, repository and contract suites, codegen and traceability drift, and an
intended-tree secret scan. It never mutates the worktree.

```bash
just verify
```

This is the gate a review candidate must pass. It adds the product suite with its exact branch-coverage
verdict, the expected-suite proof, a complete reachable-history secret scan, and a clean-tree proof — so
commit before you run it. A dirty worktree is a refusal, not a warning.

All three recipes take the interpreter from the `PYTHON` variable and default to `python3`. When your default
`python3` is not the version you want the gate to use, name it explicitly:

```bash
PYTHON=/path/to/python3.13 just check
```

`GITLEAKS` overrides the secret-scanner binary the same way.

## The database

`deploy/development/compose.yaml` defines exactly one service: PostgreSQL 17 published on loopback with
`tmpfs` storage and trust authentication. Confirm that yourself:

```bash
docker compose --file deploy/development/compose.yaml config --services
```

```text
postgres
```

The test suites own that file. `tests/acceptance/increment-1/support/postgres.py` and
`tests/modules/migration/_postgres.py` each start it under a per-run project name on a free loopback port
(`CTOWER_POSTGRES_PORT`), create one uniquely named database per test with separate administration,
migration, runtime, and projection roles, and tear the project down with `--volumes` afterwards. You do not
have to start a database before running the suites, and two runs on the same machine cannot collide.

Start it yourself only when you want a PostgreSQL to inspect by hand. Choose your own project name and port
so you never touch a running suite:

```bash
CTOWER_POSTGRES_PORT=55673 docker compose --project-name my-ctower \
  --file deploy/development/compose.yaml up --detach --wait
```

```text
 Network my-ctower_default  Creating
 Network my-ctower_default  Created
 Container my-ctower-postgres-1  Creating
 Container my-ctower-postgres-1  Created
 Container my-ctower-postgres-1  Starting
 Container my-ctower-postgres-1  Started
 Container my-ctower-postgres-1  Waiting
 Container my-ctower-postgres-1  Healthy
```

It is then an ordinary PostgreSQL 17 on `127.0.0.1:55673`, database `ctower`, user `postgres`, no password:

```bash
CTOWER_POSTGRES_PORT=55673 docker compose --project-name my-ctower \
  --file deploy/development/compose.yaml ps
```

```text
NAME                   IMAGE                  COMMAND                  SERVICE    CREATED        STATUS                  PORTS
my-ctower-postgres-1   postgres:17-bookworm   "docker-entrypoint.s…"   postgres   1 second ago   Up 1 second (healthy)   127.0.0.1:55673->5432/tcp
```

The container carries no ctower schema. Migrations belong to the code that owns a database — the suites
apply them to the database they create, and the persistent runtime applies them through its own migration
verb. There is no supported command that migrates a database you started by hand.

Always remove your own project when you are done. The storage is `tmpfs`, so the data is gone either way:

```bash
CTOWER_POSTGRES_PORT=55673 docker compose --project-name my-ctower \
  --file deploy/development/compose.yaml down --volumes
```

## What Compose does not give you

The file has no `api` service, no UI service, no API port, and no UI port. Running it gives you a database,
not ctower.

That is a real gap, not an omission in this page. A composed application stack would need pieces the
product does not have yet:

- an API entry point that takes its database and credentials from the environment — today's
  `ctower-development-api` reads one strict local configuration and resolves every secret through a
  Secret Service keyring, so it cannot be handed a container DSN;
- a first-run bootstrap and credential ceremony that a stack can perform unattended;
- ownership of migrations for a database nobody has already prepared;
- a browser application — product browser realization remains separately activated work, with no runnable UI
  selected in this cut;
- health and readiness wiring, durable storage, and a cleanup contract for the composed services.

Adding `api:` and `ui:` service names before those exist would produce a stack that starts and does
nothing. Until they land, treat `deploy/development/compose.yaml` as a database fixture, keep synthetic
data in it only, and use `just quickstart` when you want to watch the product work.

If you want a ctower you can keep talking to, the only persistent development shape today is a single-host
loopback instance — see [Self-hosting](self-hosting.md).

## When something goes wrong

| Symptom | Cause and fix |
|---|---|
| `docker is required for Postgres acceptance tests` | Docker is absent or its daemon is unreachable. |
| A suite fails to bind its port | Another process took the loopback port between selection and start. Rerun; the suites pick a free port per run. |
| Leftover `ctower-i1-*` or `ctower-migration-*` Compose projects | A suite was killed before cleanup. List them with `docker compose ls` and remove only the ones you own. |
| `just verify` fails on an unclean tree | Commit or clean first. Stray `__pycache__` output from a targeted test run is a common cause; the recipes export `PYTHONDONTWRITEBYTECODE=1`, a direct `pytest` call does not. |

A nonzero exit from the CLI itself is a typed answer, not a crash. The
[exit-code table](reference/cli.md#exit-codes) says which ones are safe to retry.

## Next

- [CLI reference](reference/cli.md) — the exact command surface and its current gaps.
- [Development guide](contributing/development.md) — what to read before changing code or contracts.
- [Documentation policy](contributing/documentation.md) — what belongs on this site and what stays internal.
