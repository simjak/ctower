"""Real PostgreSQL 17 evidence for Record's off-host durability authority."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from httpx import Response
from psycopg.rows import dict_row
from support.postgres import (
    DatabaseFixture,
    DurabilityPair,
    create_durability_database,
    promote_durability_standby,
    start_durability_pair,
    start_durability_standby,
    stop_durability_pair,
    stop_durability_primary,
    stop_durability_standby,
)
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture, create_first_tenant

from ctower_api.interface import create_app
from ctower_api.telemetry import TelemetryRecorder
from ctower_kernel.record import DurabilityHealth, DurabilityHealthStatus
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.work import Work
from ctower_kernel.work.postgres import PostgresWork

__all__: tuple[str, ...] = ()

HTTP_ACCEPTED = 201
HTTP_PENDING = 202
HTTP_CONFLICT = 409
BOUND_SECONDS = 8.0
SHA256_BYTES = 32


@dataclass(frozen=True, slots=True)
class _AuthorityFixture:
    pair: DurabilityPair
    database: DatabaseFixture
    pending_only_health: DurabilityHealth
    standby_dsn: str
    tenant: TenantFixture


@pytest.fixture(scope="module")
def authority() -> Iterator[_AuthorityFixture]:
    """Provision one exact named physical standby and leave production defaults untouched."""

    pair = start_durability_pair()
    try:
        database, standby_dsn = create_durability_database(pair)
        tenant = create_first_tenant(database)
        pending_only_health = PostgresRecord(database.runtime_dsn).durability_health(
            now=_database_now(database.admin_dsn)
        )
        with psycopg.connect(database.admin_dsn) as connection:
            connection.execute(
                """
                UPDATE durability_policy_state
                SET policy_ref = 'ctower.cutover-rpo0@1', mode = 'cutover_rpo0',
                    standby_identity = 'ctower_i1_standby', configured_at = clock_timestamp()
                WHERE singleton
                """
            )
        yield _AuthorityFixture(pair, database, pending_only_health, standby_dsn, tenant)
    finally:
        stop_durability_pair(pair)


def test_named_standby_authority_is_replay_safe_and_fail_closed(
    authority: _AuthorityFixture,
) -> None:
    assert authority.pending_only_health.status is DurabilityHealthStatus.STATE_UNKNOWN
    assert authority.pending_only_health.reason == "pending_only"
    unconfigured = PostgresRecord(authority.database.runtime_dsn).durability_health(
        now=_database_now(authority.database.admin_dsn)
    )
    unavailable = PostgresRecord(
        authority.database.runtime_dsn,
        standby_dsn="postgresql://postgres@127.0.0.1:1/ctower?connect_timeout=1",
    ).durability_health(now=_database_now(authority.database.admin_dsn))
    assert unconfigured.status is DurabilityHealthStatus.STATE_UNKNOWN
    assert unconfigured.reason == "standby_unconfigured"
    assert unavailable.status is DurabilityHealthStatus.DEGRADED
    assert unavailable.reason == "target_mismatch"
    captures: list[dict[str, object]] = []
    recorder = TelemetryRecorder(captures.append)
    record = PostgresRecord(
        authority.database.runtime_dsn,
        standby_dsn=authority.standby_dsn,
        telemetry=recorder,
    )
    app = create_app(
        record,
        work=Work(
            record,
            writer=PostgresWork(authority.database.runtime_dsn),
            telemetry=recorder,
        ),
        telemetry=recorder,
    )

    with TestClient(app, client=("127.0.0.1", 51000)) as client:
        accepted = _accepted_replay_and_conflict(client, authority)
        _response_loss_replays_exactly(client, authority)
        _wrong_target_recovers_on_same_key(client, authority, record)
        _replay_before_receipt_recovers_on_same_key(client, authority)
        _assert_primary_evidence(authority, accepted)
        local_commands = _standby_loss_is_bounded_and_dependency_safe(client, authority)

    _assert_secret_free_telemetry(captures, authority.tenant)
    _assert_primary_loss_boundary(authority, accepted, local_commands)


def _accepted_replay_and_conflict(
    client: TestClient, authority: _AuthorityFixture
) -> tuple[UUID, UUID]:
    command_id = uuid4()
    first = _create_ticket(client, authority.tenant, command_id, title="Accepted authority")
    replay = _create_ticket(client, authority.tenant, command_id, title="Accepted authority")
    changed = _create_ticket(client, authority.tenant, command_id, title="Changed request")

    assert first.status_code == HTTP_ACCEPTED
    assert first.json()["durability_state"] == "accepted"
    assert replay.status_code == HTTP_ACCEPTED
    assert replay.content == first.content
    assert replay.json()["event_ids"] == first.json()["event_ids"]
    assert changed.status_code == HTTP_CONFLICT
    assert changed.json()["code"] == "idempotency-conflict"
    return command_id, UUID(cast(str, first.json()["ticket"]["ticket_id"]))


def _response_loss_replays_exactly(client: TestClient, authority: _AuthorityFixture) -> None:
    command_id = uuid4()
    _create_ticket(client, authority.tenant, command_id, title="Discarded first response")
    replay = _create_ticket(client, authority.tenant, command_id, title="Discarded first response")
    assert replay.status_code == HTTP_ACCEPTED
    assert replay.json()["durability_state"] == "accepted"
    _assert_one_result_and_ack(authority, command_id)


def _wrong_target_recovers_on_same_key(
    client: TestClient, authority: _AuthorityFixture, record: PostgresRecord
) -> None:
    _set_target(authority, "wrong_standby_identity")
    command_id = uuid4()
    pending = _create_ticket(client, authority.tenant, command_id, title="Wrong named target")
    health = record.durability_health(now=_database_now(authority.database.admin_dsn))
    assert pending.status_code == HTTP_PENDING
    assert pending.headers["Retry-After"] == "1"
    assert pending.json()["durability_state"] == "durability_pending"
    assert health.status is DurabilityHealthStatus.DEGRADED
    _assert_replay_without_receipt(authority, command_id)

    _set_target(authority, "ctower_i1_standby")
    accepted = _create_ticket(client, authority.tenant, command_id, title="Wrong named target")
    healthy = record.durability_health(now=_database_now(authority.database.admin_dsn))
    assert accepted.status_code == HTTP_ACCEPTED
    assert healthy.status is DurabilityHealthStatus.HEALTHY
    assert healthy.acceptance_position is not None
    assert _semantic_without_durability(accepted.json()) == _semantic_without_durability(
        pending.json()
    )
    assert accepted.json()["event_ids"] == pending.json()["event_ids"]


def _replay_before_receipt_recovers_on_same_key(
    client: TestClient, authority: _AuthorityFixture
) -> None:
    _install_ack_delay(authority.database.admin_dsn)
    command_id = uuid4()
    try:
        started = time.monotonic()
        pending = _create_ticket(client, authority.tenant, command_id, title="Delayed receipt")
        elapsed = time.monotonic() - started
    finally:
        _remove_ack_delay(authority.database.admin_dsn)

    assert pending.status_code == HTTP_PENDING
    assert pending.headers["Retry-After"] == "1"
    assert elapsed < BOUND_SECONDS
    _assert_replay_without_receipt(authority, command_id)

    accepted = _create_ticket(client, authority.tenant, command_id, title="Delayed receipt")
    assert accepted.status_code == HTTP_ACCEPTED
    assert _semantic_without_durability(accepted.json()) == _semantic_without_durability(
        pending.json()
    )
    assert accepted.json()["event_ids"] == pending.json()["event_ids"]


def _standby_loss_is_bounded_and_dependency_safe(
    client: TestClient, authority: _AuthorityFixture
) -> tuple[UUID, UUID, UUID]:
    stop_durability_standby(authority.pair)
    pending_command = uuid4()
    started = time.monotonic()
    pending = _create_ticket(
        client,
        authority.tenant,
        pending_command,
        title="Primary-local before replay",
    )
    elapsed = time.monotonic() - started
    pending_ticket = UUID(cast(str, pending.json()["ticket"]["ticket_id"]))
    assert pending.status_code == HTTP_PENDING
    assert pending.headers["Retry-After"] == "1"
    assert elapsed < BOUND_SECONDS
    _assert_primary_only_result(authority.database.admin_dsn, pending_command)

    refusal_command = uuid4()
    refused = _change_priority(
        client,
        authority.tenant,
        pending_ticket,
        refusal_command,
    )
    assert refused.status_code == HTTP_CONFLICT
    assert refused.json()["code"] == "durability_pending"
    _assert_exact_refusal(authority.database.admin_dsn, refusal_command)

    unrelated_command = uuid4()
    unrelated = _create_ticket(
        client,
        authority.tenant,
        unrelated_command,
        title="Unrelated local progress",
    )
    assert unrelated.status_code == HTTP_PENDING
    assert UUID(cast(str, unrelated.json()["ticket"]["ticket_id"])) != pending_ticket
    return pending_command, refusal_command, unrelated_command


def _assert_primary_evidence(authority: _AuthorityFixture, accepted: tuple[UUID, UUID]) -> None:
    command_id, _ = accepted
    with psycopg.connect(authority.standby_dsn, row_factory=dict_row) as connection:
        receipt = connection.execute(
            """
            SELECT acceptance_position, command_root, request_sha256,
                standby_application_name, standby_identity, standby_in_recovery
            FROM durability_acknowledgements AS acknowledgement
            JOIN LATERAL (
                SELECT standby_in_recovery
                FROM durability_target_observations AS observation
                WHERE observation.tenant_id = acknowledgement.tenant_id
                  AND observation.principal_id = acknowledgement.principal_id
                  AND observation.client_command_id = acknowledgement.client_command_id
                  AND observation.receipt_visible
                ORDER BY observation.observed_at DESC LIMIT 1
            ) AS observation ON true
            WHERE acknowledgement.tenant_id = %s
              AND acknowledgement.client_command_id = %s
            """,
            (authority.tenant.tenant_id, command_id),
        ).fetchone()
        positions = connection.execute(
            """
            SELECT acceptance_position FROM durability_acknowledgements
            ORDER BY acceptance_position
            """
        ).fetchall()
    assert receipt is not None
    assert int(cast(int, receipt["acceptance_position"])) > 0
    assert len(bytes(cast(bytes, receipt["command_root"]))) == SHA256_BYTES
    assert len(bytes(cast(bytes, receipt["request_sha256"]))) == SHA256_BYTES
    assert receipt["standby_application_name"] == "ctower_i1_ack"
    assert receipt["standby_identity"] == "ctower_i1_standby"
    assert receipt["standby_in_recovery"] is True
    ordered = [int(cast(int, row["acceptance_position"])) for row in positions]
    assert ordered == sorted(set(ordered))


def _assert_primary_loss_boundary(
    authority: _AuthorityFixture,
    accepted: tuple[UUID, UUID],
    local_commands: tuple[UUID, UUID, UUID],
) -> None:
    accepted_command, accepted_ticket = accepted
    stop_durability_primary(authority.pair)
    start_durability_standby(authority.pair)
    promote_durability_standby(authority.pair)

    with psycopg.connect(authority.standby_dsn) as connection:
        accepted_row = connection.execute(
            """
            SELECT
                EXISTS (SELECT 1 FROM tickets WHERE ticket_id = %s),
                EXISTS (
                    SELECT 1 FROM durability_acknowledgements
                    WHERE tenant_id = %s AND client_command_id = %s
                )
            """,
            (accepted_ticket, authority.tenant.tenant_id, accepted_command),
        ).fetchone()
        absent = connection.execute(
            """
            SELECT count(*) FROM command_results
            WHERE tenant_id = %s AND client_command_id = ANY(%s)
            """,
            (authority.tenant.tenant_id, list(local_commands)),
        ).fetchone()
    assert accepted_row == (True, True)
    assert absent == (0,)


def _assert_replay_without_receipt(authority: _AuthorityFixture, command_id: UUID) -> None:
    with psycopg.connect(authority.standby_dsn) as connection:
        facts = connection.execute(
            """
            SELECT
                EXISTS (
                    SELECT 1 FROM command_results
                    WHERE tenant_id = %s AND client_command_id = %s
                ),
                EXISTS (
                    SELECT 1 FROM durability_acknowledgements
                    WHERE tenant_id = %s AND client_command_id = %s
                )
            """,
            (
                authority.tenant.tenant_id,
                command_id,
                authority.tenant.tenant_id,
                command_id,
            ),
        ).fetchone()
    assert facts == (True, False)


def _assert_primary_only_result(dsn: str, command_id: UUID) -> None:
    with psycopg.connect(dsn) as connection:
        row = connection.execute(
            """
            SELECT count(*) FROM command_results
            WHERE client_command_id = %s
            """,
            (command_id,),
        ).fetchone()
    assert row == (1,)


def _assert_one_result_and_ack(authority: _AuthorityFixture, command_id: UUID) -> None:
    with psycopg.connect(authority.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM command_results WHERE client_command_id = %s),
                (SELECT count(*) FROM durability_acknowledgements WHERE client_command_id = %s)
            """,
            (command_id, command_id),
        ).fetchone()
    assert row == (1, 1)


def _assert_exact_refusal(dsn: str, command_id: UUID) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT status_code, response_body, event_ids
            FROM command_results WHERE client_command_id = %s
            """,
            (command_id,),
        ).fetchone()
    assert row is not None
    assert row["status_code"] == HTTP_CONFLICT
    assert cast(dict[str, object], row["response_body"])["code"] == "durability_pending"
    assert row["event_ids"] == []


def _assert_secret_free_telemetry(captures: list[dict[str, object]], tenant: TenantFixture) -> None:
    encoded = json.dumps(captures, separators=(",", ":"), sort_keys=True)
    assert tenant.operator_credential not in encoded
    assert tenant.commander_credential not in encoded
    assert "postgresql://" not in encoded
    assert {str(item["reason"]) for item in captures} <= {
        "authorized",
        "committed",
        "durability_pending",
        "idempotency-conflict",
    }


def _semantic_without_durability(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _semantic_without_durability(item)
            for key, item in value.items()
            if key != "durability_state"
        }
    if isinstance(value, list):
        return [_semantic_without_durability(item) for item in value]
    return value


def _set_target(authority: _AuthorityFixture, identity: str) -> None:
    with psycopg.connect(authority.database.admin_dsn) as connection:
        connection.execute(
            """
            UPDATE durability_policy_state
            SET standby_identity = %s, configured_at = clock_timestamp()
            WHERE singleton
            """,
            (identity,),
        )


def _install_ack_delay(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        connection.execute(
            """
            CREATE FUNCTION test_delay_durability_ack() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                PERFORM pg_sleep(3);
                RETURN NEW;
            END
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER test_delay_durability_ack
            BEFORE INSERT ON durability_acknowledgements
            FOR EACH ROW EXECUTE FUNCTION test_delay_durability_ack()
            """
        )


def _remove_ack_delay(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "DROP TRIGGER IF EXISTS test_delay_durability_ack ON durability_acknowledgements"
        )
        connection.execute("DROP FUNCTION IF EXISTS test_delay_durability_ack()")


def _database_now(dsn: str) -> datetime:
    with psycopg.connect(dsn) as connection:
        row = connection.execute("SELECT clock_timestamp()").fetchone()
    if row is None:
        raise RuntimeError("database clock was unavailable")
    return cast(datetime, row[0])


def _create_ticket(
    client: TestClient,
    tenant: TenantFixture,
    command_id: UUID,
    *,
    title: str,
) -> Response:
    return cast(
        Response,
        client.post(
            "/v1/tickets",
            json={
                "initial_custodian_id": str(tenant.commander_id),
                "priority": "P1",
                "source": {"kind": "test", "ref": f"test:durability:{command_id}"},
                "title": title,
            },
            headers={
                **telemetry_headers(command_id),
                "Authorization": f"Bearer {tenant.operator_credential}",
                "Idempotency-Key": str(command_id),
            },
        ),
    )


def _change_priority(
    client: TestClient,
    tenant: TenantFixture,
    ticket_id: UUID,
    command_id: UUID,
) -> Response:
    return cast(
        Response,
        client.post(
            f"/v1/tickets/{ticket_id}/priority",
            json={
                "expected_version": 1,
                "priority": "P2",
                "reason": "Dependent mutation must wait for acknowledged subject state",
            },
            headers={
                **telemetry_headers(command_id, ticket_id=ticket_id),
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
            },
        ),
    )
