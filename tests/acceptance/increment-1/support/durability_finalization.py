"""Deterministic remote-apply ambiguity evidence for acceptance finalization."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row
from support.durability_assertions import (
    create_ticket,
    install_finalization_refusal,
    remove_finalization_refusal,
)
from support.postgres import DatabaseFixture, DurabilityPair, stop_durability_standby
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

from ctower_api.interface import create_app
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()

_ADVISORY_KEY = 7_221_643
_BOUND_SECONDS = 8.0
_HTTP_OK = 200
_HTTP_PENDING = 202


class AuthorityFixture(Protocol):
    @property
    def pair(self) -> DurabilityPair: ...

    @property
    def database(self) -> DatabaseFixture: ...

    @property
    def standby_dsn(self) -> str: ...

    @property
    def tenant(self) -> TenantFixture: ...


@dataclass(frozen=True, slots=True)
class AmbiguousFinalization:
    """One locally finalized command whose named copy never received finalization."""

    command_id: UUID
    response_content: bytes


def create_ambiguous_finalization(
    client: TestClient, authority: AuthorityFixture
) -> AmbiguousFinalization:
    """Lose the receiver after ACK replay but before finalization remote apply."""

    command_id = uuid4()
    _install_barrier(authority.database.admin_dsn)
    try:
        with (
            psycopg.connect(authority.database.admin_dsn, autocommit=True) as blocker,
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            blocker.execute("SELECT pg_advisory_lock(%s)", (_ADVISORY_KEY,))
            started = time.monotonic()
            future = executor.submit(
                lambda: create_ticket(
                    client,
                    authority.tenant,
                    command_id,
                    title="Ambiguous finalization",
                )
            )
            _wait_for_finalization_barrier(authority.database.admin_dsn, command_id)
            _assert_ack_is_replay_visible(authority, command_id)
            stop_durability_standby(authority.pair)
            blocker.execute("SELECT pg_advisory_unlock(%s)", (_ADVISORY_KEY,))
            response = future.result(timeout=_BOUND_SECONDS)
            elapsed = time.monotonic() - started
    finally:
        _remove_barrier(authority.database.admin_dsn)

    assert elapsed < _BOUND_SECONDS
    assert response.status_code == _HTTP_PENDING
    assert response.headers["Retry-After"] == "1"
    assert response.json()["durability_state"] == "durability_pending"
    _assert_primary_only_finalization(authority.database.admin_dsn, command_id)
    replay = create_ticket(
        client,
        authority.tenant,
        command_id,
        title="Ambiguous finalization",
    )
    assert replay.status_code == _HTTP_PENDING
    assert replay.content == response.content
    ticket = client.get(
        f"/v1/tickets/{response.json()['ticket']['ticket_id']}",
        headers={
            **telemetry_headers(),
            "Authorization": f"Bearer {authority.tenant.operator_credential}",
        },
    )
    assert ticket.status_code == _HTTP_OK
    assert ticket.json()["durability_state"] == "durability_pending"
    return AmbiguousFinalization(command_id, response.content)


def assert_receipt_mismatches_are_rejected(client: TestClient, authority: AuthorityFixture) -> None:
    """Reject a finalization that differs from its ACK in any immutable field."""

    command_id = uuid4()
    install_finalization_refusal(authority.database.admin_dsn)
    try:
        pending = create_ticket(
            client,
            authority.tenant,
            command_id,
            title="Receipt-bound finalization",
        )
    finally:
        remove_finalization_refusal(authority.database.admin_dsn)
    assert pending.status_code == _HTTP_PENDING
    with psycopg.connect(authority.database.admin_dsn, row_factory=dict_row) as connection:
        receipt = connection.execute(
            """
            SELECT tenant_id, principal_id, client_command_id, request_sha256,
                command_root, acceptance_position, policy_ref,
                standby_application_name, standby_identity,
                standby_system_identifier, standby_timeline_id,
                standby_replay_lsn::text AS standby_replay_lsn
            FROM durability_acknowledgements
            WHERE tenant_id = %s AND client_command_id = %s
            """,
            (authority.tenant.tenant_id, command_id),
        ).fetchone()
    assert receipt is not None
    values = list(receipt.values())
    request_digest = bytes(cast(bytes, values[3]))
    command_root = bytes(cast(bytes, values[4]))
    mismatches: tuple[tuple[int, object], ...] = (
        (0, uuid4()),
        (1, uuid4()),
        (2, uuid4()),
        (3, bytes([request_digest[0] ^ 1]) + request_digest[1:]),
        (4, bytes([command_root[0] ^ 1]) + command_root[1:]),
        (5, int(cast(int, values[5])) + 1),
        (6, "ctower.mismatched@1"),
        (7, "ctower_wrong_ack"),
        (8, "wrong_standby_identity"),
        (9, int(str(values[9])) + 1),
        (10, int(cast(int, values[10])) + 1),
        (11, "FFFFFFFF/FFFFFFFE"),
    )
    for index, mismatch in mismatches:
        candidate = [*values]
        candidate[index] = mismatch
        with (
            psycopg.connect(authority.database.admin_dsn) as connection,
            pytest.raises(psycopg.IntegrityError),
        ):
            connection.execute(
                """
                INSERT INTO durability_acceptance_finalizations (
                    tenant_id, principal_id, client_command_id, request_sha256,
                    command_root, acceptance_position, policy_ref,
                    standby_application_name, standby_identity,
                    standby_system_identifier, standby_timeline_id,
                    standby_replay_lsn, finalized_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    clock_timestamp())
                """,
                candidate,
            )
    with psycopg.connect(authority.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT count(*) FROM durability_acceptance_finalizations
            WHERE tenant_id = %s AND client_command_id = %s
            """,
            (authority.tenant.tenant_id, command_id),
        ).fetchone()
    assert row == (0,)


def assert_promoted_replay(authority: AuthorityFixture, ambiguity: AmbiguousFinalization) -> None:
    """Require the named copy to replay the same bounded pending response exactly."""

    promoted_runtime_dsn = authority.standby_dsn.replace(
        "postgresql://postgres@", "postgresql://ctower_runtime@", 1
    )
    app = create_app(PostgresRecord(promoted_runtime_dsn))
    with TestClient(app, client=("127.0.0.1", 51002)) as client:
        replay = create_ticket(
            client,
            authority.tenant,
            ambiguity.command_id,
            title="Ambiguous finalization",
        )
    assert replay.status_code == _HTTP_PENDING
    assert replay.content == ambiguity.response_content
    with psycopg.connect(authority.standby_dsn) as connection:
        facts = connection.execute(
            """
            SELECT
                EXISTS (
                    SELECT 1 FROM durability_acknowledgements
                    WHERE tenant_id = %s AND client_command_id = %s
                ),
                EXISTS (
                    SELECT 1 FROM durability_acceptance_finalizations
                    WHERE tenant_id = %s AND client_command_id = %s
                )
            """,
            (
                authority.tenant.tenant_id,
                ambiguity.command_id,
                authority.tenant.tenant_id,
                ambiguity.command_id,
            ),
        ).fetchone()
    assert facts == (True, False)


def _install_barrier(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        connection.execute(
            f"""
            CREATE FUNCTION test_block_durability_finalization() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                PERFORM pg_advisory_xact_lock({_ADVISORY_KEY});
                RETURN NEW;
            END
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER test_block_durability_finalization
            BEFORE INSERT ON durability_acceptance_finalizations
            FOR EACH ROW EXECUTE FUNCTION test_block_durability_finalization()
            """
        )


def _remove_barrier(dsn: str) -> None:
    with psycopg.connect(dsn) as connection:
        connection.execute("SET LOCAL synchronous_commit = local")
        connection.execute(
            """
            DROP TRIGGER IF EXISTS test_block_durability_finalization
            ON durability_acceptance_finalizations
            """
        )
        connection.execute("DROP FUNCTION IF EXISTS test_block_durability_finalization()")


def _wait_for_finalization_barrier(dsn: str, command_id: UUID) -> None:
    deadline = time.monotonic() + _BOUND_SECONDS
    while time.monotonic() < deadline:
        with psycopg.connect(dsn) as connection:
            blocked = connection.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND wait_event_type = 'Lock'
                      AND wait_event = 'advisory'
                      AND query LIKE '%INSERT INTO durability_acceptance_finalizations%'
                )
                """
            ).fetchone()
        if blocked == (True,):
            return
        time.sleep(0.02)
    raise RuntimeError(f"finalization barrier was not reached for {command_id}")


def _assert_ack_is_replay_visible(authority: AuthorityFixture, command_id: UUID) -> None:
    with psycopg.connect(authority.standby_dsn) as connection:
        row = connection.execute(
            """
            SELECT count(*) FROM durability_acknowledgements
            WHERE tenant_id = %s AND client_command_id = %s
            """,
            (authority.tenant.tenant_id, command_id),
        ).fetchone()
    assert row == (1,)


def _assert_primary_only_finalization(dsn: str, command_id: UUID) -> None:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM durability_acknowledgements
                 WHERE client_command_id = %s) AS acknowledgements,
                (SELECT count(*) FROM durability_acceptance_finalizations
                 WHERE client_command_id = %s) AS finalizations
            """,
            (command_id, command_id),
        ).fetchone()
    assert row == {"acknowledgements": 1, "finalizations": 1}
