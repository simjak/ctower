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

The ordinary development `pending_only` configuration is likewise not a deployment mode. A signed
2026-07-28 E2 observation in Mission Control artifact
`coordination/2026-07-28_1030--engineer-r2164-e2-runtime--persistent-slice.status.md` recorded persistent
PostgreSQL 17.10 primary/synchronous-development-ACK storage, supervised API/worker units, ordinary
finalization, and lifecycle replay on that VPS at that time. It is dated provenance, not current health or
a supported operator path, external failure domain, backup/restore proof, or CP3-D result; the observation
remained `CP3_D_NOT_PROVEN`.

`deploy/private-vps/development/compose.yaml` separately records a secret-free reference composition for
an alternate one-host source-contract topology. Its verifier binds the whole normalized Compose authority,
review-sealed Caddy/collector sources, and development recurrence artifacts, but it neither observes nor
describes any current E2 systemd topology and supplies no released image, credentials, installation,
activation, external failure domain, CP3-D proof, or accepted I1-exit claim.

## Operational guidance today

Use Docker Compose only to run the documented repository acceptance tests. Do not put tenant data,
credentials, or real work into either fixture or the private-VPS reference composition. The latter is
present for read-only source/configuration/evidence verification, not as a start command or operator path.
For current health vocabulary and redaction rules, see [Observability](observability.md) and
[Secret handling](../security/secret-handling.md).

## Local CP3-C recovery evidence

The repository has local/verifier-only CP3-C evidence for digest-bound object handling, [backup and
anchors](backup-and-anchors.md), [key recovery](key-recovery.md), [isolated restore](isolated-restore.md),
[rollback](rollback.md), and [recovery evidence](recovery-evidence.md). These bounded procedures do not
provide external targets, a supported installation, production activation, or CP3-D recovery.

The checked-in private-VPS development composition is not a product Compose contract. Production
deployment, configuration, monitoring, and recovery require their own conformance evidence and operator
path.

## I1.7A cutover boundary

I1.7A exposes strict cutover-health and read-only Project Delivery data and accepts the documented
migration command spellings only as authenticated, online-only refusal stubs. It does not freeze Mission
Control, import a record, publish a client pointer, commit an epoch, or enable ctower-project writes.

I1.7B owns source selection/import/reconciliation and the legacy fence. I1.7C owns the development epoch
and dogfood proof. Even then the allowed cohort is reconstructible ctower engineering data only and health
must remain `CP3_D_NOT_PROVEN` until the separate CP3-D promotion gate passes.
