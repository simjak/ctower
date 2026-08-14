# What is deliberately unavailable

ctower is pre-alpha. The repository proves a development slice and offers one private, loopback-only
self-hosted shadow; it does not offer a production service. Do not infer availability from a schema,
package boundary, generated client, test fixture, or roadmap item.

## Do not attempt these yet

- Exposing ctower as an internet-facing or team-shared service.
- Treating the local checkpoint, restore, migration, upgrade, or monitoring tools as supported production
  procedures.
- Managing real tenants, tickets, credentials, or production work.
- Treating the development CompanyBundle pointer as runtime/effect activation or a production rollout.
- Using a product browser UI, runner, local/remote agent adapter, or external effect provider. The separate
  development Inbox controls are not a supported product UI.
- Depending on a published package, stable Python runtime, compatibility promise, or production release.

The checked-in Compose file supports disposable PostgreSQL acceptance tests. The separate
[self-hosting boundary](../self-hosting.md) installs a fixed loopback-only development topology whose
primary and standby share one host.

## What is safe to do

- Read the public concepts and exact CLI/API references.
- Run repository verification against synthetic/disposable fixtures.
- Exercise the protected CLI/spool and CompanyBundle guides against disposable verifier fixtures.
- Install the private loopback shadow for reconstructible, low-value work by following the exact
  self-hosting boundary and accepting its same-host durability limit.
- Inspect the read-only Console server contract without treating it as a supported browser product.
- Improve documentation, contracts, tests, or one complete development vertical through the contribution
  process.

For the current repository structure and responsibility boundaries, use the
[architecture atlas](https://github.com/simjak/ctower/blob/main/ARCHITECTURE.md).
