"""Real-Postgres transport-disconnect closure proofs for Console SSE."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import cast
from uuid import UUID

import psycopg
import pytest
from console_test_support import (
    Adapter,
    Clock,
    browser_actor,
    observation,
    policy,
    recorded_session_ref,
)
from psycopg.rows import dict_row
from starlette.types import Send
from support.tenant_fixture import TenantFixture

from ctower_api.console_streaming import console_streaming_response
from ctower_kernel.console import (
    AesGcmConsoleCipher,
    ConsoleEventStream,
    ConsoleGlobalSwitchCommand,
    ConsoleSessionAllowance,
    ConsoleSessionAllowCommand,
    ConsoleSessionRevocation,
    ConsoleViewer,
    ConsoleViewGrant,
    PostgresConsoleAuthority,
    PostgresConsoleOutputStore,
)
from ctower_kernel.record import Actor, PrincipalKind

__all__: tuple[str, ...] = ()
_CHUNK_BYTES = 16 * 1024
_MAX_CLOSE_SECONDS = 5
_MAX_REVOCATION_POLL_SECONDS = 4
_STALE_OUTPUT_SECONDS = 61


class _ReplayAgeBoundObservedError(Exception):
    """The stale-replay proof reached its empty-output wait without yielding old bytes."""


@pytest.mark.parametrize("pending_bytes", [_CHUNK_BYTES, 256 * 1024])
def test_immediate_send_error_closes_as_client_disconnect_without_slow_gap(
    tenant: TenantFixture,
    pending_bytes: int,
) -> None:
    stream, allowance = _stream(
        tenant,
        pending_bytes=pending_bytes,
        payload=b"a" * _CHUNK_BYTES + b"b" * _CHUNK_BYTES,
    )

    elapsed = asyncio.run(_fail_first_body_send(stream))

    assert elapsed <= _MAX_CLOSE_SECONDS
    _assert_client_disconnect(tenant, stream, allowance.allowance_id)


def test_cancellation_while_iterator_waits_closes_as_client_disconnect(
    tenant: TenantFixture,
) -> None:
    stream, allowance = _stream(tenant, pending_bytes=256 * 1024, payload=b"")

    elapsed = asyncio.run(_cancel_waiting_response(stream))

    assert elapsed <= _MAX_CLOSE_SECONDS
    _assert_client_disconnect(tenant, stream, allowance.allowance_id)


@pytest.mark.parametrize(
    ("change", "expected_code"),
    [("session", "revoked"), ("global", "globally_disabled")],
)
def test_revocation_and_kill_switch_close_the_real_delivery_loop_within_five_seconds(
    tenant: TenantFixture,
    change: str,
    expected_code: str,
) -> None:
    now = datetime.now(UTC)
    sleeper_started = Event()

    def measured_sleep(seconds: float) -> None:
        sleeper_started.set()
        time.sleep(seconds)

    viewer, operator, allowance, stream = _polling_stream(tenant, now, measured_sleep)
    with ThreadPoolExecutor(max_workers=1) as executor:
        closing_event = executor.submit(_wait_for_durable_close, stream)
        assert sleeper_started.wait(timeout=1)
        _apply_control_change(change, viewer, operator, allowance)
        committed_at = time.monotonic()
        closed = closing_event.result(timeout=_MAX_CLOSE_SECONDS)
        elapsed = time.monotonic() - committed_at

    assert f'"code":"{expected_code}"'.encode() in closed
    assert elapsed <= _MAX_CLOSE_SECONDS
    _assert_control_fact_to_close_bound(tenant, stream, allowance, change, expected_code, now)


def test_reconnect_never_recovers_output_older_than_the_replay_age_bound(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    clock = Clock(now)

    def stale_replay_wait(_seconds: float) -> None:
        raise _ReplayAgeBoundObservedError

    ref = recorded_session_ref(tenant)
    authority = PostgresConsoleAuthority(tenant.database.runtime_dsn, policy=policy())
    viewer = ConsoleViewer(
        authority,
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        Adapter(observation(ref), b"must-not-replay-after-sixty-seconds"),
        AesGcmConsoleCipher(
            wrapping_key=hashlib.sha256(b"replay-age-kek").digest(),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
        clock=clock,
        sleeper=stale_replay_wait,
    )
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    browser = browser_actor(tenant, now=now)
    allowance = viewer.allow_session(
        operator, ConsoleSessionAllowCommand(ref, "restricted", "standard")
    )
    assert isinstance(allowance, ConsoleSessionAllowance)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    initial = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(initial, ConsoleEventStream)
    assert b"event: chunk" in next(initial.events)
    cast(Generator[bytes, None, None], initial.events).close()

    clock.now += timedelta(seconds=_STALE_OUTPUT_SECONDS)
    assert isinstance(
        viewer.mint_grant(browser, allowance.allowance_id, renewal=True), ConsoleViewGrant
    )
    reconnect = viewer.open_stream(browser, allowance.allowance_id, last_event_id=0)
    assert isinstance(reconnect, ConsoleEventStream)
    with pytest.raises(_ReplayAgeBoundObservedError):
        next(reconnect.events)
    _assert_one_output_access(tenant, allowance.allowance_id)


def _polling_stream(
    tenant: TenantFixture,
    now: datetime,
    sleeper: Callable[[float], None],
) -> tuple[ConsoleViewer, Actor, ConsoleSessionAllowance, ConsoleEventStream]:
    ref = recorded_session_ref(tenant)
    active_policy = policy()
    assert active_policy.revocation_poll_seconds == _MAX_REVOCATION_POLL_SECONDS
    authority = PostgresConsoleAuthority(tenant.database.runtime_dsn, policy=active_policy)
    viewer = ConsoleViewer(
        authority,
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        Adapter(observation(ref), b"poll-bound-output"),
        AesGcmConsoleCipher(
            wrapping_key=hashlib.sha256(b"poll-bound-kek").digest(),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
        sleeper=sleeper,
    )
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    browser = browser_actor(tenant, now=now)
    allowance = viewer.allow_session(
        operator, ConsoleSessionAllowCommand(ref, "restricted", "standard")
    )
    assert isinstance(allowance, ConsoleSessionAllowance)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(stream, ConsoleEventStream)
    assert b"event: chunk" in next(stream.events)
    return viewer, operator, allowance, stream


def _wait_for_durable_close(stream: ConsoleEventStream) -> bytes:
    closed_event = next(stream.events)
    try:
        next(stream.events)
    except StopIteration:
        return closed_event
    raise AssertionError("Console stream emitted content after its typed close")


def _apply_control_change(
    change: str,
    viewer: ConsoleViewer,
    operator: Actor,
    allowance: ConsoleSessionAllowance,
) -> None:
    if change == "session":
        outcome = viewer.revoke_session(
            operator,
            ConsoleSessionRevocation(allowance.allowance_id, "wall-clock revocation proof"),
        )
    else:
        outcome = viewer.set_global_switch(
            operator,
            ConsoleGlobalSwitchCommand(enabled=True, reason="wall-clock kill-switch proof"),
        )
    assert outcome is None


def _assert_control_fact_to_close_bound(
    tenant: TenantFixture,
    stream: ConsoleEventStream,
    allowance: ConsoleSessionAllowance,
    change: str,
    expected_code: str,
    started_at: datetime,
) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        close = connection.execute(
            "SELECT code, closed_at FROM console_stream_closes WHERE stream_id = %s",
            (stream.lease.stream_id,),
        ).fetchone()
        if change == "session":
            control = connection.execute(
                "SELECT revoked_at AS control_at FROM console_session_revocations "
                "WHERE allowance_id = %s",
                (allowance.allowance_id,),
            ).fetchone()
        else:
            control = connection.execute(
                """
                SELECT recorded_at AS control_at
                FROM console_global_kill_switch_facts
                WHERE tenant_id = %s AND enabled
                ORDER BY recorded_at DESC, fact_id DESC
                LIMIT 1
                """,
                (tenant.tenant_id,),
            ).fetchone()
    assert close is not None
    assert control is not None
    assert close["code"] == expected_code
    assert cast(datetime, close["closed_at"]) >= started_at
    assert cast(datetime, close["closed_at"]) - cast(datetime, control["control_at"]) <= timedelta(
        seconds=_MAX_CLOSE_SECONDS
    )


def _assert_one_output_access(tenant: TenantFixture, allowance_id: UUID) -> None:
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        accesses = connection.execute(
            """
            SELECT count(*)
            FROM console_output_access_facts AS access
            JOIN console_output_objects AS object USING (object_id)
            WHERE object.allowance_id = %s
            """,
            (allowance_id,),
        ).fetchone()
    assert accesses == (1,)


def _stream(
    tenant: TenantFixture,
    *,
    pending_bytes: int,
    payload: bytes,
) -> tuple[ConsoleEventStream, ConsoleSessionAllowance]:
    now = datetime.now(UTC)
    ref = recorded_session_ref(tenant)
    authority = PostgresConsoleAuthority(
        tenant.database.runtime_dsn,
        policy=replace(
            policy(pending_bytes=pending_bytes),
            revocation_poll_seconds=1,
        ),
    )
    viewer = ConsoleViewer(
        authority,
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        Adapter(observation(ref), payload),
        AesGcmConsoleCipher(
            wrapping_key=hashlib.sha256(b"transport-disconnect").digest(),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
    )
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    browser = browser_actor(tenant, now=now)
    allowance = viewer.allow_session(
        operator, ConsoleSessionAllowCommand(ref, "restricted", "standard")
    )
    assert isinstance(allowance, ConsoleSessionAllowance)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(stream, ConsoleEventStream)
    return stream, allowance


async def _fail_first_body_send(stream: ConsoleEventStream) -> float:
    response = console_streaming_response(stream)

    async def send(message: dict[str, object]) -> None:
        if message.get("type") == "http.response.body" and message.get("body"):
            # Let the producer enter its next synchronous read before the peer drops.
            await asyncio.sleep(0.05)
            raise OSError("peer disconnected")

    started = time.monotonic()
    with pytest.raises(OSError, match="peer disconnected"):
        await response.stream_response(cast(Send, send))
    return time.monotonic() - started


async def _cancel_waiting_response(stream: ConsoleEventStream) -> float:
    response = console_streaming_response(stream)
    response_started = asyncio.Event()

    async def send(message: dict[str, object]) -> None:
        if message.get("type") == "http.response.start":
            response_started.set()

    task = asyncio.create_task(response.stream_response(cast(Send, send)))
    await asyncio.wait_for(response_started.wait(), timeout=1)
    await asyncio.sleep(0.05)
    started = time.monotonic()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    return time.monotonic() - started


def _assert_client_disconnect(
    tenant: TenantFixture,
    stream: ConsoleEventStream,
    allowance_id: UUID,
) -> None:
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        facts = connection.execute(
            """
            SELECT close.code, close.gap_required,
                (SELECT count(*) FROM console_output_gap_facts
                 WHERE allowance_id = %s) AS gaps
            FROM console_stream_closes AS close
            WHERE close.stream_id = %s
            """,
            (allowance_id, stream.lease.stream_id),
        ).fetchall()
    assert facts == [{"code": "client_disconnected", "gap_required": False, "gaps": 0}]
