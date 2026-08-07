# What is deliberately unavailable

ctower is pre-alpha. The repository can prove parts of a development slice without offering an operator
product. Do not infer availability from a schema, package boundary, generated client, test fixture, or
roadmap item.

## Do not attempt these yet

- Deploying ctower as a networked or internet-facing service. The one supported self-hosted shape is a
  single-host, loopback-only instance for reconstructible work; see [Self-hosting](../self-hosting.md).
- Composing an application stack from `deploy/development/compose.yaml`; it publishes a database only.
- Running a supported backup, restore, recovery, monitoring, or incident procedure.
- Managing real tenants, tickets, credentials, or production work.
- Treating the development CompanyBundle pointer as runtime/effect activation or a production rollout.
- Treating the read-only operator UI as the supported I2.4 browser product, a write authority, or part of
  the self-hosted install; using a runner, local/remote agent adapter, or external effect provider.
- Treating the dark-by-default OIDC scaffold as an activated, supported human-provider login path.
- Depending on a published package, stable Python runtime, compatibility promise, or production release.

The checked-in Compose file supports disposable PostgreSQL fixtures only. Read
[Local development](../local-development.md) before treating it as infrastructure.

## What is safe to do

- Read the canonical design and decisions.
- Run repository verification against synthetic/disposable fixtures.
- Exercise the protected CLI/spool and CompanyBundle guides against disposable verifier fixtures.
- Improve documentation, contracts, tests, or one complete development vertical through the contribution
  process.

For the working path, use [Getting started](../getting-started.md). For the current product boundary, use
the [Overview](../index.md) and [Self-hosting](../self-hosting.md).
