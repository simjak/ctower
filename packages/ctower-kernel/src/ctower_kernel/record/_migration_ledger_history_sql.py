"""Immutable history reads and writes for the private migration ledger."""

from __future__ import annotations

import hmac
from datetime import datetime
from typing import Literal, cast

import psycopg

from ctower_kernel.record._migration_ledger_models import (
    MigrationBaseline,
    MigrationScript,
    MigrationStateError,
)

__all__ = [
    "AppliedMigrationRow",
    "baseline_index",
    "record_migration",
    "validated_applied_prefix",
    "validated_applied_prefix_version",
]

type AppliedMigrationRow = tuple[str, str, str, str, datetime, int | None]


def baseline_index(
    migrations: tuple[MigrationScript, ...],
    baseline: MigrationBaseline,
) -> int:
    for index, migration in enumerate(migrations):
        if migration.migration_id == baseline.through:
            return index
    raise MigrationStateError(
        "baseline-manifest-mismatch",
        f"baseline migration is not a database migration: {baseline.through}",
    )


def validated_applied_prefix(
    connection: psycopg.Connection[tuple[object, ...]],
    migrations: tuple[MigrationScript, ...],
    baseline: MigrationBaseline,
) -> list[AppliedMigrationRow]:
    return validated_applied_prefix_version(
        connection,
        migrations,
        baseline,
        versioned=True,
    )


def validated_applied_prefix_version(
    connection: psycopg.Connection[tuple[object, ...]],
    migrations: tuple[MigrationScript, ...],
    baseline: MigrationBaseline,
    *,
    versioned: bool,
) -> list[AppliedMigrationRow]:
    query = (
        """
        SELECT migration_id, sha256, application_kind,
               result_schema_sha256, applied_at, applied_server_version_num
        FROM ctower_schema_migrations
        ORDER BY migration_id
        """
        if versioned
        else """
        SELECT migration_id, sha256, application_kind,
               result_schema_sha256, applied_at,
               NULL::integer AS applied_server_version_num
        FROM ctower_schema_migrations
        ORDER BY migration_id
        """
    )
    rows = cast(
        list[AppliedMigrationRow],
        connection.execute(query).fetchall(),
    )
    expected_ids = [migration.migration_id for migration in migrations[: len(rows)]]
    actual_ids = [row[0] for row in rows]
    if actual_ids != expected_ids:
        raise MigrationStateError(
            "ledger-history-mismatch",
            "ledger rows are not one contiguous authored migration prefix",
        )
    for row, migration in zip(rows, migrations, strict=False):
        if not hmac.compare_digest(row[1], migration.sha256):
            raise MigrationStateError(
                "ledger-checksum-mismatch",
                f"recorded checksum differs for {migration.migration_id}",
            )
    _validate_baseline_rows(rows, migrations, baseline)
    return rows


def _validate_baseline_rows(
    rows: list[AppliedMigrationRow],
    migrations: tuple[MigrationScript, ...],
    baseline: MigrationBaseline,
) -> None:
    baseline_position = baseline_index(migrations, baseline)
    baseline_ids = [row[0] for row in rows if row[2] == "baseline"]
    if baseline_ids and baseline_ids != [
        migration.migration_id for migration in migrations[: baseline_position + 1]
    ]:
        raise MigrationStateError(
            "ledger-baseline-mismatch",
            "baseline rows must be the complete declared pre-ledger history",
        )
    if any(row[2] not in {"applied", "baseline"} for row in rows):
        raise MigrationStateError(
            "ledger-application-kind-mismatch",
            "ledger contains an unknown application kind",
        )


def record_migration(
    connection: psycopg.Connection[tuple[object, ...]],
    migration: MigrationScript,
    *,
    application_kind: Literal["applied", "baseline"],
    result_schema_sha256: str,
) -> None:
    connection.execute(
        """
        INSERT INTO ctower_schema_migrations (
            migration_id, sha256, application_kind, result_schema_sha256, applied_at,
            applied_server_version_num
        ) VALUES (
            %s, %s, %s, %s, clock_timestamp(),
            current_setting('server_version_num')::integer
        )
        """,
        (
            migration.migration_id,
            migration.sha256,
            application_kind,
            result_schema_sha256,
        ),
    )
