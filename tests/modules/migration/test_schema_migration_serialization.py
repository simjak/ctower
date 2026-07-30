"""Migration control-lock coverage of cluster-global role reconciliation."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from random import SystemRandom
from threading import Event, Lock

import psycopg
import pytest

from ctower_kernel.record import _setup_sql
from ctower_kernel.record.postgres import apply_migrations, provision_database_roles

from ._postgres import Database

__all__: tuple[str, ...] = ()
_MIGRATION_CONTROL = vars(_setup_sql)["_migration_control_sql"]
_NETWORK_ATTEMPTS = 10
_CONCURRENT_CALLERS = 2
_ROLE_POLICY_ATTEMPTS = 3
_NETWORK_DEADLINE_SECONDS = 10.0
_CONNECT_TIMEOUT_SECONDS = 2
_STATEMENT_TIMEOUT_MS = 1_000
_MAXIMUM_BACKOFF_SECONDS = 0.5
_RANDOM = SystemRandom()


class _MaximumJitter:
    @staticmethod
    def uniform(_lower: float, upper: float) -> float:
        return upper


def test_role_reconciliation_retries_transient_failures_with_capped_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def transient_then_success(_dsn: str) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < _ROLE_POLICY_ATTEMPTS:
            raise psycopg.OperationalError("transient connection failure")

    monkeypatch.setattr(_MIGRATION_CONTROL, "_RANDOM", _MaximumJitter())
    monkeypatch.setattr(
        "ctower_kernel.record._migration_control_sql.time.sleep",
        sleeps.append,
    )

    _MIGRATION_CONTROL.reconcile_database_roles(
        "postgresql://postgres@127.0.0.1/ctower",
        transient_then_success,
    )

    assert attempts == _ROLE_POLICY_ATTEMPTS
    assert sleeps == [0.05, 0.1]


def test_role_reconciliation_permanent_failure_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    def permanent_failure(_dsn: str) -> None:
        nonlocal attempts
        attempts += 1
        raise psycopg.errors.InvalidPassword("permanent authentication failure")

    monkeypatch.setattr(
        "ctower_kernel.record._migration_control_sql.time.sleep",
        sleeps.append,
    )

    with pytest.raises(psycopg.errors.InvalidPassword):
        _MIGRATION_CONTROL.reconcile_database_roles(
            "postgresql://postgres@127.0.0.1/ctower",
            permanent_failure,
        )

    assert attempts == 1
    assert sleeps == []


def test_role_reconciliation_exhaustion_is_typed_and_attributable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failures: list[psycopg.OperationalError] = []
    sleeps: list[float] = []

    def transient_failure(_dsn: str) -> None:
        failure = psycopg.OperationalError("transient connection failure")
        failures.append(failure)
        raise failure

    monkeypatch.setattr(_MIGRATION_CONTROL, "_RANDOM", _MaximumJitter())
    monkeypatch.setattr(
        "ctower_kernel.record._migration_control_sql.time.sleep",
        sleeps.append,
    )

    with pytest.raises(_MIGRATION_CONTROL.MigrationNetworkExhaustedError) as raised:
        _MIGRATION_CONTROL.reconcile_database_roles(
            "postgresql://postgres@127.0.0.1/ctower",
            transient_failure,
        )

    assert raised.value.operation == "role-reconciliation"
    assert raised.value.attempt_count == _ROLE_POLICY_ATTEMPTS
    assert raised.value.elapsed_seconds >= 0
    assert raised.value.last_failure is failures[-1]
    assert sleeps == [0.05, 0.1]


def test_direct_role_reconciliation_serializes_a_new_caller(
    migration_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_entered = Event()
    release_first = Event()
    second_entered = Event()
    counter_lock = Lock()
    call_count = 0
    active_count = 0
    maximum_active = 0
    actual = vars(_setup_sql)["validate_recovery_role_shapes"]

    def observe_reconciliation(connection: psycopg.Connection[dict[str, object]]) -> None:
        nonlocal active_count, call_count, maximum_active
        with counter_lock:
            call_count += 1
            active_count += 1
            maximum_active = max(maximum_active, active_count)
            call_number = call_count
        if call_number == 1:
            first_entered.set()
            if not release_first.wait(timeout=10):
                raise AssertionError("first role reconciliation was not released")
        else:
            second_entered.set()
        try:
            actual(connection)
        finally:
            with counter_lock:
                active_count -= 1

    monkeypatch.setattr(_setup_sql, "validate_recovery_role_shapes", observe_reconciliation)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(provision_database_roles, migration_database.admin_dsn)
        assert first_entered.wait(timeout=10)
        second = workers.submit(provision_database_roles, migration_database.admin_dsn)
        try:
            second_entered.wait(timeout=1)
        finally:
            release_first.set()
        first.result(timeout=60)
        second.result(timeout=60)

    assert call_count == _CONCURRENT_CALLERS
    assert maximum_active == 1


def test_migration_lock_precedes_cluster_role_reconciliation(
    migration_database: Database,
) -> None:
    with ThreadPoolExecutor(max_workers=1) as worker:
        with (
            _MIGRATION_CONTROL.migration_control(migration_database.admin_dsn),
            _connect_with_backoff(migration_database.projection_dsn) as active_projection,
        ):
            migration = worker.submit(
                apply_migrations,
                migration_database.migrator_dsn,
                role_admin_dsn=migration_database.admin_dsn,
            )
            try:
                _wait_for_migration_lock(migration_database)
                assert active_projection.execute("SELECT 1").fetchone() == (1,)
            finally:
                active_projection.close()
        migration.result(timeout=60)


def _wait_for_migration_lock(database: Database) -> None:
    started = time.monotonic()
    delay = 0.01
    last_failure: psycopg.Error | None = None
    for attempt in range(1, _NETWORK_ATTEMPTS + 1):
        try:
            with _bounded_connect(database.admin_dsn) as connection:
                waiting = connection.execute(
                    """
                    SELECT 1 FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND wait_event_type = 'Lock'
                      AND wait_event = 'advisory'
                      AND query LIKE 'SELECT pg_advisory_lock%'
                    """
                ).fetchone()
        except psycopg.Error as error:
            if not _MIGRATION_CONTROL.retryable_database_failure(error):
                raise
            last_failure = error
        else:
            if waiting is not None:
                return
        if attempt < _NETWORK_ATTEMPTS:
            remaining = _NETWORK_DEADLINE_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                break
            ceiling = min(delay, _MAXIMUM_BACKOFF_SECONDS, remaining)
            time.sleep(_RANDOM.uniform(ceiling / 2, ceiling))
            delay *= 2
    raise AssertionError("migration caller did not wait for the control lock") from last_failure


def _connect_with_backoff(
    dsn: str,
) -> psycopg.Connection[tuple[object, ...]]:
    started = time.monotonic()
    delay = 0.01
    last_failure: psycopg.Error | None = None
    for attempt in range(1, _NETWORK_ATTEMPTS + 1):
        try:
            return _bounded_connect(dsn, autocommit=True)
        except psycopg.Error as error:
            if not _MIGRATION_CONTROL.retryable_database_failure(error):
                raise
            last_failure = error
        if attempt < _NETWORK_ATTEMPTS:
            remaining = _NETWORK_DEADLINE_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                break
            ceiling = min(delay, _MAXIMUM_BACKOFF_SECONDS, remaining)
            time.sleep(_RANDOM.uniform(ceiling / 2, ceiling))
            delay *= 2
    raise AssertionError("test database connection retry policy exhausted") from last_failure


def _bounded_connect(
    dsn: str,
    *,
    autocommit: bool = False,
) -> psycopg.Connection[tuple[object, ...]]:
    return psycopg.connect(
        dsn,
        autocommit=autocommit,
        connect_timeout=_CONNECT_TIMEOUT_SECONDS,
        options=f"-c statement_timeout={_STATEMENT_TIMEOUT_MS}",
    )
