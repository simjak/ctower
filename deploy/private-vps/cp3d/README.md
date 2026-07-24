# CP3-D PostgreSQL operator-binding packet

This directory is a secret-free source packet for one PostgreSQL 17 primary and one physical
synchronous standby. The two Compose projects are deliberately independent: install
`primary.compose.yaml` only on host A and `standby.compose.yaml` only on host B.

The packet state is `READY_FOR_OPERATOR_BINDING`. It is not CP3-D evidence, a product deployment,
or permission to enable `cutover_rpo0`. The repository has no supported ctower product image or
installation contract, so these projects contain PostgreSQL only. They do not invent an API,
worker, scheduler, failover controller, or application service.

## Safety boundary

- PostgreSQL is fixed to major version 17 and an operator-supplied immutable image digest.
- The primary requires `FIRST 1 (ctower_i1_ack)` and `remote_apply`. The standby presents the exact
  `application_name=ctower_i1_ack` and uses a root-owned passfile reference.
- Both projects use host networking but bind PostgreSQL to the declared RFC1918/ULA address. They
  publish no port, accept no environment credential, start under the dormant
  `operator-start-only` profile, and keep `restart: "no"`.
- `pending_only` is the only accepted packet policy. Even a fully bound packet cannot activate
  accepted writes.
- `docker compose config --format json` is local parsing. It does not contact the Docker daemon or
  create a container, network, volume, image, or credential.
- A same-machine render is mechanics evidence only. Every manifest has `cp3d_qualified=false` and
  `external_evidence_claim=not_exercised`.

Do not place a password, token, private key, certificate contents, wrapped key, connection URI, or
credential value in the bindings JSON. A passfile, TLS material, workload identity, Vault/KMS key,
alert route, account, signature, and evidence item appear only as root-owned file metadata or a
reference URI.

## Bind the operator facts

Copy `bindings.synthetic.json` to a root-owned working location outside Git. Set
`binding_kind` to `operator_bound`, set `validation_context` to `distinct_host_review`, and replace
every value containing `synthetic`. Operator-bound input containing that word is rejected.

The following facts are mandatory; names are the exact JSON paths to replace:

| Required operator fact | Binding path |
| --- | --- |
| Provider, region, zone, host, failure domain, operator domain | `primary.*`, `standby.*` |
| Private RFC1918/ULA endpoint and PostgreSQL data directory | `primary.private_ip`, `standby.private_ip`, each `data_directory` |
| PostgreSQL 17 image tag plus immutable digest and runtime UID/GID | `postgres.image`, `postgres.uid`, `postgres.gid` |
| Root-owned PostgreSQL/HBA/TLS inputs with reference, path, group, mode, digest | `primary.*_config`, `primary.tls_*`, matching `standby` fields |
| Root-owned standby replication passfile metadata | `standby.replication_passfile` |
| Separate primary, standby, backup, object, anchor, recovery identities | `workload_identities.*` |
| HTTPS S3 endpoint/account/region and three distinct buckets | `object_store.*` |
| Versioning, Object Lock, retention | `object_store.versioning`, `object_store.object_lock`, `object_store.retention_days` |
| Vault/KMS versioned key refs, public-key digest, recovery principal/owner | `key_recovery.*` |
| Alert destination reference and accountable owner | `alerting.*` |
| Authorized destructive-drill window | `destructive_drill_window` |
| Accepted synchronous-ACK latency and signed measurement | `ack_latency_acceptance.*` |
| Signed topology, network/TLS, Object Lock, and image reviews | `signed_evidence.*` |

File references must resolve below `/etc/ctower/cp3d`, be owned by root, and be exactly `0400` or
`0440`. The host-local preflight also checks the declared group and SHA-256 without printing file
contents. The PostgreSQL data directory must be a real directory, owned by the bound PostgreSQL UID,
and have no group write or other permissions.

## Progressive ceremony

Run from a clean ctower checkout with Python 3.12+ and the repository dependencies installed.
These first commands are source-only and may use the committed synthetic fixture:

```bash
export PYTHONDONTWRITEBYTECODE=1
python3 -m tools.cp3d_packet validate \
  --bindings deploy/private-vps/cp3d/bindings.synthetic.json
python3 -m tools.cp3d_packet compose-config \
  --bindings deploy/private-vps/cp3d/bindings.synthetic.json --role primary
python3 -m tools.cp3d_packet compose-config \
  --bindings deploy/private-vps/cp3d/bindings.synthetic.json --role standby
python3 -m tools.cp3d_packet render \
  --bindings deploy/private-vps/cp3d/bindings.synthetic.json
```

For the real ceremony, an authenticated operator first provisions the two VPSs, private network,
firewall, root-owned TLS/replication files, data directories, object targets, workload identities,
Vault/KMS references, and alert route. Those are external security-boundary changes, not actions
performed by this packet.

On host A and host B independently, validate the operator-bound file and inspect only that host's
installed references:

```bash
sudo chown root:root /etc/ctower/cp3d/bindings.operator.json
sudo chmod 0400 /etc/ctower/cp3d/bindings.operator.json
python3 -m tools.cp3d_packet validate --bindings /etc/ctower/cp3d/bindings.operator.json
python3 -m tools.cp3d_packet render --bindings /etc/ctower/cp3d/bindings.operator.json
sudo -- python3 -m tools.cp3d_packet preflight \
  --bindings /etc/ctower/cp3d/bindings.operator.json --role primary
sudo -- python3 -m tools.cp3d_packet preflight \
  --bindings /etc/ctower/cp3d/bindings.operator.json --role standby
```

Run the primary preflight on host A and the standby preflight on host B. Running both on one machine
is explicitly test mechanics and never satisfies the failure-domain gate.

After independent Review/CSO compare the canonical manifest bytes and an authenticated operator
authorizes host installation, render and install only the matching project. The rendered Compose JSON
contains paths and reference identifiers but no credential values:

```bash
# Host A: render primary only, then create a stopped container.
python3 -m tools.cp3d_packet compose-config \
  --bindings /etc/ctower/cp3d/bindings.operator.json --role primary \
  | sudo tee /etc/ctower/cp3d/primary.compose.rendered.json >/dev/null
sudo chmod 0440 /etc/ctower/cp3d/primary.compose.rendered.json
docker compose -f /etc/ctower/cp3d/primary.compose.rendered.json \
  --profile operator-start-only create --no-build --pull never

# Host B: render standby only, then create a stopped container.
python3 -m tools.cp3d_packet compose-config \
  --bindings /etc/ctower/cp3d/bindings.operator.json --role standby \
  | sudo tee /etc/ctower/cp3d/standby.compose.rendered.json >/dev/null
sudo chmod 0440 /etc/ctower/cp3d/standby.compose.rendered.json
docker compose -f /etc/ctower/cp3d/standby.compose.rendered.json \
  --profile operator-start-only create --no-build --pull never
```

Container start, base-backup/bootstrap, replication-slot creation, firewall/TLS changes, promotion,
host poweroff, restore enablement, and cleanup require the authenticated external ceremony. After an
authorized start, observation is read-only: verify `application_name = 'ctower_i1_ack'`,
`sync_state = 'sync'`, replay/flush LSNs, TLS peer identity, and measured ACK latency. Keep ctower
`pending_only`; the absent product image/runtime means no application acceptance claim is possible.

For rollback, stop the affected project and return to `pending_only`. Do not remove the data volume or
destroy either VPS. Destructive cleanup is a separate operator decision.

## Choice audit and accepted debt

- Compose was chosen as the smallest independently runnable VPS substrate. It does not provide
  scheduling, HA election, provider discovery, secret distribution, or fencing.
- Host networking avoids a cross-host overlay and network objects; it depends on the external
  private-interface and firewall proof.
- The least-trusted facts are operator/failure-domain independence, measured ACK latency, Object Lock
  enforcement, TLS identity, and the image attestation. Typed declarations cannot prove those facts;
  their signed evidence remains an external gate.
- The synthetic image digest is intentionally non-runnable mechanics data. A real, independently
  attested PostgreSQL 17 digest is required before host preflight.
- Ctower still lacks a supported product image/runtime and installation contract. This packet cannot
  deploy the API/control worker or claim CP3-D, I1, accepted-record RPO 0, restore, reboot, or failover
  evidence.

Recovery and evidence procedures remain in the linked CP3-C runbooks. They become CP3-D evidence only
after the real two-host topology and destructive drills are independently verified.
