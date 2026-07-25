# What is deliberately unavailable

ctower is pre-alpha. The repository can prove parts of a development slice without offering an operator
product. Do not infer availability from a schema, package boundary, generated client, test fixture, or
roadmap item.

## Do not attempt these yet

- Installing or deploying ctower as a service, with Docker Compose or otherwise.
- Running a supported backup, restore, migration, recovery, monitoring, or incident procedure.
- Managing real tenants, tickets, credentials, or production work.
- Treating the development CompanyBundle pointer as runtime/effect activation or a production rollout.
- Using a browser UI, runner, local/remote agent adapter, or external effect provider.
- Depending on a published package, stable Python runtime, compatibility promise, or production release.

The checked-in Compose file supports disposable PostgreSQL acceptance tests only. Read
[Current operational boundary](../operations/current-boundary.md) before treating it as infrastructure.

## What is safe to do

- Read the canonical design and decisions.
- Run repository verification against synthetic/disposable fixtures.
- Exercise the protected CLI/spool and CompanyBundle guides against disposable verifier fixtures.
- Improve documentation, contracts, tests, or one complete development vertical through the contribution
  process.

For precise current evidence, use [Project status](../project-status.md). For planned sequence and exit
criteria, use the [implementation roadmap](https://github.com/simjak/ctower/blob/main/IMPLEMENTATION-ROADMAP.md)
and [system specification](https://github.com/simjak/ctower/blob/main/SPEC.md).
