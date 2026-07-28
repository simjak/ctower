"""Persistent development-runtime acceptance at the ordinary finalizer boundary."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from support.durability_assertions import create_ticket
from support.postgres import (
    DatabaseFixture,
    DurabilityPair,
    create_durability_database,
    pause_durability_replay,
    start_durability_pair,
    stop_durability_pair,
    wait_for_durability_replay_current,
)
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture, create_first_tenant

from ctower_api.interface import create_app
from ctower_kernel.record import DurabilityHealthStatus
from ctower_kernel.record.postgres import PostgresDurabilityFinalizer, PostgresRecord

__all__: tuple[str, ...] = ()
_HTTP_ACCEPTED = 202
_HTTP_CREATED = 201


@dataclass(frozen=True, slots=True)
class _DevelopmentAuthority:
    pair: DurabilityPair
    database: DatabaseFixture
    standby_dsn: str
    tenant: TenantFixture


def test_ordinary_finalizer_reconciles_development_ack_without_cp3d_claim() -> None:
    """A committed pending command becomes accepted through the ordinary worker capability."""

    with _development_authority() as authority:
        record = PostgresRecord(
            authority.database.runtime_dsn,
            standby_dsn=authority.standby_dsn,
        )
        command_id = uuid4()
        with (
            TestClient(create_app(record), client=("127.0.0.1", 51000)) as client,
            pause_durability_replay(authority.pair),
        ):
            pending = create_ticket(
                client,
                authority.tenant,
                command_id,
                title="Ordinary development finalizer",
            )
        assert pending.status_code == _HTTP_ACCEPTED
        assert pending.json()["durability_state"] == "durability_pending"

        wait_for_durability_replay_current(authority.pair)
        batch = PostgresDurabilityFinalizer(
            authority.database.runtime_dsn,
            standby_dsn=authority.standby_dsn,
        ).finalize_pending()

        with TestClient(create_app(record), client=("127.0.0.1", 51000)) as client:
            replay = create_ticket(
                client,
                authority.tenant,
                command_id,
                title="Ordinary development finalizer",
            )
            ticket_id = pending.json()["ticket"]["ticket_id"]
            durable_ticket = client.get(
                f"/v1/tickets/{ticket_id}",
                headers={
                    **telemetry_headers(),
                    "Authorization": f"Bearer {authority.tenant.operator_credential}",
                },
            )
        health = record.durability_health(now=_database_now(authority.database.admin_dsn))

        assert batch.accepted >= 1
        assert replay.status_code == _HTTP_CREATED
        assert replay.json()["durability_state"] == "accepted"
        assert durable_ticket.json()["durability_state"] == "accepted"
        assert health.status is DurabilityHealthStatus.DEGRADED
        assert health.reason == "development_offhost_ack_cp3_d_not_proven"


@contextmanager
def _development_authority() -> Iterator[_DevelopmentAuthority]:
    pair = start_durability_pair()
    try:
        database, standby_dsn = create_durability_database(pair)
        tenant = create_first_tenant(database)
        with psycopg.connect(database.admin_dsn) as connection:
            connection.execute(
                """
                UPDATE durability_policy_state
                SET policy_ref = 'ctower.development-offhost-ack@1',
                    mode = 'development_offhost_ack',
                    standby_identity = 'ctower_i1_standby',
                    configured_at = clock_timestamp()
                WHERE singleton
                """
            )
        wait_for_durability_replay_current(pair)
        yield _DevelopmentAuthority(pair, database, standby_dsn, tenant)
    finally:
        stop_durability_pair(pair)


def _database_now(dsn: str) -> datetime:
    with psycopg.connect(dsn) as connection:
        row = connection.execute("SELECT clock_timestamp()").fetchone()
    if row is None:
        raise RuntimeError("database clock is unavailable")
    return cast(datetime, row[0])
