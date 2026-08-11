"""Real-Postgres proof that authorized viewers share one serialized collection cursor."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier, Lock
from typing import cast

import psycopg
from console_test_support import (
    Adapter,
    browser_actor,
    console_setup,
    observation,
    policy,
    recorded_session_ref,
)
from psycopg.rows import dict_row
from support.tenant_fixture import TenantFixture

from ctower_kernel.console import (
    AesGcmConsoleCipher,
    ConsoleBackendObservation,
    ConsoleEventStream,
    ConsoleOutputBatch,
    ConsoleSessionAllowance,
    ConsoleSessionAllowCommand,
    ConsoleSessionRef,
    ConsoleViewer,
    ConsoleViewGrant,
    PostgresConsoleAuthority,
    PostgresConsoleOutputStore,
)
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem

__all__: tuple[str, ...] = ()
_GRANT_CHAIN_LENGTH = 3


def test_two_authorized_actors_collect_one_shared_source_position_serially(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    ref = recorded_session_ref(tenant)
    adapter = _CountingAdapter(observation(ref), b"shared-source-position")
    authority = PostgresConsoleAuthority(tenant.database.runtime_dsn, policy=policy())
    viewer = ConsoleViewer(
        authority,
        PostgresConsoleOutputStore(tenant.database.runtime_dsn),
        adapter,
        AesGcmConsoleCipher(
            wrapping_key=hashlib.sha256(b"two-actor-collection-lock").digest(),
            wrapping_key_reference="secret-service:ctower-development/console-output-kek",
        ),
        clock=lambda: now,
    )
    operator = Actor(tenant.operator_id, tenant.tenant_id, PrincipalKind.OPERATOR)
    first_actor = browser_actor(tenant, now=now)
    second_actor = browser_actor(tenant, now=now)
    allowance = viewer.allow_session(
        operator, ConsoleSessionAllowCommand(ref, "restricted", "standard")
    )
    assert isinstance(allowance, ConsoleSessionAllowance)
    assert isinstance(viewer.mint_grant(first_actor, allowance.allowance_id), ConsoleViewGrant)
    assert isinstance(viewer.mint_grant(second_actor, allowance.allowance_id), ConsoleViewGrant)
    first = viewer.open_stream(first_actor, allowance.allowance_id, last_event_id=None)
    second = viewer.open_stream(second_actor, allowance.allowance_id, last_event_id=None)
    assert isinstance(first, ConsoleEventStream)
    assert isinstance(second, ConsoleEventStream)
    barrier = Barrier(2)

    def read(stream: ConsoleEventStream) -> bytes:
        barrier.wait()
        return next(stream.events)

    with ThreadPoolExecutor(max_workers=2) as executor:
        events = [
            future.result()
            for future in (executor.submit(read, first), executor.submit(read, second))
        ]

    assert all(b"event: chunk" in event for event in events)
    assert events[0] == events[1]
    assert adapter.read_count == 1
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        facts = connection.execute(
            """
            SELECT
                (SELECT count(*) FROM console_output_objects) AS objects,
                (SELECT count(*) FROM console_output_access_facts) AS accesses,
                (SELECT count(*) FROM console_output_recovery_facts) AS recoveries
            """
        ).fetchone()
    assert facts == {"objects": 1, "accesses": 2, "recoveries": 2}
    cast(Generator[bytes, None, None], first.events).close()
    cast(Generator[bytes, None, None], second.events).close()


class _CountingAdapter(Adapter):
    def __init__(self, live_observation: ConsoleBackendObservation, payload: bytes) -> None:
        super().__init__(live_observation, payload)
        self._read_lock = Lock()
        self.read_count = 0

    def read(
        self,
        session_ref: ConsoleSessionRef,
        *,
        after_cursor: int,
        maximum_bytes: int,
    ) -> ConsoleOutputBatch:
        with self._read_lock:
            self.read_count += 1
        time.sleep(0.1)
        return super().read(session_ref, after_cursor=after_cursor, maximum_bytes=maximum_bytes)


def test_parallel_renew_before_use_forms_one_linear_latest_grant_chain(
    tenant: TenantFixture,
) -> None:
    now = datetime.now(UTC)
    viewer, _authority, _adapter, _operator, browser, allowance = console_setup(tenant, now)
    initial = viewer.mint_grant(browser, allowance.allowance_id)
    assert isinstance(initial, ConsoleViewGrant)
    barrier = Barrier(2)

    def renew() -> ConsoleViewGrant | RecordProblem:
        barrier.wait()
        return viewer.mint_grant(browser, allowance.allowance_id, renewal=True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [future.result() for future in (executor.submit(renew), executor.submit(renew))]
    assert all(isinstance(outcome, ConsoleViewGrant) for outcome in outcomes)
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        chain = connection.execute(
            """
            SELECT grant_id, renewed_from_grant_id
            FROM console_view_grants
            WHERE allowance_id = %s
            ORDER BY grant_sequence
            """,
            (allowance.allowance_id,),
        ).fetchall()
    assert len(chain) == _GRANT_CHAIN_LENGTH
    assert chain[0]["grant_id"] == initial.grant_id
    assert chain[0]["renewed_from_grant_id"] is None
    assert chain[1]["renewed_from_grant_id"] == chain[0]["grant_id"]
    assert chain[2]["renewed_from_grant_id"] == chain[1]["grant_id"]

    stream = viewer.open_stream(browser, allowance.allowance_id, last_event_id=None)
    assert isinstance(stream, ConsoleEventStream)
    assert stream.lease.grant.grant_id == chain[2]["grant_id"]
    with psycopg.connect(tenant.database.admin_dsn, row_factory=dict_row) as connection:
        claimed = connection.execute(
            "SELECT grant_id FROM console_stream_opens WHERE stream_id = %s",
            (stream.lease.stream_id,),
        ).fetchone()
    assert claimed == {"grant_id": chain[2]["grant_id"]}
    cast(Generator[bytes, None, None], stream.events).close()
