"""Live durability-health fault scenarios for the PostgreSQL 17 pair."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import cast

import psycopg
from support.postgres import (
    DatabaseFixture,
    DurabilityPair,
    delay_durability_replay,
    disconnect_durability_receiver,
    pause_durability_replay,
)

from ctower_kernel.record import DurabilityHealth, DurabilityHealthStatus
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()

_STANDBY_EVIDENCE_FUNCTION = """
CREATE FUNCTION durability_standby_live_evidence()
RETURNS TABLE (
    matching_receiver_count bigint,
    receiver_status text,
    cluster_name text,
    in_recovery boolean,
    replay_paused boolean,
    replay_lsn {replay_type},
    system_identifier numeric,
    timeline_id integer
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
    SELECT
        count(*) AS matching_receiver_count,
        min(receiver.status) AS receiver_status,
        current_setting('cluster_name') AS cluster_name,
        pg_is_in_recovery() AS in_recovery,
        pg_is_wal_replay_paused() AS replay_paused,
        {replay_lsn} AS replay_lsn,
        (pg_control_system()).system_identifier,
        (pg_control_checkpoint()).timeline_id
    FROM pg_stat_wal_receiver AS receiver
$$;
"""


@contextmanager
def unreadable_standby_replay_evidence(
    primary_admin_dsn: str, *, malformed: bool
) -> Iterator[None]:
    """Expose NULL or malformed replay evidence through the real standby probe."""

    expression = "'not-an-lsn'::text" if malformed else "NULL::pg_lsn"
    replay_type = "text" if malformed else "pg_lsn"
    _replace_standby_probe(primary_admin_dsn, expression, replay_type)
    try:
        yield
    finally:
        _replace_standby_probe(primary_admin_dsn, "pg_last_wal_replay_lsn()", "pg_lsn")


def _replace_standby_probe(primary_admin_dsn: str, replay_lsn: str, replay_type: str) -> None:
    with psycopg.connect(primary_admin_dsn) as connection:
        connection.execute("SET LOCAL synchronous_commit = remote_apply")
        connection.execute("DROP FUNCTION durability_standby_live_evidence()")
        connection.execute(
            _STANDBY_EVIDENCE_FUNCTION.format(replay_lsn=replay_lsn, replay_type=replay_type)
        )
        connection.execute(
            "ALTER FUNCTION durability_standby_live_evidence() OWNER TO ctower_durability_probe"
        )
        connection.execute("REVOKE ALL ON FUNCTION durability_standby_live_evidence() FROM PUBLIC")
        connection.execute(
            "GRANT EXECUTE ON FUNCTION durability_standby_live_evidence() TO ctower_svc"
        )


def assert_live_health_faults(
    record: PostgresRecord,
    pair: DurabilityPair,
    database: DatabaseFixture,
) -> None:
    """Prove paused, disconnected, and behind replay evidence never reports green."""

    baseline = _health(record, database)
    assert baseline.status is DurabilityHealthStatus.HEALTHY, baseline

    with pause_durability_replay(pair):
        paused = _health(record, database)
        assert paused.status is DurabilityHealthStatus.DEGRADED
        assert paused.reason == "replay_paused"
    assert _health(record, database).status is DurabilityHealthStatus.HEALTHY

    with disconnect_durability_receiver(pair):
        disconnected = _health(record, database)
        assert disconnected.status is DurabilityHealthStatus.DEGRADED
        assert disconnected.reason in {
            "replay_evidence_unreadable",
            "sender_not_live",
            "target_not_live",
        }
    assert _health(record, database).status is DurabilityHealthStatus.HEALTHY

    with delay_durability_replay(pair):
        with psycopg.connect(database.admin_dsn) as connection:
            connection.execute("SET LOCAL synchronous_commit = local")
            connection.execute(
                """
                UPDATE durability_policy_state
                SET configured_at = clock_timestamp() WHERE singleton
                """
            )
        _wait_for_replay_lag(pair)
        catching_up = _health(record, database)
        assert catching_up.status is DurabilityHealthStatus.DEGRADED
        assert catching_up.reason == "replay_not_current"
    assert _health(record, database).status is DurabilityHealthStatus.HEALTHY


def _health(record: PostgresRecord, database: DatabaseFixture) -> DurabilityHealth:
    return record.durability_health(now=_database_now(database.admin_dsn))


def _database_now(dsn: str) -> datetime:
    with psycopg.connect(dsn) as connection:
        row = connection.execute("SELECT clock_timestamp()").fetchone()
    if row is None:
        raise RuntimeError("database clock was unavailable")
    return cast(datetime, row[0])


def _wait_for_replay_lag(pair: DurabilityPair) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with psycopg.connect(pair.primary_admin_dsn) as primary:
            primary_lsn = primary.execute("SELECT pg_current_wal_flush_lsn()::text").fetchone()
        with psycopg.connect(pair.standby_admin_dsn) as standby:
            standby_lsn = standby.execute("SELECT pg_last_wal_replay_lsn()::text").fetchone()
        if (
            primary_lsn is not None
            and standby_lsn is not None
            and _lsn_position(str(standby_lsn[0])) < _lsn_position(str(primary_lsn[0]))
        ):
            return
        time.sleep(0.05)
    raise RuntimeError("delayed standby did not expose a catching-up replay watermark")


def _lsn_position(value: str) -> int:
    high, low = value.split("/", maxsplit=1)
    return (int(high, 16) << 32) | int(low, 16)
