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

## I1.7A cutover boundary

I1.7A exposes strict cutover-health and read-only Project Delivery data and accepts the documented
migration command spellings only as authenticated, online-only refusal stubs. It does not freeze Mission
Control, import a record, publish a client pointer, commit an epoch, or enable ctower-project writes.

I1.7B owns source selection/import/reconciliation and the legacy fence. I1.7C owns the development epoch
and dogfood proof. Even then the allowed cohort is reconstructible ctower engineering data only and health
must remain `CP3_D_NOT_PROVEN` until the separate CP3-D promotion gate passes.
