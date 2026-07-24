# Current operational boundary

ctower has no supported operational deployment. The checked-in file
[`deploy/development/compose.yaml`](https://github.com/simjak/ctower/blob/main/deploy/development/compose.yaml)
is a disposable PostgreSQL 17 acceptance-test fixture, not a ctower stack.

## What the fixture does

It starts one loopback-bound PostgreSQL container with temporary database storage so Increment-1 acceptance
tests can exercise migrations and process boundaries. The tests create and remove this fixture themselves.

## What it does not do

It does not compose ctower API or control-worker processes, a durable primary/standby pair, credentials,
TLS, an object store, backups, restore, monitoring, or release artifacts. Its trust authentication and
temporary storage are test-fixture choices, not an operational security or durability design.

The development `pending_only` configuration is likewise not a deployment mode. A verifier-owned
primary/standby topology exercises acknowledged durability, but it is not packaged as an operator path.

## Operational guidance today

Use Docker Compose only to run the documented repository acceptance tests. Do not put tenant data,
credentials, or real work into their fixture database. For current health vocabulary and redaction rules,
see [Observability](observability.md) and [Secret handling](../security/secret-handling.md).

A lean Docker Compose deployment direction may be proposed in future work, but no product Compose contract
has shipped. Deployment, configuration, backup/restore, recovery, and operational monitoring guides require
their own executable evidence before they become runbooks.
