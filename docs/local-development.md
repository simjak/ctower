# Local development

The repository does **not** currently provide the requested application Compose stack.

The checked-in file `deploy/development/compose.yaml` defines one service: a loopback-bound PostgreSQL 17
fixture with temporary storage. It does not define the ctower API or a UI. This is a tested implementation
finding, not an installation instruction.

The topology check is:

```bash
docker compose --file deploy/development/compose.yaml config --services
```

Its complete output is:

```text
postgres
```

In the R2711 disposable run, that service became healthy on an isolated port. A probe to the isolated API
port failed with curl exit `7` because Compose had started no API listener; the service inventory had no UI
entry or UI port. The project-scoped container and network were then removed.

## The supported developer path

Use the one-command walking slice instead:

```bash
just quickstart
```

That recipe owns the missing composition in a verifier harness: it starts PostgreSQL and an API, installs
the CLI, checks health, exercises the full workflow, and cleans up. It deliberately has no browser step,
because browser implementation remains out of the current accepted product scope.

## Why the gap is not patched here

Adding `api` and `ui` service names would not make a working product stack. A truthful stack also needs an
implemented browser application, API bootstrap and credential ceremony, durable topology, health and
readiness wiring, migration ownership, secret references, and lifecycle/cleanup behavior. The browser
source currently contains architecture declarations only; no frontend framework or runnable UI has been
selected.

Until those capabilities are accepted and implemented, treat the Compose file as a database fixture only.
Do not store real tickets, credentials, or irreplaceable data in it.
