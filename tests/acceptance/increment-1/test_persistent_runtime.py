"""Persistent development-runtime acceptance at the ordinary finalizer boundary."""

from __future__ import annotations

import signal
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import psycopg
import pytest
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

from ctower_api import development_runtime
from ctower_api.development_finalizer import DevelopmentFinalizerProgress
from ctower_api.interface import create_app
from ctower_api.synthetic_handler import SyntheticRetryError
from ctower_kernel.record import DurabilityHealthStatus, RecordProblem
from ctower_kernel.record import _durability_finalizer_sql as finalizer_sql
from ctower_kernel.record.postgres import PostgresRecord

__all__: tuple[str, ...] = ()
_HTTP_ACCEPTED = 202
_HTTP_CREATED = 201
_REFUSAL_ATTEMPTS = 3
_WORKER_SCANS_PAST_BOUND = 7
_PACKS = Path(__file__).parents[3] / "packs"


@dataclass(frozen=True, slots=True)
class _DevelopmentAuthority:
    pair: DurabilityPair
    database: DatabaseFixture
    standby_dsn: str
    tenant: TenantFixture


@dataclass(slots=True)
class _BoundedWorkerStop:
    scans: int
    after_scan: Callable[[], None]
    completed: int = 0
    signalled: bool = False

    def is_set(self) -> bool:
        return self.signalled or self.completed >= self.scans

    def wait(self, _timeout: float) -> bool:
        self.completed += 1
        self.after_scan()
        return self.is_set()

    def set(self) -> None:
        self.signalled = True


class _RetryingSyntheticHandler:
    def execute(self, _attempt: object) -> object:
        raise SyntheticRetryError


@dataclass(slots=True)
class _RefusingReconciler:
    refused_id: UUID
    actual: Callable[..., object]
    calls: int = 0

    def __call__(
        self,
        primary_dsn: str,
        standby_dsn: str | None,
        tenant_id: UUID,
        principal_id: UUID,
        command_id: UUID,
        *,
        now: datetime,
    ) -> object:
        if command_id == self.refused_id:
            self.calls += 1
            return RecordProblem(
                "durability-integrity",
                "Permanent test refusal",
                503,
                "Durability integrity unavailable",
                command_id,
            )
        return self.actual(
            primary_dsn,
            standby_dsn,
            tenant_id,
            principal_id,
            command_id,
            now=now,
        )


def test_ordinary_finalizer_reconciles_development_ack_without_cp3d_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        progress = _run_development_worker(authority, monkeypatch, scans=2)

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

        assert any(item.accepted >= 1 for item in progress)
        assert replay.status_code == _HTTP_CREATED
        assert replay.json()["durability_state"] == "accepted"
        assert durable_ticket.json()["durability_state"] == "accepted"
        assert health.status is DurabilityHealthStatus.DEGRADED
        assert health.reason == "development_offhost_ack_cp3_d_not_proven"


def test_refused_finalization_quarantines_finitely_and_later_work_is_serviced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ordinary worker durably bounds refusal retries without blocking later work."""

    with _development_authority() as authority:
        record = PostgresRecord(
            authority.database.runtime_dsn,
            standby_dsn=authority.standby_dsn,
        )
        refused_id = uuid4()
        later_id = uuid4()
        _create_refusal_fixture(authority, record, refused_id, later_id)
        wait_for_durability_replay_current(authority.pair)

        refusal = _RefusingReconciler(
            refused_id,
            cast(
                Callable[..., object],
                getattr(finalizer_sql, "reconcile_durability"),  # noqa: B009
            ),
        )
        clock = [_database_now(authority.database.admin_dsn)]
        monkeypatch.setattr(finalizer_sql, "reconcile_durability", refusal)
        monkeypatch.setattr(finalizer_sql, "_database_now", lambda _dsn: clock[0])
        progress = _run_development_worker(
            authority,
            monkeypatch,
            scans=_WORKER_SCANS_PAST_BOUND,
            after_scan=lambda: clock.__setitem__(0, clock[0] + timedelta(seconds=61)),
        )

        _assert_quarantine_evidence(authority.database.admin_dsn, refused_id)
        with TestClient(create_app(record), client=("127.0.0.1", 51000)) as client:
            later_replay = create_ticket(
                client,
                authority.tenant,
                later_id,
                title="Later finalization still serviced",
            )

        assert refusal.calls == _REFUSAL_ATTEMPTS
        assert any(item.quarantined == 1 for item in progress)
        assert later_replay.status_code == _HTTP_CREATED
        assert later_replay.json()["durability_state"] == "accepted"


def _run_development_worker(
    authority: _DevelopmentAuthority,
    monkeypatch: pytest.MonkeyPatch,
    *,
    scans: int,
    after_scan: Callable[[], None] = lambda: None,
) -> tuple[DevelopmentFinalizerProgress, ...]:
    progress: list[DevelopmentFinalizerProgress] = []
    _patch_worker_dependencies(authority, monkeypatch, progress)
    stop = _BoundedWorkerStop(scans, after_scan)
    monkeypatch.setattr(development_runtime, "Event", lambda: stop)
    monkeypatch.setattr(signal, "signal", lambda *_args: None)

    development_runtime.worker_main()

    assert stop.completed == scans
    return tuple(progress)


def _patch_worker_dependencies(
    authority: _DevelopmentAuthority,
    monkeypatch: pytest.MonkeyPatch,
    progress: list[DevelopmentFinalizerProgress],
) -> None:
    unused_reference = "unused-reference"
    config = SimpleNamespace(
        api_host="127.0.0.1",
        api_port=8091,
        commander_secret_ref=unused_reference,
        operator_secret_ref=unused_reference,
    )
    dsn_by_role = {
        ("ctower_runtime", False): authority.database.runtime_dsn,
        ("ctower_projection_runtime", False): authority.database.projection_dsn,
        ("postgres", True): authority.standby_dsn,
    }
    monkeypatch.setattr(development_runtime, "load_config", lambda: config)
    monkeypatch.setattr(
        development_runtime,
        "load_state",
        lambda: SimpleNamespace(commander_id=authority.tenant.commander_id),
    )
    monkeypatch.setattr(
        development_runtime,
        "development_dsn",
        lambda _config, role, *, standby=False: dsn_by_role[(role, standby)],
    )
    monkeypatch.setattr(development_runtime, "load_secret", lambda _reference: "unused")
    monkeypatch.setattr(development_runtime, "_pack_root", lambda: _PACKS)
    monkeypatch.setattr(
        development_runtime,
        "load_finalizer_progress",
        lambda: (_ for _ in ()).throw(OSError("no prior progress")),
    )
    monkeypatch.setattr(development_runtime, "write_finalizer_progress", progress.append)
    monkeypatch.setattr(
        development_runtime,
        "SyntheticFourStageHandler",
        lambda *_args, **_kwargs: _RetryingSyntheticHandler(),
    )


def _create_refusal_fixture(
    authority: _DevelopmentAuthority,
    record: PostgresRecord,
    refused_id: UUID,
    later_id: UUID,
) -> None:
    with (
        TestClient(create_app(record), client=("127.0.0.1", 51000)) as client,
        pause_durability_replay(authority.pair),
    ):
        refused = create_ticket(
            client,
            authority.tenant,
            refused_id,
            title="Permanently refused finalization",
        )
        later = create_ticket(
            client,
            authority.tenant,
            later_id,
            title="Later finalization still serviced",
        )
    assert refused.status_code == _HTTP_ACCEPTED
    assert later.status_code == _HTTP_ACCEPTED


def _assert_quarantine_evidence(dsn: str, refused_id: UUID) -> None:
    with psycopg.connect(dsn) as connection:
        attempts = connection.execute(
            """
            SELECT attempt_number, outcome, problem_code, next_attempt_at
            FROM durability_finalizer_attempts
            WHERE client_command_id = %s
            ORDER BY attempt_number
            """,
            (refused_id,),
        ).fetchall()
        confirmations = connection.execute(
            """
            SELECT count(*)
            FROM durability_acceptance_confirmations
            WHERE client_command_id = %s
            """,
            (refused_id,),
        ).fetchone()
    assert [(row[0], row[1], row[2]) for row in attempts] == [
        (1, "retry_scheduled", "durability-integrity"),
        (2, "retry_scheduled", "durability-integrity"),
        (3, "quarantined", "durability-integrity"),
    ]
    assert attempts[-1][3] is None
    assert confirmations == (0,)


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
