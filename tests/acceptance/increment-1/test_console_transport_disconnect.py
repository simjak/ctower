"""Real-Postgres transport-disconnect closure proofs for Console SSE."""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import psycopg
import pytest
from console_test_support import Adapter, browser_actor, observation, policy, recorded_session_ref
from psycopg.rows import dict_row
from starlette.types import Send
from support.tenant_fixture import TenantFixture

from ctower_api.console_streaming import console_streaming_response
from ctower_kernel.console import (
    AesGcmConsoleCipher,
    ConsoleEventStream,
    ConsoleSessionAllowance,
    ConsoleSessionAllowCommand,
    ConsoleViewer,
    ConsoleViewGrant,
    PostgresConsoleAuthority,
    PostgresConsoleOutputStore,
)
from ctower_kernel.record import Actor, PrincipalKind

__all__: tuple[str, ...] = ()
_CHUNK_BYTES = 16 * 1024
_MAX_CLOSE_SECONDS = 5


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
