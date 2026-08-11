"""Real-Postgres proofs for authority recheck-to-persistence atomicity."""

from __future__ import annotations

import hashlib
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import uuid4

import psycopg
import pytest
from console_test_support import (
    Adapter,
    browser_actor,
    console_setup,
    execute_service_fact,
    observation,
    policy,
    recorded_session_ref,
)
from psycopg import sql
from support.tenant_fixture import TenantFixture

from ctower_kernel.console import (
    AesGcmConsoleCipher,
    ConsoleEventStream,
    ConsoleGlobalSwitchCommand,
    ConsoleSessionAllowance,
    ConsoleSessionAllowCommand,
    ConsoleViewer,
    ConsoleViewGrant,
    PostgresConsoleAuthority,
    PostgresConsoleOutputStore,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.human_identity import HumanRoleBindingRevocation
from ctower_kernel.record.postgres import PostgresRecord
from ctower_kernel.telemetry import NoopTelemetry, TelemetryContext
from ctower_kernel.work import AssignmentKind, ChangeAssignment, Work, WorkReceipt
from ctower_kernel.work.postgres import PostgresWork

__all__: tuple[str, ...] = ()
_WAIT_SECONDS = 5
_BARRIERS = {
    "grant": (437_021, "console_view_grants"),
    "open": (437_022, "console_stream_opens"),
    "output": (437_023, "console_output_objects"),
    "access": (437_024, "console_output_access_facts"),
    "assignment": (437_025, "assignment_intervals"),
}
type _BarrierKind = Literal["grant", "open", "output", "access", "assignment"]


def test_grant_insert_serializes_a_concurrent_global_disable(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, operator, browser, allowance = console_setup(tenant, now)
    key, blocker = _install_insert_barrier(tenant, "grant")
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            grant_future = executor.submit(viewer.mint_grant, browser, allowance.allowance_id)
            _wait_for_insert_barrier(tenant, key)
            mutation_future = executor.submit(
                viewer.set_global_switch,
                operator,
                ConsoleGlobalSwitchCommand(enabled=True, reason="grant persist barrier"),
            )
            mutation_blocked = _future_remained_blocked(mutation_future)
            blocker.execute("SELECT pg_advisory_unlock(%s)", (key,))
            granted = grant_future.result(timeout=_WAIT_SECONDS)
            assert mutation_future.result(timeout=_WAIT_SECONDS) is None
    finally:
        blocker.close()

    assert mutation_blocked
    assert isinstance(granted, ConsoleViewGrant)
    refused = viewer.mint_grant(browser, allowance.allowance_id, renewal=True)
    assert isinstance(refused, RecordProblem)
    assert refused.code == "console-globally-disabled"


def test_stream_open_insert_serializes_a_concurrent_human_revocation(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, _operator, browser, allowance = console_setup(tenant, now)
    assert browser.human_session_id is not None
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    key, blocker = _install_insert_barrier(tenant, "open")
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            open_future = executor.submit(
                viewer.open_stream, browser, allowance.allowance_id, last_event_id=None
            )
            _wait_for_insert_barrier(tenant, key)
            mutation_future = executor.submit(
                execute_service_fact,
                tenant,
                """
                INSERT INTO human_session_revocations (
                    session_id, tenant_id, reason, revoked_at
                ) VALUES (%s, %s, 'open persist barrier', %s)
                """,
                (browser.human_session_id, tenant.tenant_id, now),
            )
            mutation_blocked = _future_remained_blocked(mutation_future)
            blocker.execute("SELECT pg_advisory_unlock(%s)", (key,))
            opened = open_future.result(timeout=_WAIT_SECONDS)
            mutation_future.result(timeout=_WAIT_SECONDS)
    finally:
        blocker.close()

    assert mutation_blocked
    assert isinstance(opened, ConsoleEventStream)
    assert b'"code":"reauthentication_required"' in next(opened.events)


def test_grant_insert_serializes_canonical_human_role_revocation(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, operator, browser, allowance = console_setup(tenant, now)
    assert browser.human_binding_id is not None
    record = PostgresRecord(tenant.database.runtime_dsn, telemetry=NoopTelemetry())
    command = HumanRoleBindingRevocation(
        client_command_id=uuid4(),
        binding_id=browser.human_binding_id,
        reason="canonical Console authority race",
    )
    key, blocker = _install_insert_barrier(tenant, "grant")
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            grant_future = executor.submit(viewer.mint_grant, browser, allowance.allowance_id)
            _wait_for_insert_barrier(tenant, key)
            revoke_future = executor.submit(
                record.human_identity.revoke_role,
                operator,
                command,
                request_digest=hashlib.sha256(b"canonical-console-revoke").digest(),
                now=now,
                telemetry=_telemetry(),
            )
            revoke_blocked = _future_remained_blocked(revoke_future)
            blocker.execute("SELECT pg_advisory_unlock(%s)", (key,))
            granted = grant_future.result(timeout=_WAIT_SECONDS)
            revoked = revoke_future.result(timeout=_WAIT_SECONDS)
    finally:
        blocker.close()

    assert revoke_blocked
    assert isinstance(granted, ConsoleViewGrant)
    assert not isinstance(revoked, RecordProblem)
    assert revoked.state == "revoked"
    refused = viewer.mint_grant(browser, allowance.allowance_id, renewal=True)
    assert isinstance(refused, RecordProblem)
    assert refused.code == "console-reauthentication-required"


def test_output_insert_serializes_a_concurrent_global_disable(
    tenant: TenantFixture,
) -> None:
    viewer, operator, opened = _opened_stream(tenant)
    key, blocker = _install_insert_barrier(tenant, "output")
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            output_future = executor.submit(next, opened.events)
            _wait_for_insert_barrier(tenant, key)
            mutation_future = executor.submit(
                viewer.set_global_switch,
                operator,
                ConsoleGlobalSwitchCommand(enabled=True, reason="output persist barrier"),
            )
            mutation_blocked = _future_remained_blocked(mutation_future)
            blocker.execute("SELECT pg_advisory_unlock(%s)", (key,))
            closed = output_future.result(timeout=_WAIT_SECONDS)
            assert mutation_future.result(timeout=_WAIT_SECONDS) is None
    finally:
        blocker.close()

    assert mutation_blocked
    assert b'"code":"globally_disabled"' in closed
    with pytest.raises(StopIteration):
        next(opened.events)
    assert _fact_counts(tenant)[2:] == (1, 0)


def test_access_insert_serializes_a_concurrent_global_disable(
    tenant: TenantFixture,
) -> None:
    viewer, operator, opened = _opened_stream(tenant)
    key, blocker = _install_insert_barrier(tenant, "access")
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            access_future = executor.submit(next, opened.events)
            _wait_for_insert_barrier(tenant, key)
            mutation_future = executor.submit(
                viewer.set_global_switch,
                operator,
                ConsoleGlobalSwitchCommand(enabled=True, reason="access persist barrier"),
            )
            mutation_blocked = _future_remained_blocked(mutation_future)
            blocker.execute("SELECT pg_advisory_unlock(%s)", (key,))
            first_event = access_future.result(timeout=_WAIT_SECONDS)
            assert mutation_future.result(timeout=_WAIT_SECONDS) is None
    finally:
        blocker.close()

    assert mutation_blocked
    if b"event: chunk" in first_event:
        assert b'"code":"globally_disabled"' in next(opened.events)
    else:
        assert b'"code":"globally_disabled"' in first_event
    assert _fact_counts(tenant)[2:] == (1, 1)


def test_canonical_assignment_change_cannot_deadlock_a_grant_decision(
    tenant: TenantFixture,
) -> None:
    work, operator, viewer, browser, allowance, command = _assignment_race_setup(tenant)
    key, blocker = _install_insert_barrier(tenant, "assignment")
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            work_future = executor.submit(work.execute, operator, command, telemetry=_telemetry())
            _wait_for_insert_barrier(tenant, key)
            grant_future = executor.submit(viewer.mint_grant, browser, allowance.allowance_id)
            grant_blocked = _future_remained_blocked(grant_future)
            blocker.execute("SELECT pg_advisory_unlock(%s)", (key,))
            changed = work_future.result(timeout=_WAIT_SECONDS)
            refused = grant_future.result(timeout=_WAIT_SECONDS)
    finally:
        blocker.close()

    assert grant_blocked
    assert isinstance(changed, WorkReceipt)
    assert isinstance(refused, RecordProblem)
    assert refused.code == "console-assignment-stale"


def _opened_stream(
    tenant: TenantFixture,
) -> tuple[ConsoleViewer, Actor, ConsoleEventStream]:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, operator, browser, allowance = console_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    opened = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(opened, ConsoleEventStream)
    return viewer, operator, opened


def _assignment_race_setup(
    tenant: TenantFixture,
) -> tuple[Work, Actor, ConsoleViewer, Actor, ConsoleSessionAllowance, ChangeAssignment]:
    now = datetime.now(UTC)
    ref = recorded_session_ref(tenant)
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    work = Work(
        PostgresRecord(tenant.database.runtime_dsn),
        writer=PostgresWork(tenant.database.runtime_dsn),
    )
    version = _ticket_version(tenant, ref.assignment_ticket_id)
    seeded = work.execute(
        operator,
        ChangeAssignment(
            uuid4(),
            ref.assignment_ticket_id,
            version,
            "bind canonical Console authority race",
            AssignmentKind.CURRENT_ASSIGNEE,
            ref.seat_principal_id,
        ),
        telemetry=_telemetry(),
    )
    assert isinstance(seeded, WorkReceipt)
    version, sequence = _current_assignment(tenant, ref.assignment_ticket_id)
    ref = replace(
        ref,
        assignment_kind=AssignmentKind.CURRENT_ASSIGNEE.value,
        assignment_interval_sequence=sequence,
    )
    viewer = _viewer(tenant, Adapter(observation(ref), b"authority-race-output"), now)
    browser = browser_actor(tenant, now=now)
    allowance = viewer.allow_session(
        operator, ConsoleSessionAllowCommand(ref, "restricted", "standard")
    )
    assert isinstance(allowance, ConsoleSessionAllowance)
    command = ChangeAssignment(
        uuid4(),
        ref.assignment_ticket_id,
        version,
        "canonical Console authority race",
        AssignmentKind.CURRENT_ASSIGNEE,
        tenant.operator_id,
    )
    return work, operator, viewer, browser, allowance, command


def _ticket_version(tenant: TenantFixture, ticket_id: object) -> int:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT version FROM tickets WHERE ticket_id = %s AND tenant_id = %s",
            (ticket_id, tenant.tenant_id),
        ).fetchone()
    assert row is not None
    return int(row[0])


def _current_assignment(tenant: TenantFixture, ticket_id: object) -> tuple[int, int]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT ticket.version, assignment.interval_sequence
            FROM tickets AS ticket
            JOIN assignment_intervals AS assignment
              ON assignment.ticket_id = ticket.ticket_id
             AND assignment.tenant_id = ticket.tenant_id
            WHERE ticket.ticket_id = %s AND ticket.tenant_id = %s
              AND assignment.assignment_kind = 'current_assignee'
              AND assignment.released_at IS NULL
            """,
            (ticket_id, tenant.tenant_id),
        ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1])


def _install_insert_barrier(
    tenant: TenantFixture, kind: _BarrierKind
) -> tuple[int, psycopg.Connection[tuple[object, ...]]]:
    key, table = _BARRIERS[kind]
    function = f"console_test_block_{kind}_insert"
    statement = sql.SQL(
        """
        CREATE FUNCTION {}() RETURNS trigger LANGUAGE plpgsql AS $function$
        BEGIN PERFORM pg_advisory_xact_lock({}); RETURN NEW; END $function$;
        CREATE TRIGGER {} BEFORE INSERT ON {} FOR EACH ROW EXECUTE FUNCTION {}();
        """
    ).format(
        sql.Identifier(function),
        sql.Literal(key),
        sql.Identifier(function),
        sql.Identifier(table),
        sql.Identifier(function),
    )
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        connection.execute(statement)
    blocker = psycopg.connect(tenant.database.admin_dsn, autocommit=True)
    blocker.execute("SELECT pg_advisory_lock(%s)", (key,))
    return key, blocker


def _wait_for_insert_barrier(tenant: TenantFixture, key: int) -> None:
    deadline = time.monotonic() + _WAIT_SECONDS
    while time.monotonic() < deadline:
        with psycopg.connect(tenant.database.admin_dsn) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM pg_locks
                WHERE locktype = 'advisory' AND NOT granted AND objid = %s
                  AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
                """,
                (key,),
            ).fetchone()
        if row is not None:
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for the database insert barrier")


def _future_remained_blocked(future: Future[Any]) -> bool:
    try:
        future.result(timeout=0.2)
    except FutureTimeoutError:
        return True
    return False


def _fact_counts(tenant: TenantFixture) -> tuple[int, int, int, int]:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM console_view_grants),
                (SELECT count(*) FROM console_stream_opens),
                (SELECT count(*) FROM console_output_objects),
                (SELECT count(*) FROM console_output_access_facts)
            """
        ).fetchone()
    assert row is not None
    return cast(tuple[int, int, int, int], row)


def _telemetry() -> TelemetryContext:
    command_id = str(uuid4())
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id="0" * 32,
        span_id="0" * 16,
        trace_flags=1,
        correlation_id=command_id,
        causation_id=command_id,
        tenant_id="test-tenant",
        actor_id="test-actor",
        command_id=command_id,
    )


def _viewer(tenant: TenantFixture, adapter: Adapter, now: datetime) -> ConsoleViewer:
    return ConsoleViewer(
        PostgresConsoleAuthority(tenant.database.runtime_dsn, policy=policy()),
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        adapter,
        AesGcmConsoleCipher(
            wrapping_key=hashlib.sha256(b"console-authority-atomicity").digest(),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
        clock=lambda: now,
    )
