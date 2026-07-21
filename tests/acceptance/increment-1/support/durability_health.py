"""Live durability-health fault scenarios for the PostgreSQL 17 pair."""

from __future__ import annotations

import time
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
        assert disconnected.reason in {"sender_not_live", "target_not_live"}
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
