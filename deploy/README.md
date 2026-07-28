# Deployment homes

Deployment configuration belongs here; runtime credentials do not.

`development/compose.yaml` is a disposable PostgreSQL 17 fixture for Increment-1 acceptance tests. It is
loopback-bound, uses temporary storage, and does **not** compose a ctower API, control worker, durable
topology, credentials, backups, or a product deployment.

The repository also contains observability collector, dashboard, and alert homes.
`private-vps/development/` is a secret-free, exact-bound reference composition of the one-host development
shape; it is source verification material, not the topology of the separately proven E2 shadow runtime or
an operator installation path. A signed 2026-07-28 E2 observation is retained in Mission Control artifact
`coordination/2026-07-28_1030--engineer-r2164-e2-runtime--persistent-slice.status.md`; it recorded
supervised systemd API/worker units and a persistent PostgreSQL 17.10 synchronous development-ACK pair
while remaining `CP3_D_NOT_PROVEN`. It is dated provenance, not current health.
`private-vps/` also contains the CP3-C recovery templates. None establishes a supported product
deployment: there is no released image, credential ceremony, supported activation path, external failure
domain, or production durability switch. Those require CP3-D conformance evidence before becoming
operator deployment documentation.
