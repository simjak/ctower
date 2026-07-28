# Private-VPS development and recovery boundary

## Development reference composition

`development/` is a secret-free, source-verifiable reference composition for one reviewed source-contract
private-VPS shape. Its authored deployment and evidence schemas describe only
`development`/`pending_only`, single-failure-domain, disposable synthetic use. The verifier checks exact
source, image, review-sealed Caddy/collector configuration, identity, UID/GID, root-owned reference,
bootstrap-parent, network, volume, mount, capability, command, and recurrence bindings from bounded
descriptor-confined snapshots. Its recurrence artifact is a deployment contract validation, not a claim
that installed state was observed.

This composition is not an installer, supported deployment, container release, credential ceremony,
CP3-D proof, accepted-write RPO-zero path, or I1 exit. The evidence language cannot represent `i1_exit`;
the CLI refuses that claim before reading a manifest. Do not start the composition with tenant data or
real credentials. Its image digests and external references are examples, and the named volumes remain
inside one failure domain.

## Observed VPS reality

The verification VPS now has a separately gated E2 shadow runtime installed from source
`10951fc3c568f1d6115d1e029b1f0194a6d531a1`, not from this packet's bound current-main source. That
instance has persistent PostgreSQL 17.10 primary and synchronous development-ACK volumes, supervised API
and worker units, ordinary finalizer processing, and lifecycle replay across service restarts and release
swaps. It identifies its policy as `development_offhost_ack` while remaining visibly
`CP3_D_NOT_PROVEN`.

That running instance does not use or validate this reference Compose topology, its example images, its
Caddy/collector configuration, or its self-declared recurrence documents. Conversely, a passing
`development_rehearsal` result from this packet is only source-contract consistency evidence and is not
evidence that the running instance is healthy, installed from this candidate, externally durable,
supported, or production-ready.

## CP3-C recovery templates

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
