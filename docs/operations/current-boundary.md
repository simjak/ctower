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

## Local CP3-C recovery evidence

The repository has local/verifier-only CP3-C evidence for digest-bound object handling, [backup and
anchors](backup-and-anchors.md), [key recovery](key-recovery.md), [isolated restore](isolated-restore.md),
[rollback](rollback.md), and [recovery evidence](recovery-evidence.md). These bounded procedures do not
provide external targets, a supported installation, production activation, or CP3-D recovery.

A lean Docker Compose deployment direction may be proposed in future work, but no product Compose contract
has shipped. Production deployment, configuration, monitoring, and recovery require their own conformance
evidence and operator path.
