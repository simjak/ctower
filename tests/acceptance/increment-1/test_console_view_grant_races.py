"""Real-Postgres concurrency, replay, backpressure, and custody races for Console Phase 1."""

from __future__ import annotations

from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from typing import cast

import psycopg
import pytest
from console_test_support import console_setup
from psycopg.rows import dict_row
from support.tenant_fixture import TenantFixture

from ctower_kernel.console import (
    ConsoleEventStream,
    ConsoleSessionRevocation,
    ConsoleViewGrant,
)
from ctower_kernel.record import RecordProblem

__all__: tuple[str, ...] = ()


def test_parallel_stream_claim_has_exactly_one_real_postgres_winner(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, _operator, browser, allowance = console_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    barrier = Barrier(2)

    def claim() -> ConsoleEventStream | RecordProblem:
        barrier.wait()
        return viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [future.result() for future in (executor.submit(claim), executor.submit(claim))]
    streams = [outcome for outcome in outcomes if isinstance(outcome, ConsoleEventStream)]
    refusals = [outcome for outcome in outcomes if isinstance(outcome, RecordProblem)]
    assert len(streams) == 1
    assert [refusal.code for refusal in refusals] == ["console-stream-already-open"]
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        count = connection.execute("SELECT count(*) FROM console_stream_opens").fetchone()
    assert count == (1,)
    cast(Generator[bytes, None, None], streams[0].events).close()


def test_configured_pending_cap_closes_the_production_stream_as_slow_consumer(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, _operator, browser, allowance = console_setup(
        tenant, now, pending_bytes=1
    )
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(stream, ConsoleEventStream)

    gap = next(stream.events)
    closed = next(stream.events)

    assert b'"reason":"slow_consumer"' in gap
    assert b'"code":"slow_consumer"' in closed
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        facts = connection.execute(
            "SELECT reason FROM console_output_gap_facts WHERE allowance_id = %s",
            (allowance.allowance_id,),
        ).fetchall()
    assert facts == [{"reason": "slow_consumer"}]


def test_unprovable_reconnect_cursor_emits_one_durable_gap_then_resumes(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, _operator, browser, allowance = console_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=999_999)
    assert isinstance(stream, ConsoleEventStream)

    gap = next(stream.events)
    chunk = next(stream.events)

    assert gap.count(b"event: gap") == 1
    assert b'"reason":"unprovable_range"' in gap
    assert gap.startswith(b"id: ")
    assert b"event: chunk" in chunk
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        gaps = connection.execute(
            """
            SELECT cursor, reason FROM console_output_gap_facts
            WHERE allowance_id = %s ORDER BY cursor
            """,
            (allowance.allowance_id,),
        ).fetchall()
    gap_cursor = int(gap.splitlines()[0].removeprefix(b"id: "))
    assert gaps == [{"cursor": gap_cursor, "reason": "unprovable_range"}]
    assert int(chunk.splitlines()[0].removeprefix(b"id: ")) > gap_cursor
    cast(Generator[bytes, None, None], stream.events).close()


def test_revocation_between_replay_items_prevents_the_next_content_access(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, adapter, operator, browser, allowance = console_setup(tenant, now)
    adapter.payload = b"a" * (16 * 1024) + b"b" * (16 * 1024)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    original = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(original, ConsoleEventStream)
    assert b"event: chunk" in next(original.events)
    assert b"event: chunk" in next(original.events)
    cast(Generator[bytes, None, None], original.events).close()
    assert isinstance(
        viewer.mint_grant(browser, allowance.allowance_id, renewal=True), ConsoleViewGrant
    )
    replay = viewer.open_stream(browser, allowance.allowance_id, last_event_id=0)
    assert isinstance(replay, ConsoleEventStream)
    assert b"event: chunk" in next(replay.events)

    assert (
        viewer.revoke_session(
            operator,
            ConsoleSessionRevocation(allowance.allowance_id, "replay revocation proof"),
        )
        is None
    )
    assert b'"code":"revoked"' in next(replay.events)
    with pytest.raises(StopIteration):
        next(replay.events)
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        replay_accesses = connection.execute(
            """
            SELECT count(*) AS count FROM console_output_access_facts
            WHERE stream_id = %s AND access_kind = 'reconnect'
            """,
            (replay.lease.stream_id,),
        ).fetchone()
    assert replay_accesses == {"count": 1}


def test_committed_reader_access_id_can_recover_content_only_once(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, _operator, browser, allowance = console_setup(tenant, now)
    assert isinstance(viewer.mint_grant(browser, allowance.allowance_id), ConsoleViewGrant)
    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(stream, ConsoleEventStream)
    assert b"event: chunk" in next(stream.events)
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        access = connection.execute("SELECT access_id FROM console_output_access_facts").fetchone()
        recovery = connection.execute(
            "SELECT count(*) AS count FROM console_output_recovery_facts"
        ).fetchone()
    assert access is not None and recovery == {"count": 1}
    with (
        pytest.raises(psycopg.errors.UniqueViolation),
        psycopg.connect(tenant.database.runtime_dsn) as connection,
    ):
        connection.execute("SET ROLE ctower_svc")
        connection.execute(
            "SELECT * FROM recover_console_output_object(%s, %s)",
            (access["access_id"], now),
        ).fetchall()
    with psycopg.connect(tenant.database.admin_dsn) as connection:
        count = connection.execute("SELECT count(*) FROM console_output_recovery_facts").fetchone()
    assert count == (1,)
    cast(Generator[bytes, None, None], stream.events).close()
