# Persistent shadow-only development runtime

This is the supported E2 walking slice for local dogfood on one private VPS. It is always
`SHADOW_ONLY_CP3_D_NOT_PROVEN`: it is not a production deployment, does not authorize the
`development_single_writer` epoch, and must contain only low-value reconstructible work.

The fixed topology is a PostgreSQL 17 primary and named physical ACK standby in persistent Docker
volumes, a loopback-only API, and a same-wheel control worker. The worker includes the ordinary bounded
durability finalizer. Docker publishes PostgreSQL only on `127.0.0.1`; the API binds only to
`127.0.0.1:8091`. No firewall, DNS, TLS endpoint, or external listener is created.

Configuration under `~/.config/ctower/` contains labels, ports, image digests, and Secret Service
references only. PostgreSQL passwords and operator/commander bearer values live in the allowlisted OS
keyring. The systemd units contain no secret values. Release directories live under
`~/.local/share/ctower-development/releases/`; staged releases become visible only when complete, and a
strict owner-only transition journal makes `current`/`previous` pointer updates crash-resumable.

This unattended linger host uses the passwordless GNOME login collection of a dedicated development
account, owner-only on disk, and an exact user unit that unlocks that login collection before ctower
starts. This is a development-keyring tradeoff for this shadow instance, not a production secret-at-rest
claim. Values never appear in ctower config, unit, environment, argument, or plaintext credential files.
PostgreSQL host authentication is SCRAM from initial publication. A network-isolated initializer reads the
referenced administrator secret through stdin, leaves only the initialized volume, and is replaced by the
steady-state published container with no password environment entry; standby cloning is likewise
stdin-only.

From a clean release source tree, build the wheel with the approved standard-GIL interpreter and bind it:

```text
uv build --wheel --python /path/to/python3.13
ctower-release-manifest build --source-root . --wheel dist/ctower_workspace-0.0.0-py3-none-any.whl \
  --output dist/development-manifest.json --python /path/to/python3.13
ctower-private-vps install-release --wheel dist/ctower_workspace-0.0.0-py3-none-any.whl \
  --manifest dist/development-manifest.json --packs packs --python /path/to/python3.13 \
  --source-root .
```

For an upgrade, add `--predecessor sha256:<current-manifest-sha256>` to the manifest build,
where the value is the SHA-256 digest of the exact `current/manifest.json`. Omit it only
when no current release exists. Installation refuses a predecessor that does not match the
current pointer.

First install:

```text
ctower-private-vps database-up
ctower-private-vps install-units --unit-root deploy/private-vps/development/systemd
ctower-private-vps bootstrap
ctower-private-vps observe
```

Bootstrap persists only a command ID and Secret Service reference until the first-tenant operation,
credential bindings, state write, and service activation finish. Re-running the same command resumes that
checkpoint; it never mints a replacement capability for a partial bootstrap.

`observe` reports `finalizer_health` separately from policy health. It is `HEALTHY` only while the worker
unit is active and a completed finalizer scan (including an empty scan) advanced within ten seconds.
Missing or malformed progress, an inactive/crash-looping worker, a failed scan, a refused command, future
clock data, or progress older than ten seconds is typed `DEGRADED`; unknown is never treated as healthy.

Drive the instance only through the protected public CLI wrapper:

```text
ctower-shadow-ctl ticket create ...
ctower-shadow-ctl ticket query TICKET_ID
ctower-shadow-ctl synthetic run --workflow ctower.trust-spine-four-stage@1 \
  --wait --assert resolved,closed
```

`ctower-private-vps rollback` journals and completes the exact `current`/`previous` exchange before
restarting the API and worker. Database migrations are append-only; rollback never reverses accepted facts
or resumes a legacy writer.

The Docker containers use `--restart unless-stopped`, the user units are enabled under
`default.target`, and user lingering is a host prerequisite. A service restart is proven in this slice;
an actual host reboot remains deferred operational evidence unless the operator schedules it.

Explicit debt: TLS and any external endpoint, complete telemetry/export, backup/key-recovery/restore
drills, independent failure-domain ACK, CP3-D, production claims, and authoritative-writer promotion.
