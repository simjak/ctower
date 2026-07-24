# Deployment homes

Deployment configuration belongs here; runtime credentials do not.

`development/compose.yaml` is a disposable PostgreSQL 17 fixture for Increment-1 acceptance tests. It is
loopback-bound, uses temporary storage, and does **not** compose a ctower API, control worker, durable
topology, credentials, backups, or a product deployment.

The repository also contains observability collector, dashboard, and alert homes. None establishes a
supported deployment, backup/restore procedure, or operational configuration contract. Compose, Postgres
roles, systemd units, VPS manifests, release images, and root-owned release-supervisor configuration require
their own stable work and conformance evidence before they become operator documentation.
