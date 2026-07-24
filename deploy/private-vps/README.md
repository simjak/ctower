# Private-VPS durability and recovery packets

These files describe the local recovery shape without activating a production target. They contain
identifiers and references only. Do not add passwords, tokens, private keys, wrapped data keys, TLS
private keys, or recovered plaintext.

CP3-C keeps all of these facts disabled until CP3-D supplies and verifies them:

- a standby outside the primary failure domain;
- versioned off-host backup, object, and anchor locations;
- separate backup, object, anchor, and restore workload identities;
- KMS/Vault key references and an independently controlled recovery identity;
- alert routes, destructive-drill windows, and measured RPO/RTO evidence;
- the `cutover-rpo0` durability policy.

`cp3c.env.example` is an inventory template, not an environment file to source. Values ending in
`_REF` must resolve through root-owned workload identity configuration outside the application.
`pgbackrest.conf.example` and `postgresql-recovery.conf` show required invariants but are not deployable
until every `CP3D_REQUIRED` marker has been replaced and independently reviewed.

The application continues with `pending_only`, object-only switching remains off, and restored
installations remain quarantined until the exact report/installation enablement receipt exists.

`cp3d/` adds the source-only PostgreSQL Compose packet for operator binding. It has two independently
runnable host projects, strict typed validation, local `docker compose config` rendering, host-local
root-owned file checks, and a canonical redacted topology manifest. It remains `pending_only` and
cannot claim CP3-D: provider provisioning, network/TLS policy, credentials, actual two-host
replication, destructive drills, and the missing ctower product image/runtime remain external.

Runbooks:

- [CP3-D PostgreSQL operator-binding packet](cp3d/README.md)
- [backup and anchors](../../docs/operations/backup-and-anchors.md)
- [key recovery](../../docs/operations/key-recovery.md)
- [isolated restore](../../docs/operations/isolated-restore.md)
- [rollback](../../docs/operations/rollback.md)
- [evidence capture](../../docs/operations/recovery-evidence.md)
