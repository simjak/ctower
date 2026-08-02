# Deployment homes

Deployment configuration belongs here; runtime credentials do not.

`development/compose.yaml` is a disposable PostgreSQL 17 fixture for Increment-1 acceptance tests. It is
loopback-bound, uses temporary storage, and does **not** compose a ctower API, control worker, durable
topology, credentials, backups, or a product deployment. The reader-facing account of how the suites drive
it, and of what a composed stack would still need, is `docs/local-development.md`.

The repository also contains observability collector, dashboard, and alert homes. `private-vps/` adds the
secret-free CP3-C recovery shape. Neither establishes a supported product deployment: there is no external
endpoint, credential, systemd activation, or production durability switch. Those require CP3-D conformance
evidence before becoming operator deployment documentation.

The operator-approved E2 exception is the loopback-only
[`private-vps/development`](private-vps/development/README.md) walking slice. It is a supported development
runtime, always says `SHADOW_ONLY_CP3_D_NOT_PROVEN`, and activates neither production nor authoritative
single-writer scope. That runbook is the install, upgrade, and rollback authority;
`docs/self-hosting.md` is its public front door and states the boundary a self-hoster is accepting.
