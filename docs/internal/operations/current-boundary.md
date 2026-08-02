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
see [Observability](observability.md) and [Secret handling](../../security/secret-handling.md).

## Local CP3-C recovery evidence

The repository has local/verifier-only CP3-C evidence for digest-bound object handling, [backup and
anchors](backup-and-anchors.md), [key recovery](key-recovery.md), [isolated restore](isolated-restore.md),
[rollback](rollback.md), and [recovery evidence](recovery-evidence.md). These bounded procedures do not
provide external targets, a supported installation, production activation, or CP3-D recovery.

A lean Docker Compose deployment direction may be proposed in future work, but no product Compose contract
has shipped. Production deployment, configuration, monitoring, and recovery require their own conformance
evidence and operator path.

## Development authority and full-I1 boundary

The current I1.7A surface exposes strict cutover-health and read-only Project Delivery data and accepts the
documented migration command spellings only as authenticated, online-only refusal stubs. That current
visibility does not establish fresh-database authority, carry an item forward, issue a CT-I1-008 verdict,
or prove CP3-D. Mission Control remains the writable ctower-project source.

The approved later development path creates the ctower Company / Project / checkpoint hierarchy and
Project Delivery projection on a fresh database. It retains the complete legacy corpus as signed read-only
provenance and recreates only an exact reviewed still-actionable set through ordinary generated API/CLI
commands with stable legacy aliases and source digests. Bulk legacy import is dormant behind a separate
future decision; there is no corpus importer, automatic backfill, or dual-write interval.

CT-I1-008 is the development dogfood go/no-go. It may be `GO_WITH_LIMITS` while CP3-D is red and may
complete only the development Project Delivery pilot/I1.7 checkpoint for reconstructible ctower
engineering data. Credentials, accounting, production authority/effects, incidents, client data, and
irreplaceable artifacts remain forbidden, and health must continue to expose `CP3_D_NOT_PROVEN`.

Full normative I1 exit remains `NO-GO` until CP3-D proves external-failure-domain acknowledgement, key
recovery, isolated destructive restore, and measured RPO/RTO. The CT-I2-001 dependency on CT-I1-008 means
that full exit, not a development `GO` or `GO_WITH_LIMITS`; I2 is unauthorized while CP3-D is red.
