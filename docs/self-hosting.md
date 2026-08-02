# Self-hosting

Production self-hosting is not available in this revision.

ctower has no supported production image or package, internet-facing API topology, browser UI, backup and
restore runbook, independent failure-domain acknowledgement, credential rotation procedure, monitoring and
incident path, or compatibility promise. Publishing setup steps without those pieces would turn a
development fixture into an unsupported source of truth.

## What exists

The repository contains a loopback-only shadow runtime for one private development host. It is restricted
to low-value, reconstructible dogfood and reports `SHADOW_ONLY_CP3_D_NOT_PROVEN`. Its same-host standby is
useful development evidence; it is not proof that data survives loss of the host.

The checked-in recovery templates likewise describe required shapes without activating a target. They use
secret references rather than values and remain internal verification material.

## What must be true before a production guide can exist

A future self-hosting guide needs accepted, repeatable evidence for all of these:

1. a published, immutable runtime artifact and supported runtime matrix;
2. an external TLS endpoint with an explicit authentication and network boundary;
3. PostgreSQL acknowledgement outside the primary host's failure domain;
4. encrypted off-host backups, independently controlled key recovery, isolated restore, and measured RPO/RTO;
5. migration, upgrade, rollback, and incident procedures tested against the released artifact;
6. health, telemetry, alerting, and operator ownership that fail closed on unknown state;
7. a supported UI or an explicit CLI/API-only production contract.

Those are product and operations capabilities, not missing prose. Until they land, there is no honest
production setup command to run or document.

For a safe first look today, use the disposable [Getting started](getting-started.md) tour. For the exact
database-fixture finding, see [Local development](local-development.md).
