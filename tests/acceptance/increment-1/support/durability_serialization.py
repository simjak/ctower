"""Deterministic two-connection subject-head serialization evidence."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from typing import cast
from uuid import UUID, uuid4

import psycopg
from fastapi.testclient import TestClient
from httpx import Response
from support.postgres import DatabaseFixture
from support.telemetry import telemetry_headers
from support.tenant_fixture import TenantFixture

__all__: tuple[str, ...] = ()

HTTP_PENDING = 202
HTTP_CONFLICT = 409
SERIALIZATION_LOCK_KEY = 712_040_120
BOUND_SECONDS = 8.0


def assert_subject_serialization(
    client: TestClient,
    concurrent_client: TestClient,
    tenant: TenantFixture,
    database: DatabaseFixture,
    ticket_id: UUID,
) -> tuple[UUID, UUID]:
    """Make B reach the head boundary before A commits, then require one refusal."""

    first_command, second_command = uuid4(), uuid4()
    started = time.monotonic()
    with (
        _serialization_deadline(database.admin_dsn),
        _event_barrier(database.admin_dsn, first_command) as release_barrier,
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        first_future = executor.submit(
            _change_priority,
            client,
            tenant,
            ticket_id,
            first_command,
            expected_version=1,
            priority="P2",
        )
        _wait_for_lock(database.admin_dsn, "advisory", first_future)
        second_future = executor.submit(
            _change_priority,
            concurrent_client,
            tenant,
            ticket_id,
            second_command,
            expected_version=2,
            priority="P1",
        )
        _wait_for_subject_head_lock(database.admin_dsn, second_future)
        release_barrier()
        first = first_future.result(timeout=BOUND_SECONDS)
        second = second_future.result(timeout=BOUND_SECONDS)

    assert time.monotonic() - started < BOUND_SECONDS
    assert first.status_code == HTTP_PENDING
    assert second.status_code == HTTP_CONFLICT
    assert second.json()["code"] == "durability_pending"
    _assert_serialized_result(
        database.admin_dsn,
        tenant,
        ticket_id,
        first_command,
        second_command,
    )
    return first_command, second_command


@contextmanager
def _serialization_deadline(dsn: str) -> Iterator[None]:
    # Leave enough time for B to prove it is waiting on A's subject-head row,
    # while keeping A's fail-closed response inside the regression's hard bound.
    _set_commit_deadline(dsn, 2_500)
    try:
        yield
    finally:
        _set_commit_deadline(dsn, 1_500)


def _set_commit_deadline(dsn: str, milliseconds: int) -> None:
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("SET synchronous_commit = local")
        connection.execute(
            """
            UPDATE durability_policy_state
            SET commit_deadline_ms = %s, configured_at = clock_timestamp()
            WHERE singleton
            """,
            (milliseconds,),
        )


@contextmanager
def _event_barrier(dsn: str, command_id: UUID) -> Iterator[Callable[[], None]]:
    _install_barrier(dsn, command_id)
    control = psycopg.connect(dsn, autocommit=True)
    control.execute("SELECT pg_advisory_lock(%s)", (SERIALIZATION_LOCK_KEY,))

    def release() -> None:
        row = control.execute("SELECT pg_advisory_unlock(%s)", (SERIALIZATION_LOCK_KEY,)).fetchone()
        assert row == (True,)

    try:
        yield release
    finally:
        control.execute("SELECT pg_advisory_unlock(%s)", (SERIALIZATION_LOCK_KEY,))
        control.close()
        _remove_barrier(dsn)


def _install_barrier(dsn: str, command_id: UUID) -> None:
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("SET synchronous_commit = local")
        connection.execute(
            """
            CREATE TABLE test_durability_event_barrier (
                client_command_id uuid PRIMARY KEY,
                lock_key bigint NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO test_durability_event_barrier VALUES (%s, %s)",
            (command_id, SERIALIZATION_LOCK_KEY),
        )
        connection.execute("GRANT SELECT ON test_durability_event_barrier TO ctower_svc")
        connection.execute(
            """
            CREATE FUNCTION test_wait_at_durability_event() RETURNS trigger
            LANGUAGE plpgsql AS $$
            DECLARE barrier_key bigint;
            BEGIN
                SELECT lock_key INTO barrier_key
                FROM test_durability_event_barrier
                WHERE client_command_id = NEW.client_command_id;
                IF FOUND THEN
                    PERFORM pg_advisory_xact_lock(barrier_key);
                END IF;
                RETURN NEW;
            END
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER test_wait_at_durability_event
            BEFORE INSERT ON events
            FOR EACH ROW EXECUTE FUNCTION test_wait_at_durability_event()
            """
        )


def _remove_barrier(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("SET synchronous_commit = local")
        connection.execute("DROP TRIGGER IF EXISTS test_wait_at_durability_event ON events")
        connection.execute("DROP FUNCTION IF EXISTS test_wait_at_durability_event()")
        connection.execute("DROP TABLE IF EXISTS test_durability_event_barrier")


def _wait_for_lock(dsn: str, wait_event: str, future: Future[Response]) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with psycopg.connect(dsn) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM pg_stat_activity
                WHERE wait_event = %s AND query LIKE '%%INSERT INTO events%%'
                LIMIT 1
                """,
                (wait_event,),
            ).fetchone()
        if row is not None:
            return
        if future.done():
            response = future.result()
            raise AssertionError(
                f"first command completed before barrier: {response.status_code} {response.text}"
            )
        time.sleep(0.02)
    raise RuntimeError("first command did not reach the event barrier")


def _wait_for_subject_head_lock(dsn: str, future: Future[Response]) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with psycopg.connect(dsn) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM pg_stat_activity
                WHERE wait_event_type = 'Lock'
                  AND query LIKE '%durability_subject_heads%'
                LIMIT 1
                """
            ).fetchone()
        if row is not None:
            return
        if future.done():
            response = future.result()
            raise AssertionError(
                "second command completed before A committed: "
                f"{response.status_code} {response.text}"
            )
        time.sleep(0.02)
    with psycopg.connect(dsn) as connection:
        waiting = connection.execute(
            """
            SELECT wait_event_type, wait_event, query FROM pg_stat_activity
            WHERE wait_event_type = 'Lock'
            """
        ).fetchall()
    raise RuntimeError(f"second command wait was not a subject-head query: {waiting!r}")


def _assert_serialized_result(
    dsn: str,
    tenant: TenantFixture,
    ticket_id: UUID,
    first_command: UUID,
    second_command: UUID,
) -> None:
    with psycopg.connect(dsn) as connection:
        ticket = connection.execute(
            "SELECT version, priority FROM tickets WHERE ticket_id = %s", (ticket_id,)
        ).fetchone()
        facts = connection.execute(
            """
            SELECT client_command_id, status_code, cardinality(event_ids)
            FROM command_results
            WHERE tenant_id = %s AND principal_id = %s
              AND client_command_id = ANY(%s)
            ORDER BY client_command_id
            """,
            (
                tenant.tenant_id,
                tenant.commander_id,
                [first_command, second_command],
            ),
        ).fetchall()
        events = connection.execute(
            "SELECT client_command_id FROM events WHERE client_command_id = ANY(%s)",
            ([first_command, second_command],),
        ).fetchall()
        head = connection.execute(
            """
            SELECT principal_id, client_command_id FROM durability_subject_heads
            WHERE tenant_id = %s AND subject_kind = 'ticket' AND subject_id = %s
            """,
            (tenant.tenant_id, ticket_id),
        ).fetchone()
    assert ticket == (2, "P2")
    assert sorted((row[1], row[2]) for row in facts) == [(200, 1), (HTTP_CONFLICT, 0)]
    assert events == [(first_command,)]
    assert head == (tenant.commander_id, first_command)


def _change_priority(
    client: TestClient,
    tenant: TenantFixture,
    ticket_id: UUID,
    command_id: UUID,
    *,
    expected_version: int,
    priority: str,
) -> Response:
    return cast(
        Response,
        client.post(
            f"/v1/tickets/{ticket_id}/priority",
            json={
                "expected_version": expected_version,
                "priority": priority,
                "reason": "Deterministic subject-head serialization regression",
            },
            headers={
                **telemetry_headers(command_id, ticket_id=ticket_id),
                "Authorization": f"Bearer {tenant.commander_credential}",
                "Idempotency-Key": str(command_id),
            },
        ),
    )
