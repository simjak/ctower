# ctower

ctower is an open-source control plane for durable work performed by humans and replaceable AI agents. It
keeps the work's ownership, workflow position, evidence, decisions, and audit trail authoritative when a
terminal, model, machine, or worker disappears.

> [!IMPORTANT]
> ctower is a **pre-alpha, development-only project**. The only supported install is the private-VPS,
> loopback-only E2 shadow runtime for low-value reconstructible dogfood. It is not a hosted service,
> backup/restore product, browser UI, runner, production release, CP3-D deployment, or source-of-truth
> authority.

## The two-minute orientation

ctower keeps durable authority separate from replaceable execution:

```text
request -> Work -> Workflow -> evidence -> gate -> outcome
             durable control plane       replaceable workers
```

- **Record** preserves accepted facts and their audit trail.
- **Work** is the durable case for an outcome; its Kanban status and Workflow stage are separate facts.
- **Proof** binds evidence to the exact candidate a gate evaluates.
- **Workflow** constrains legal movement; a harness or agent executes work but never becomes the source of
  truth.

Read [Core concepts](https://simjak.github.io/ctower/concepts/) for the shared vocabulary.

## What you can use today

The current development slice has first-tenant bootstrap, durable ticket/comment/Work facts, a six-lane
Board projection, the proof-gated four-stage fixture, generated clients/contracts, a universal
CompanyBundle Catalog checkpoint, and a protected CLI with an encrypted local replay spool. The normal
development configuration is `pending_only`. The operator-approved persistent E2 runtime adds the strictly
development-labeled `development_offhost_ack` mode, an ordinary finalizer, and supervised loopback services;
see [`deploy/private-vps/development`](deploy/private-vps/development/README.md). It is always
`SHADOW_ONLY_CP3_D_NOT_PROVEN` and cannot hold authoritative or irreplaceable work. Local,
verifier-only CP3-C evidence also covers digest-bound object handling, backup and anchors, key recovery,
isolated restore, rollback, and recovery evidence. Those pages describe bounded checkpoints, not a
production recovery service or CP3-D activation.

After following the [repository setup guide](https://simjak.github.io/ctower/start-here/repository-setup/),
clone the repository and run the warm verification gate:

```bash
git clone https://github.com/simjak/ctower.git
cd ctower
just check
```

`just verify` is the full clean-tree verification gate and exercises disposable PostgreSQL acceptance
fixtures through Docker Compose. It validates the repository; it does not install or deploy ctower. See
[the development walking slice](https://simjak.github.io/ctower/getting-started/) for the boundary.

## Current interfaces

- **CLI:** `ctowerctl` and `ctl` expose the authored ticket, Work, Proof, Workflow, Board/health, protected
  outbox, CompanyBundle, and local spool families. Non-bootstrap mutations are encrypted and durable before
  send; Linux verification uses a real Secret Service.
- **HTTP/OpenAPI:** all 41 development operations carry explicit CLI/query-mutation/spool metadata and
  generate the strict client plus runtime contract resource package.
- **CompanyBundle:** validate/plan/export are read-only; apply atomically advances one future-only Catalog
  pointer through server authority. It does not activate runtime/effects.
- **I1.7A visibility:** strict cutover-health and read-only Project Delivery contracts expose the
  development boundary. Migration commands are online-only refusing stubs; they do not import, fence, or
  rewire ctower-project work.
- **Not available:** no published package, external/product deployment, production backup/restore runbook,
  browser UI, runner, remote agent adapter, CP3-D activation, or production release exists.

For the local CP3-C boundary, read [Backup and anchors](https://simjak.github.io/ctower/operations/backup-and-anchors/),
[Key recovery](https://simjak.github.io/ctower/operations/key-recovery/), and
[Isolated restore](https://simjak.github.io/ctower/operations/isolated-restore/). Do not treat these
verifier-only guides as an installation or deployment path.

For the development I1.4 surfaces, read the
[protected CLI guide](https://simjak.github.io/ctower/guides/protected-cli/) and
[CompanyBundle guide](https://simjak.github.io/ctower/guides/company-bundle/).

Public API + protected CLI precede I1 source-of-truth cutover. Browser implementation, browser evidence,
and browser E2E first activate at CT-I2-005 / I2.4.

See [Project status](https://simjak.github.io/ctower/project-status/) for the exact capability
boundary and [the OpenAPI contract](contracts/http/openapi.yaml) for the authored development surface.

## Go deeper

- [Start here](https://simjak.github.io/ctower/project-status/) — maturity, setup, and what not
  to attempt.
- [Development guide](https://simjak.github.io/ctower/contributing/development/) — source ownership and
  verification gates.
- [Security policy](SECURITY.md) — private vulnerability reporting.
- [System specification](SPEC.md), [architecture atlas](ARCHITECTURE.md),
  [decision log](DECISIONS.md), and [implementation roadmap](IMPLEMENTATION-ROADMAP.md) — canonical design
  and delivery sources.

## Contributing

Contributions are welcome, especially work that proves one complete durable path. Read
[CONTRIBUTING.md](CONTRIBUTING.md), the [documentation policy](https://simjak.github.io/ctower/contributing/documentation/),
and [SECURITY.md](SECURITY.md) before opening a pull request.

## License

Apache License 2.0. See [LICENSE](LICENSE).
