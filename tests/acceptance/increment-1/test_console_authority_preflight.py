"""Real-Postgres proofs that authority refusal precedes runtime inspection."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Generator
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Event
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
from support.tenant_fixture import TenantFixture

from ctower_kernel.console import (
    AesGcmConsoleCipher,
    ConsoleBackendObservation,
    ConsoleEventStream,
    ConsoleGlobalSwitchCommand,
    ConsoleOutputBatch,
    ConsoleSessionAllowance,
    ConsoleSessionAllowCommand,
    ConsoleSessionRef,
    ConsoleSessionRevocation,
    ConsoleViewer,
    ConsoleViewGrant,
    PostgresConsoleAuthority,
    PostgresConsoleOutputStore,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem

__all__: tuple[str, ...] = ()
_WAIT_SECONDS = 5
_INSERT_BARRIERS = {
    "grant": (
        437_021,
        """
        CREATE FUNCTION console_test_block_grant_insert() RETURNS trigger
        LANGUAGE plpgsql AS $function$
        BEGIN
            PERFORM pg_advisory_xact_lock(437021);
            RETURN NEW;
        END
        $function$;
        CREATE TRIGGER console_test_block_grant_insert
        BEFORE INSERT ON console_view_grants
        FOR EACH ROW EXECUTE FUNCTION console_test_block_grant_insert();
        """,
    ),
    "open": (
        437_022,
        """
        CREATE FUNCTION console_test_block_open_insert() RETURNS trigger
        LANGUAGE plpgsql AS $function$
        BEGIN
            PERFORM pg_advisory_xact_lock(437022);
            RETURN NEW;
        END
        $function$;
        CREATE TRIGGER console_test_block_open_insert
        BEFORE INSERT ON console_stream_opens
        FOR EACH ROW EXECUTE FUNCTION console_test_block_open_insert();
        """,
    ),
    "output": (
        437_023,
        """
        CREATE FUNCTION console_test_block_output_insert() RETURNS trigger
        LANGUAGE plpgsql AS $function$
        BEGIN
            PERFORM pg_advisory_xact_lock(437023);
            RETURN NEW;
        END
        $function$;
        CREATE TRIGGER console_test_block_output_insert
        BEFORE INSERT ON console_output_objects
        FOR EACH ROW EXECUTE FUNCTION console_test_block_output_insert();
        """,
    ),
    "access": (
        437_024,
        """
        CREATE FUNCTION console_test_block_access_insert() RETURNS trigger
        LANGUAGE plpgsql AS $function$
        BEGIN
            PERFORM pg_advisory_xact_lock(437024);
            RETURN NEW;
        END
        $function$;
        CREATE TRIGGER console_test_block_access_insert
        BEFORE INSERT ON console_output_access_facts
        FOR EACH ROW EXECUTE FUNCTION console_test_block_access_insert();
        """,
    ),
}


class _BarrierAdapter(Adapter):
    def __init__(self, ref: ConsoleSessionRef) -> None:
        super().__init__(observation(ref), b"authority-race-output")
        self._blocked_operation: Literal["inspect", "read"] | None = None
        self.entered = Event()
        self.release = Event()

    def arm(self, operation: Literal["inspect", "read"]) -> None:
        self._blocked_operation = operation
        self.entered.clear()
        self.release.clear()

    def inspect(self, session_ref: ConsoleSessionRef) -> ConsoleBackendObservation:
        self._block("inspect")
        return super().inspect(session_ref)

    def read(
        self,
        session_ref: ConsoleSessionRef,
        *,
        after_cursor: int,
        maximum_bytes: int,
    ) -> ConsoleOutputBatch:
        self._block("read")
        return super().read(
            session_ref,
            after_cursor=after_cursor,
            maximum_bytes=maximum_bytes,
        )

    def _block(self, operation: Literal["inspect", "read"]) -> None:
        if self._blocked_operation != operation:
            return
        self.entered.set()
        if not self.release.wait(_WAIT_SECONDS):
            raise AssertionError(f"timed out waiting to release blocked {operation}")
        self._blocked_operation = None


def test_non_operator_allowance_refuses_before_adapter_inspection(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    ref = recorded_session_ref(tenant)
    adapter = Adapter(observation(ref), b"must-not-be-read")
    viewer = _viewer(tenant, adapter, now)

    refused = viewer.allow_session(
        browser_actor(tenant, now=now),
        ConsoleSessionAllowCommand(ref, "restricted", "standard"),
    )

    assert isinstance(refused, RecordProblem)
    assert refused.code == "console-allowlist-refused"
    assert adapter.inspection_count == 0


@pytest.mark.parametrize("actor_state", ["commander", "foreign-project"])
def test_ineligible_actor_mint_refuses_before_adapter_inspection(
    tenant: TenantFixture,
    actor_state: str,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, adapter, _operator, browser, allowance = console_setup(tenant, now)
    actor = (
        replace(browser, kind=PrincipalKind.COMMANDER)
        if actor_state == "commander"
        else replace(browser, project_grants=frozenset({"foreign-project"}))
    )
    adapter.inspection_count = 0

    refused = viewer.mint_grant(actor, allowance.allowance_id)

    assert isinstance(refused, RecordProblem)
    assert refused.code == (
        "console-role-refused" if actor_state == "commander" else "console-project-refused"
    )
    assert adapter.inspection_count == 0


@pytest.mark.parametrize("authority_state", ["suspended", "revoked"])
def test_inactive_session_is_absent_and_mint_refuses_without_adapter_inspection(
    tenant: TenantFixture,
    authority_state: str,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, adapter, operator, browser, allowance = console_setup(tenant, now)
    if authority_state == "revoked":
        assert (
            viewer.revoke_session(
                operator,
                ConsoleSessionRevocation(allowance.allowance_id, "preflight refusal proof"),
            )
            is None
        )
    else:
        execute_service_fact(
            tenant,
            """
            INSERT INTO console_view_suspensions (
                suspension_id, tenant_id, actor_principal_id, denial_count,
                reason, suspended_at, expires_at
            ) VALUES (%s, %s, %s, 3, 'preflight refusal proof', %s, %s)
            """,
            (uuid4(), tenant.tenant_id, browser.principal_id, now, now + timedelta(minutes=15)),
        )
    adapter.inspection_count = 0

    assert viewer.visible_sessions(browser) == ()
    refused = viewer.mint_grant(browser, allowance.allowance_id)

    assert isinstance(refused, RecordProblem)
    assert refused.code == (
        "console-actor-suspended" if authority_state == "suspended" else "console-session-revoked"
    )
    assert adapter.inspection_count == 0


@pytest.mark.parametrize("grant_state", ["missing", "used"])
def test_unclaimable_grant_refuses_before_adapter_inspection(
    tenant: TenantFixture,
    grant_state: str,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, adapter, _operator, browser, allowance = console_setup(tenant, now)
    if grant_state == "used":
        assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
        opened = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
        assert isinstance(opened, ConsoleEventStream)
        next(opened.events)
        cast(Generator[bytes, None, None], opened.events).close()
    adapter.inspection_count = 0

    refused = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)

    assert isinstance(refused, RecordProblem)
    assert refused.code == "console-grant-unavailable"
    assert adapter.inspection_count == 0


def test_allowance_rechecks_authority_after_adapter_inspection(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    ref = recorded_session_ref(tenant)
    adapter = _BarrierAdapter(ref)
    viewer = _viewer(tenant, adapter, now)
    operator = replace(browser_actor(tenant, now=now), kind=PrincipalKind.OPERATOR)
    command = ConsoleSessionAllowCommand(ref, "restricted", "standard")
    adapter.arm("inspect")

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(viewer.allow_session, operator, command)
        assert adapter.entered.wait(_WAIT_SECONDS)
        execute_service_fact(
            tenant,
            """
            UPDATE assignment_intervals SET released_at = %s
            WHERE ticket_id = %s AND assignment_kind = %s AND interval_sequence = %s
            """,
            (
                now + timedelta(seconds=1),
                ref.assignment_ticket_id,
                ref.assignment_kind,
                ref.assignment_interval_sequence,
            ),
        )
        adapter.release.set()
        refused = future.result(timeout=_WAIT_SECONDS)

    assert isinstance(refused, RecordProblem)
    assert refused.code == "console-session-join-stale"
    assert _fact_counts(tenant)[:2] == (0, 0)


@pytest.mark.parametrize(
    ("decision", "authority_change", "expected_code"),
    [
        ("mint", "session", "console-session-revoked"),
        ("mint", "suspension", "console-actor-suspended"),
        ("mint", "human-session", "console-reauthentication-required"),
        ("renewal", "target", "console-session-join-stale"),
        ("renewal", "human-binding", "console-reauthentication-required"),
        ("open", "global", "console-globally-disabled"),
        ("open", "assignment", "console-session-revoked"),
    ],
)
def test_grant_and_open_recheck_revocation_after_adapter_inspection(
    tenant: TenantFixture,
    decision: str,
    authority_change: str,
    expected_code: str,
) -> None:
    now = datetime.now(UTC)
    viewer, adapter, operator, browser, allowance, ref = _barrier_setup(tenant, now)
    if decision in {"renewal", "open"}:
        assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    grants_before, _opens_before, _objects_before, _accesses_before = _fact_counts(tenant)
    adapter.arm("inspect")

    def decide() -> ConsoleEventStream | ConsoleViewGrant | RecordProblem:
        if decision == "open":
            return viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
        return viewer.mint_grant(
            browser,
            allowance.allowance_id,
            renewal=decision == "renewal",
        )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(decide)
        assert adapter.entered.wait(_WAIT_SECONDS)
        _apply_authority_change(
            authority_change, tenant, viewer, operator, browser, allowance, ref, now=now
        )
        adapter.release.set()
        refused = future.result(timeout=_WAIT_SECONDS)

    assert isinstance(refused, RecordProblem)
    assert refused.code == expected_code
    assert _fact_counts(tenant)[:2] == (grants_before, 0)


@pytest.mark.parametrize(
    ("authority_change", "expected_code"),
    [
        ("session", "revoked"),
        ("target", "revoked"),
        ("global", "globally_disabled"),
        ("assignment", "revoked"),
    ],
)
def test_active_read_rechecks_revocation_before_persisting_output(
    tenant: TenantFixture,
    authority_change: str,
    expected_code: str,
) -> None:
    now = datetime.now(UTC)
    viewer, adapter, operator, browser, allowance, ref = _barrier_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    opened = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(opened, ConsoleEventStream)
    adapter.arm("read")

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(next, opened.events)
        assert adapter.entered.wait(_WAIT_SECONDS)
        _apply_authority_change(
            authority_change, tenant, viewer, operator, browser, allowance, ref, now=now
        )
        adapter.release.set()
        closed = future.result(timeout=_WAIT_SECONDS)

    assert f'"code":"{expected_code}"'.encode() in closed
    with pytest.raises(StopIteration):
        next(opened.events)
    _grants, opens, objects, accesses = _fact_counts(tenant)
    assert opens == 1
    assert (objects, accesses) == (0, 0)


def test_preflight_denials_append_exactly_until_suspension(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, adapter, _operator, browser, allowance = console_setup(tenant, now)
    foreign_project = replace(browser, project_grants=frozenset({"foreign-project"}))
    adapter.inspection_count = 0

    for _attempt in range(3):
        refused = viewer.mint_grant(foreign_project, allowance.allowance_id)
        assert isinstance(refused, RecordProblem)
        assert refused.code == "console-project-refused"
    suspended = viewer.mint_grant(browser, allowance.allowance_id)

    assert isinstance(suspended, RecordProblem)
    assert suspended.code == "console-actor-suspended"
    assert adapter.inspection_count == 0
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM console_view_denials),
                (SELECT count(*) FROM console_view_suspensions)
            """
        ).fetchone()
    assert counts == (3, 1)


def test_human_session_expiry_during_inspection_refuses_grant(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, adapter, _operator, browser, allowance, _ref = _barrier_setup(tenant, now)
    assert browser.human_session_id is not None
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        row = connection.execute(
            "SELECT expires_at FROM human_sessions WHERE session_id = %s",
            (browser.human_session_id,),
        ).fetchone()
    assert row is not None
    later = cast(datetime, row[0]) + timedelta(seconds=1)
    clock_now = [now]
    viewer._clock = lambda: clock_now[0]
    adapter.arm("inspect")

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(viewer.mint_grant, browser, allowance.allowance_id)
        assert adapter.entered.wait(_WAIT_SECONDS)
        clock_now[0] = later
        adapter.release.set()
        refused = future.result(timeout=_WAIT_SECONDS)

    assert isinstance(refused, RecordProblem)
    assert refused.code == "console-reauthentication-required"
    assert _fact_counts(tenant)[0] == 0


def test_grant_insert_serializes_a_concurrent_global_disable(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _adapter, operator, browser, allowance, _ref = _barrier_setup(tenant, now)
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
    viewer, _adapter, _operator, browser, allowance, _ref = _barrier_setup(tenant, now)
    assert browser.human_session_id is not None
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    key, blocker = _install_insert_barrier(tenant, "open")
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            open_future = executor.submit(
                viewer.open_stream,
                browser,
                allowance.allowance_id,
                last_event_id=None,
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
    closed = next(opened.events)
    assert b'"code":"reauthentication_required"' in closed


def test_output_insert_serializes_a_concurrent_global_disable(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _adapter, operator, browser, allowance, _ref = _barrier_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    opened = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(opened, ConsoleEventStream)
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
    now = datetime.now(UTC)
    viewer, _adapter, operator, browser, allowance, _ref = _barrier_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    opened = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(opened, ConsoleEventStream)
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


def _barrier_setup(
    tenant: TenantFixture, now: datetime
) -> tuple[
    ConsoleViewer,
    _BarrierAdapter,
    Actor,
    Actor,
    ConsoleSessionAllowance,
    ConsoleSessionRef,
]:
    ref = recorded_session_ref(tenant)
    adapter = _BarrierAdapter(ref)
    viewer = _viewer(tenant, adapter, now)
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    browser = browser_actor(tenant, now=now)
    allowance = viewer.allow_session(
        operator, ConsoleSessionAllowCommand(ref, "restricted", "standard")
    )
    assert isinstance(allowance, ConsoleSessionAllowance)
    return viewer, adapter, operator, browser, allowance, ref


def _apply_authority_change(
    change: str,
    tenant: TenantFixture,
    viewer: ConsoleViewer,
    operator: Actor,
    browser: Actor,
    allowance: ConsoleSessionAllowance,
    ref: ConsoleSessionRef,
    *,
    now: datetime,
) -> None:
    if change == "session":
        assert (
            viewer.revoke_session(
                operator,
                ConsoleSessionRevocation(allowance.allowance_id, "adapter barrier race"),
            )
            is None
        )
        return
    if change == "suspension":
        execute_service_fact(
            tenant,
            """
            INSERT INTO console_view_suspensions (
                suspension_id, tenant_id, actor_principal_id, denial_count,
                reason, suspended_at, expires_at
            ) VALUES (%s, %s, %s, 3, 'adapter barrier race', %s, %s)
            """,
            (uuid4(), tenant.tenant_id, browser.principal_id, now, now + timedelta(minutes=15)),
        )
        return
    if change == "target":
        execute_service_fact(
            tenant,
            "UPDATE principals SET disabled = true WHERE principal_id = %s",
            (ref.seat_principal_id,),
            use_admin=True,
        )
        return
    if change == "assignment":
        execute_service_fact(
            tenant,
            """
            UPDATE assignment_intervals SET released_at = %s
            WHERE ticket_id = %s AND assignment_kind = %s AND interval_sequence = %s
            """,
            (
                now + timedelta(seconds=1),
                ref.assignment_ticket_id,
                ref.assignment_kind,
                ref.assignment_interval_sequence,
            ),
        )
        return
    if change == "human-session":
        assert browser.human_session_id is not None
        execute_service_fact(
            tenant,
            """
            INSERT INTO human_session_revocations (session_id, tenant_id, reason, revoked_at)
            VALUES (%s, %s, 'adapter barrier race', %s)
            """,
            (browser.human_session_id, tenant.tenant_id, now),
        )
        return
    if change == "human-binding":
        assert browser.human_binding_id is not None
        execute_service_fact(
            tenant,
            """
            INSERT INTO human_role_binding_revocations (
                binding_id, tenant_id, revoked_by, reason, revoked_at
            ) VALUES (%s, %s, %s, 'adapter barrier race', %s)
            """,
            (browser.human_binding_id, tenant.tenant_id, tenant.operator_id, now),
        )
        return
    assert change == "global"
    assert (
        viewer.set_global_switch(
            operator,
            ConsoleGlobalSwitchCommand(enabled=True, reason="adapter barrier race"),
        )
        is None
    )


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


def _install_insert_barrier(
    tenant: TenantFixture, kind: Literal["grant", "open", "output", "access"]
) -> tuple[int, psycopg.Connection[tuple[object, ...]]]:
    key, statement = _INSERT_BARRIERS[kind]
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


def _viewer(tenant: TenantFixture, adapter: Adapter, now: datetime) -> ConsoleViewer:
    return ConsoleViewer(
        PostgresConsoleAuthority(tenant.database.runtime_dsn, policy=policy()),
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        adapter,
        AesGcmConsoleCipher(
            wrapping_key=hashlib.sha256(b"console-authority-preflight").digest(),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
        clock=lambda: now,
    )
