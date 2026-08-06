# Self-hosting

You can run one ctower instance on a machine you control, keep tickets in it, and drive it from the CLI.
That instance is loopback-only and explicitly labeled `SHADOW_ONLY_CP3_D_NOT_PROVEN`. It is the whole of
what self-hosting means in this revision.

You cannot yet run ctower as an internet-facing service. There is no published runtime artifact, no TLS or
external endpoint, no installed browser UI, no off-host durability proof, and no compatibility promise. The
repository's separate read-only operator UI is development dogfood and is not installed or served by this
topology. Those are missing product capabilities, not missing instructions — [what still blocks
production](#what-still-blocks-production) lists them exactly.

!!! danger "Reconstructible work only"
    Put nothing in this instance that you could not rebuild by hand. Its standby lives on the same host, so
    losing the host loses the data. Its durability status reports `DEGRADED` with reason
    `development_offhost_ack_cp3_d_not_proven`, permanently and by design, until off-host acknowledgement
    is proven.

## Is this instance for you?

| You want | This instance |
|---|---|
| A private ticket record you drive from the CLI on one host | Yes — that is exactly its job |
| To dogfood ctower on real but low-value work | Yes, with reconstructible work only |
| A team-shared service reachable over a network | No — it binds `127.0.0.1` and creates no external listener |
| A browser UI from this install | No — the repository's read-only operator UI is a separate dogfood surface |
| Durability against losing the host | No — the acknowledging standby is on the same host |

## What gets installed

A fixed single-host topology:

- PostgreSQL 17 as a primary and a named physical acknowledging standby, in persistent Docker volumes, both
  published on `127.0.0.1` only;
- the ctower API, bound to `127.0.0.1` on the port your configuration names — `8091` in the reference
  install, and the only host value the strict configuration accepts is loopback;
- a control worker from the same wheel, running the bounded durability finalizer;
- four systemd **user** units — `ctower-development-keyring`, `-db`, `-api`, `-worker` — plus a
  `ctower-development.target` that requires all four, each enabled under `default.target`, with the
  containers set to `--restart unless-stopped`;
- configuration under `~/.config/ctower/` holding labels, ports, image digests, and secret *references*.

No firewall rule, DNS record, TLS endpoint, or external listener is created. PostgreSQL passwords and the
operator and commander bearer values live in the OS keyring; no unit, config file, environment variable, or
argument ever holds a secret value. The verified runtime is installed once at
`~/.local/share/ctower-development/runtime/`.

## Host prerequisites

- Linux with systemd user units and lingering enabled for a dedicated account that owns the instance.
- Docker, usable by that account.
- Python 3.13 with the standard GIL, at a path you name explicitly.
- A Secret Service keyring for that account. The reference host uses a passwordless login collection
  unlocked by its own user unit before ctower starts — a development-keyring tradeoff for an unattended
  host, not a production secret-at-rest claim.
- A clean checkout of this repository.

## Installing

The install ceremony is the runbook at
[`deploy/private-vps/development/README.md`](https://github.com/simjak/ctower/blob/main/deploy/private-vps/development/README.md).
Follow it there rather than a summary: its commands are exact, ordered, and refuse to continue when a
precondition is unmet.

Its shape is:

1. build a wheel and a disposable bootstrap environment outside the checkout;
2. run the read-only runtime preflight, which loads every declared console script from the candidate
   environment and refuses the install on any missing, unimportable, or malformed entry point;
3. build the runtime manifest, then `install-runtime` — first-install-only, refusing an existing runtime
   path — into the permanent virtual environment;
4. `database-up` to create the primary and standby pair and apply migrations under an advisory lock;
5. `install-units`, then `bootstrap` for the first tenant, Operator, and Commander;
6. `observe` to confirm the result.

The bootstrap step persists only a command ID and a secret reference until the first-tenant operation,
credential binding, state write, and service activation all finish. Re-running it resumes that checkpoint
instead of minting a second capability.

This page does not restate those commands, because they are first-install-only mutations of a fixed path
and were not re-executed to write it. The verification commands below were.

## Verifying an instance

All four units should be active:

```bash
systemctl --user is-active ctower-development-keyring.service ctower-development-db.service \
  ctower-development-api.service ctower-development-worker.service
```

```text
active
active
active
active
```

The instance's own observation is one secret-free JSON object:

```bash
~/.local/share/ctower-development/runtime/venv/bin/ctower-private-vps observe
```

Read four things in it. `label` must be `SHADOW_ONLY_CP3_D_NOT_PROVEN`. `api`, `worker`, and `database` must
be `active`, with both containers `running` and `replication` reporting `["streaming", "sync"]`.
`finalizer_health.status` must be `HEALTHY` — it means the worker is active *and* a completed scan,
including an empty one, advanced within the last ten seconds; missing progress, a crash-looping worker, a
failed scan, or future clock data is typed `DEGRADED`, and unknown is never treated as healthy.
`durability_health` reports `DEGRADED` with reason `development_offhost_ack_cp3_d_not_proven`; that one is
the permanent shadow-only status, not a fault.

Ask the product itself through the protected CLI wrapper:

```bash
~/.local/share/ctower-development/runtime/venv/bin/ctower-shadow-ctl control health
```

The reply is a `ctower.health/v1` document whose contributors report per-owner status and watermarks.
Overall `DEGRADED` from the durability contributor is expected here. Contributors reported as
`STATE_UNKNOWN` with `not-applicable-in-cp3-b` are capabilities this checkpoint does not implement —
backup, object store, anchor, and synthetic — and unknown is deliberately never rendered as healthy.

The API answers nothing without authority. A request with no credential is refused before any read — use
your own API port:

```bash
curl -si --max-time 5 http://127.0.0.1:8091/health | head -1
```

```text
HTTP/1.1 401 Unauthorized
```

## Using and operating it

Drive the instance only through the protected wrapper — `ctower-shadow-ctl ticket create`,
`ticket query`, `board query`, `synthetic run`. It is the same command surface as the
[CLI reference](reference/cli.md), pinned to this instance's base URL and authority.

For upgrades, the same runbook owns the procedure, and its rules matter more than its commands:

- an upgrade is a filesystem replacement — one `renameat2(RENAME_EXCHANGE)` — that changes runtime files
  only, and running processes keep the old generation until you restart the units;
- it refuses a candidate carrying a database-migration or systemd-unit delta, because hiding that inside a
  filesystem swap is unsafe; such a release needs its own reviewed plan, and the runbook carries one
  worked, migration-specific example;
- rollback swaps the two runtime slots and nothing else. It never reverses a migration, restores a
  database, or restarts a service.

Restarting the services is proven in this slice. Surviving a host reboot is not: lingering and
`default.target` should bring the instance back, but no reboot has been recorded as evidence, so treat the
first one as an exercise you supervise.

Before any upgrade, the runbook takes an encrypted `pg_dumpall` of the cluster and a copy of the installed
wheel, manifest, and packs into a new timestamped archive, reading the database secret through a file
descriptor so it never lands in a file, argument, or environment variable. That archive is rollback
material for an operator decision — not permission to improvise a restore.

## What still blocks production

A future production guide needs accepted, repeatable evidence for all of these. None exists today:

1. a published, immutable runtime artifact and a supported runtime matrix;
2. an external TLS endpoint with an explicit authentication and network boundary;
3. PostgreSQL acknowledgement outside the primary host's failure domain;
4. encrypted off-host backups, independently controlled key recovery, isolated restore, and measured
   RPO/RTO;
5. migration, upgrade, rollback, and incident procedures tested against the released artifact;
6. health, telemetry, alerting, and operator ownership that fail closed on unknown state;
7. promotion or replacement of the read-only operator UI with a supported browser product, or an explicit
   CLI/API-only production contract;

Until they land, the single-host instance above is the honest ceiling, and this page will not describe a
production deployment ctower cannot yet stand behind.

## Next

- [Local development](local-development.md) — the disposable fixtures and the developer gate loop.
- [Getting started](getting-started.md) — the one-command tour, if you have not run it yet.
- [What is deliberately unavailable](start-here/availability.md) — the current capability boundary.
