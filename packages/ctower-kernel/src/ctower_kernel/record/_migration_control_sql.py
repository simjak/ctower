"""Bounded database coordination for migration and role reconciliation."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from random import SystemRandom

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

__all__ = [
    "MigrationNetworkExhaustedError",
    "migration_control",
    "reconcile_database_roles",
    "retryable_database_failure",
]

_LOGGER = logging.getLogger(__name__)
_RANDOM = SystemRandom()
_MIGRATION_CONTROL_LOCK = 712040119
_MAXIMUM_ATTEMPTS = 3
_MAXIMUM_ELAPSED_SECONDS = 20.0
_CONNECT_TIMEOUT_SECONDS = 2
_STATEMENT_TIMEOUT_MS = 5_000
_INITIAL_BACKOFF_SECONDS = 0.05
_MAXIMUM_BACKOFF_SECONDS = 0.5
_TRANSIENT_SQLSTATES = frozenset(
    {
        "53300",  # too_many_connections
        "55P03",  # lock_not_available
        "57014",  # query_canceled, including statement_timeout
        "57P01",  # admin_shutdown
        "57P02",  # crash_shutdown
        "57P03",  # cannot_connect_now
    }
)


class MigrationNetworkExhaustedError(RuntimeError):
    """A retryable migration database operation spent its finite policy."""

    def __init__(
        self,
        operation: str,
        *,
        attempt_count: int,
        elapsed_seconds: float,
        last_failure: psycopg.Error,
    ) -> None:
        self.operation = operation
        self.attempt_count = attempt_count
        self.elapsed_seconds = elapsed_seconds
        self.last_failure = last_failure
        sqlstate = last_failure.sqlstate or "unavailable"
        super().__init__(
            f"{operation} exhausted after {attempt_count} attempts in "
            f"{elapsed_seconds:.3f}s; last failure "
            f"{type(last_failure).__name__} SQLSTATE {sqlstate}"
        )


@contextmanager
def migration_control(
    admin_dsn: str,
) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    """Own the same-database session lock for one complete migration operation."""

    started = time.monotonic()
    connection: psycopg.Connection[tuple[object, ...]] | None = None
    last_failure: psycopg.Error | None = None
    for attempt in range(1, _MAXIMUM_ATTEMPTS + 1):
        try:
            connection = psycopg.connect(_bounded_dsn(admin_dsn))
            connection.execute(
                "SELECT pg_advisory_lock(%s)",
                (_MIGRATION_CONTROL_LOCK,),
            )
        except psycopg.Error as error:
            if connection is not None:
                connection.close()
                connection = None
            if not retryable_database_failure(error):
                raise
            last_failure = error
            if not _back_off(started, attempt):
                break
        else:
            break
    if connection is None:
        if last_failure is None:
            raise RuntimeError("migration control retry policy ended without a classified failure")
        raise _exhausted("migration-control-lock", started, attempt, last_failure)
    with connection:
        yield connection


def reconcile_database_roles(
    admin_dsn: str,
    operation: Callable[[str], None],
) -> None:
    """Retry one idempotent role reconciliation while its stable lock is held."""

    started = time.monotonic()
    last_failure: psycopg.Error | None = None
    bounded_dsn = _bounded_dsn(admin_dsn)
    for attempt in range(1, _MAXIMUM_ATTEMPTS + 1):
        try:
            operation(bounded_dsn)
        except psycopg.Error as error:
            if not retryable_database_failure(error):
                raise
            last_failure = error
            if not _back_off(started, attempt):
                break
        else:
            return
    if last_failure is None:
        raise RuntimeError("role reconciliation retry policy ended without a classified failure")
    raise _exhausted("role-reconciliation", started, attempt, last_failure)


def retryable_database_failure(error: psycopg.Error) -> bool:
    """Classify only connection, capacity, lock, cancellation, and shutdown as transient."""

    sqlstate = error.sqlstate
    return sqlstate is None or sqlstate.startswith("08") or sqlstate in _TRANSIENT_SQLSTATES


def _bounded_dsn(dsn: str) -> str:
    parameters = conninfo_to_dict(dsn)
    existing_options = parameters.get("options", "")
    timeout_option = f"-c statement_timeout={_STATEMENT_TIMEOUT_MS}"
    options = f"{existing_options} {timeout_option}".strip()
    return make_conninfo(
        dsn,
        connect_timeout=str(_CONNECT_TIMEOUT_SECONDS),
        options=options,
    )


def _back_off(started: float, attempt: int) -> bool:
    if attempt >= _MAXIMUM_ATTEMPTS:
        return False
    remaining = _MAXIMUM_ELAPSED_SECONDS - (time.monotonic() - started)
    if remaining <= 0:
        return False
    ceiling = min(
        _INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)),
        _MAXIMUM_BACKOFF_SECONDS,
        remaining,
    )
    time.sleep(_RANDOM.uniform(ceiling / 2, ceiling))
    return time.monotonic() - started < _MAXIMUM_ELAPSED_SECONDS


def _exhausted(
    operation: str,
    started: float,
    attempt_count: int,
    last_failure: psycopg.Error,
) -> MigrationNetworkExhaustedError:
    elapsed = time.monotonic() - started
    exhausted = MigrationNetworkExhaustedError(
        operation,
        attempt_count=attempt_count,
        elapsed_seconds=elapsed,
        last_failure=last_failure,
    )
    _LOGGER.error(
        "migration database retry policy exhausted",
        extra={
            "operation": operation,
            "attempt_count": attempt_count,
            "elapsed_seconds": elapsed,
            "last_failure_type": type(last_failure).__name__,
            "last_sqlstate": last_failure.sqlstate,
        },
    )
    return exhausted
