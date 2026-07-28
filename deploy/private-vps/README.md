# CP3-C private-VPS recovery templates

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

Runbooks:

- [backup and anchors](../../docs/operations/backup-and-anchors.md)
- [key recovery](../../docs/operations/key-recovery.md)
- [isolated restore](../../docs/operations/isolated-restore.md)
- [rollback](../../docs/operations/rollback.md)
- [evidence capture](../../docs/operations/recovery-evidence.md)

The separately authorized, shadow-only E2 walking slice is documented under
[`development/`](development/README.md). Its same-VPS ACK copy is deliberately labeled
`CP3_D_NOT_PROVEN` and does not activate any CP3-C/CP3-D target in this directory.
