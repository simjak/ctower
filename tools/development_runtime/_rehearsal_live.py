"""The read-only live probe: standby-first, aggregates only, never a row leaves the box."""

from __future__ import annotations

import re
from pathlib import Path
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql

from tools.development_runtime._rehearsal_vocabulary import (
    LIVE_DSN_SENTINEL,
    LIVE_FORBIDDEN,
    LIVE_READ_PREFIXES,
    UpgradeRehearsalError,
)

__all__ = [
    "LiveProperties",
    "assert_read_only",
    "live_connection",
    "live_read",
    "probe_live",
    "resolve_live_dsn",
]

__all_dummy__ = None  # marker removed below

# ---------------------------------------------------------------------------
# live probe -- read-only, standby-first, no rows leave the box
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LiveProperties:
    """Everything the clone must reproduce, derived from the live instance without writing to it."""

    endpoint: str
    in_recovery: bool
    server_version: str
    ledger_rows: int
    terminal_migration: str
    ledger_attestation: str
    schema_fingerprint: str
    schema_records: dict[str, str]
    table_counts: dict[str, int]
    rejected_checks: tuple[str, ...]
    event_kinds: dict[str, int]
    link_subject_kinds: dict[str, int]
    blockers: tuple[tuple[str, str], ...]

    @property
    def non_empty_tables(self) -> tuple[str, ...]:
        return tuple(sorted(name for name, count in self.table_counts.items() if count))

    @property
    def attestation_drift(self) -> bool:
        return self.schema_fingerprint != self.ledger_attestation


def resolve_live_dsn() -> tuple[str, str]:
    """Resolve the live DSN, preferring the standby: a replica in recovery cannot be written at all.

    Only this function touches the keyring. The resolved string carries a secret, so it travels to
    the kernel subprocess through the environment (owner-readable) and never through argv
    (world-readable in /proc), and it is never printed.
    """

    from ctower_api.development_config import load_config
    from ctower_api.development_secrets import development_dsn

    config = load_config()
    for standby in (True, False):
        dsn = development_dsn(config, "postgres", standby=standby)
        separator = "&" if "?" in dsn else "?"
        guarded = f"{dsn}{separator}options=-c%20default_transaction_read_only%3Don"
        port = config.standby_port if standby else config.primary_port
        try:
            with psycopg.connect(guarded, connect_timeout=5) as connection:
                assert_read_only(connection)
        except psycopg.OperationalError:
            continue
        return guarded, f"{config.database_host}:{port}"
    raise UpgradeRehearsalError("live instance is unreachable on both the standby and the primary")


def assert_read_only(connection: psycopg.Connection[tuple[object, ...]]) -> bool:
    """Refuse to probe at all unless the server itself is refusing writes. Returns in_recovery."""

    row = connection.execute(
        "SELECT pg_is_in_recovery(), current_setting('default_transaction_read_only')"
    ).fetchone()
    if row is None:
        raise UpgradeRehearsalError("the live session refused to answer the read-only probe")
    recovery, read_only = row
    if read_only != "on":
        raise UpgradeRehearsalError("live session did not come up read-only; refusing to probe")
    return bool(recovery)


@contextmanager
def live_connection():
    """Open the live instance so that the server itself refuses any write."""

    guarded, endpoint = resolve_live_dsn()
    with psycopg.connect(guarded, connect_timeout=5) as connection:
        yield connection, endpoint, assert_read_only(connection)


def live_read(
    connection: psycopg.Connection[tuple[object, ...]],
    statement: str,
    parameters: tuple[Any, ...] = (),
) -> list[tuple[Any, ...]]:
    """The only door to live data: SELECT-shaped statements, aggregates out, never rows."""

    head = statement.strip().split(None, 1)[0].upper()
    if head not in LIVE_READ_PREFIXES:
        raise UpgradeRehearsalError(f"refused a non-read live statement: {head}")
    body = re.sub(r"'[^']*'", "''", statement)
    forbidden = LIVE_FORBIDDEN.search(body)
    if forbidden is not None:
        raise UpgradeRehearsalError(
            f"refused a live statement carrying {forbidden.group(1).upper()}"
        )
    return connection.execute(statement, parameters).fetchall()


def probe_live(target_source: Path) -> LiveProperties:
    """Derive the property list the rehearsal must reproduce."""

    from tools.development_runtime._rehearsal_bridge import kernel_call


    with live_connection() as (connection, endpoint, recovery):
        version = str(live_read(connection, "SELECT version()")[0][0]).split(" (")[0]
        ledger = live_read(
            connection,
            """
            SELECT count(*), max(migration_id),
                   (SELECT result_schema_sha256 FROM ctower_schema_migrations
                    ORDER BY migration_id DESC LIMIT 1)
            FROM ctower_schema_migrations
            """,
        )[0]
        tables = [
            str(row[0])
            for row in live_read(
                connection,
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename",
            )
        ]
        counts = {name: _live_count(connection, name) for name in tables}
        kinds = {
            str(key): int(value)
            for key, value in live_read(
                connection, "SELECT kind, count(*) FROM events GROUP BY kind"
            )
        }
        links = {
            str(key): int(value)
            for key, value in live_read(
                connection, "SELECT subject_kind, count(*) FROM event_links GROUP BY 1"
            )
        }
    # The sentinel keeps the DSN out of argv; the resolved secret travels in the environment.
    guarded, _endpoint = resolve_live_dsn()
    fingerprint = kernel_call(target_source, "fingerprint", live_dsn=guarded, dsn=LIVE_DSN_SENTINEL)
    vector = kernel_call(target_source, "semantics", live_dsn=guarded, dsn=LIVE_DSN_SENTINEL)
    rejected = tuple(name for name, verdict in vector["checks"].items() if verdict == "reject")
    attestation = str(ledger[2])
    digest = str(fingerprint["fingerprint"])
    blockers: list[tuple[str, str]] = []
    if digest != attestation:
        blockers.append(
            (
                "ledger-schema-mismatch",
                f"live schema {digest[:20]}… does not match the attestation {attestation[:20]}… "
                f"recorded for {ledger[1]}; `database-up` refuses before any DDL runs",
            )
        )
    return LiveProperties(
        endpoint=endpoint,
        in_recovery=recovery,
        server_version=version,
        ledger_rows=int(ledger[0]),
        terminal_migration=str(ledger[1]),
        ledger_attestation=attestation,
        schema_fingerprint=digest,
        schema_records=dict(fingerprint["records"]),
        table_counts=counts,
        rejected_checks=rejected,
        event_kinds=kinds,
        link_subject_kinds=links,
        blockers=tuple(blockers),
    )


def _live_count(connection: psycopg.Connection[tuple[object, ...]], table: str) -> int:
    statement = (
        sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table)).as_string(connection)
    )
    rows = live_read(connection, statement)
    if not rows or rows[0][0] is None:
        raise UpgradeRehearsalError(f"live count for {table} returned no answer")
    return int(rows[0][0])
