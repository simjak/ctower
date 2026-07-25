# Deployment homes

Deployment configuration belongs here; runtime credentials do not.

`development/compose.yaml` is a disposable PostgreSQL 17 fixture for Increment-1 acceptance tests. It is
loopback-bound, uses temporary storage, and does **not** compose a ctower API, control worker, durable
topology, credentials, backups, or a product deployment.

The repository also contains observability collector, dashboard, and alert homes.
`private-vps/development/` is a secret-free, exact-bound reference composition of the one-host development
shape; it is source verification material, not an operator installation path. `private-vps/` also contains
the CP3-C recovery templates. None establishes a supported product deployment: there is no released image,
credential ceremony, systemd activation, external durability target, or production durability switch.
Those require CP3-D conformance evidence before becoming operator deployment documentation.
