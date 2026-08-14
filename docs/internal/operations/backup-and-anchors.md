# Backup and anchor operation

CP3-C defines a fixed daily full-backup operation and an append-only anchor operation. It does not
activate either against production. CP3-D must supply the external targets, workload identities, key
references, and alert routes.

## Daily backup

Before a run, verify the configured `pgBackRest` and `pg_dump` binaries against their pinned SHA-256
digests. The application invokes only:

1. `pgBackRest` full backup with the authored config and stanza;
2. `pg_dump --format=custom --no-password` against one configured service;
3. fixed evidence reads for the base manifest, WAL interval, logical dump, object manifest, migration
   manifest, repository version, and key reference.

A zero exit code is insufficient. Do not insert `backup_manifests` or
`backup_verification_receipts` unless every artifact exists, is nonempty, is digest-verified, the WAL
stop LSN does not regress, and the external key reference is verified. Preserve the manifest and
receipt digests in the recovery evidence bundle.

## Record anchor

Build each anchor from a contiguous accepted-root range and the previous anchor digest. Ask the
external signing authority to sign that exact digest, conditionally create the immutable external
object, read it back, and verify the external signature before inserting `record_anchor_receipts`.
Never retry by changing an already used anchor identity. An exact replay may return the existing
receipt; a changed digest, range, object version, key reference, or signature is an integrity incident.

## Failure

Keep the failed run visible and do not manufacture a success receipt. Missing WAL, object, key,
signature, or readback evidence leaves the backup/anchor unavailable and the installation degraded.
Follow [recovery evidence](recovery-evidence.md) for capture and [rollback](rollback.md) for a
software-only rollback.
