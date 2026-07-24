# Deployment homes

Deployment configuration belongs here; runtime credentials do not.

`development/compose.yaml` is a disposable PostgreSQL 17 fixture for Increment-1 acceptance tests. It is
loopback-bound, uses temporary storage, and does **not** compose a ctower API, control worker, durable
topology, credentials, backups, or a product deployment.

The repository also contains observability collector, dashboard, and alert homes. `private-vps/` adds the
secret-free CP3-C recovery shape and a [CP3-D PostgreSQL operator-binding
packet](private-vps/cp3d/README.md). The latter is a source-only pair of independent Compose projects,
not a product stack. None establishes a supported product deployment: there is no ctower product image,
external endpoint, credential, systemd activation, or production durability switch. Those require real
two-host CP3-D conformance evidence before becoming operator deployment documentation.
