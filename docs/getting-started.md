# Exercise the development walking slice

This is not a product quickstart. ctower has no supported service installation or deployment path. The
current walking slice is exercised by repository verification against disposable fixtures.

## Before you run it

Complete [Repository setup](start-here/repository-setup.md). The full gate requires Docker Compose because
the Increment-1 acceptance tests start a disposable PostgreSQL 17 fixture. The fixture is loopback-only,
uses temporary storage, and is torn down by the tests; it is not a ctower Compose deployment.

Run the complete gate only from a clean committed candidate:

```bash
just verify
```

`just verify` runs the warm checks, required suites, branch coverage, generated-drift checks, history secret
scan, and clean-tree proof. It validates the repository and its current development evidence. It does not
install ctower, make the local database durable, create a supported tenant, or prove production recovery.

## What the development slice proves

The tests cover a one-use first-tenant ceremony; durable ticket facts and custody; the protected Proof and
four-stage Workflow fixture; a read-only Board projection; the thin online CLI subset; and selected
idempotency, authorization, projection, health, and acknowledgement behaviours. See
[Project status](project-status.md) for the precise boundary.

The normal development configuration reports `pending_only`. A separate verifier-owned primary/standby
PostgreSQL topology exercises acknowledged durability. Neither topology is a supported operational setup.

## Where to inspect the exact surface

- [OpenAPI](https://github.com/simjak/ctower/blob/main/contracts/http/openapi.yaml) is the authored HTTP
  contract for the development slice.
- [`apps/ctowerctl/README.md`](https://github.com/simjak/ctower/blob/main/apps/ctowerctl/README.md) defines
  the smaller online CLI subset.
- [Contracts](https://github.com/simjak/ctower/tree/main/contracts) and
  [packs](https://github.com/simjak/ctower/tree/main/packs) distinguish authored inputs from activated
  behaviour.

Do not turn test fixtures into a real-work environment. Read
[What is deliberately unavailable](start-here/availability.md) before proposing an integration.
