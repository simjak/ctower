"""Bounded ordinary reconciliation of committed durability-pending commands."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import (
    DurabilityDecision,
    DurabilityFinalizationBatch,
    DurabilityState,
    RecordProblem,
)
from ctower_kernel.record._durability_sql import reconcile_durability
from ctower_kernel.telemetry import NoopTelemetry, Telemetry, TelemetryContext

__all__: tuple[str, ...] = ()
_MAX_BATCH_SIZE = 1_000
_MAX_REFUSAL_ATTEMPTS = 3
_MAX_REFUSAL_AGE = timedelta(minutes=10)
_MAX_BACKOFF_SECONDS = 60


@dataclass(frozen=True, slots=True)
class _PendingCommand:
    tenant_id: UUID
    principal_id: UUID
    command_id: UUID
    created_at: datetime


type FinalizerCursor = tuple[datetime, UUID, UUID]


def finalize_pending(
    primary_dsn: str,
    standby_dsn: str | None,
    *,
    limit: int,
    after: FinalizerCursor | None = None,
    telemetry: Telemetry | None = None,
) -> tuple[DurabilityFinalizationBatch, FinalizerCursor | None]:
    """Reconcile one bounded rotating batch through Record's existing authority."""

    if not 1 <= limit <= _MAX_BATCH_SIZE:
        raise ValueError("durability finalizer limit must be between 1 and 1000")
    scan_time = _database_now(primary_dsn)
    pending = _pending_commands(primary_dsn, limit=limit, after=after, now=scan_time)
    recorder = telemetry or NoopTelemetry()
    accepted = 0
    still_pending = 0
    refused = 0
    quarantined = 0
    for command in pending:
        outcome = _reconcile_command(
            primary_dsn,
            standby_dsn,
            command,
            now=scan_time,
            recorder=recorder,
        )
        if isinstance(outcome, RecordProblem):
            refused += 1
            quarantined += int(_record_refusal(primary_dsn, command, outcome.code, now=scan_time))
        elif outcome.state is DurabilityState.ACCEPTED:
            accepted += 1
        else:
            still_pending += 1
    batch = DurabilityFinalizationBatch(
        attempted=len(pending),
        accepted=accepted,
        pending=still_pending,
        refused=refused,
        quarantined=quarantined,
    )
    return batch, _next_cursor(pending)


def _reconcile_command(
    primary_dsn: str,
    standby_dsn: str | None,
    command: _PendingCommand,
    *,
    now: datetime,
    recorder: Telemetry,
) -> DurabilityDecision | RecordProblem:
    outcome = reconcile_durability(
        primary_dsn,
        standby_dsn,
        command.tenant_id,
        command.principal_id,
        command.command_id,
        now=now,
    )
    recorder.emit(
        "record.finalize_pending",
        _telemetry(command),
        outcome="error" if isinstance(outcome, RecordProblem) else "ok",
        reason=_reason(outcome),
    )
    return outcome


def _next_cursor(pending: tuple[_PendingCommand, ...]) -> FinalizerCursor | None:
    if not pending:
        return None
    last = pending[-1]
    return (last.created_at, last.principal_id, last.command_id)


def _pending_commands(
    dsn: str,
    *,
    limit: int,
    after: FinalizerCursor | None,
    now: datetime,
) -> tuple[_PendingCommand, ...]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        policy = connection.execute(
            "SELECT mode FROM durability_policy_state WHERE singleton"
        ).fetchone()
        if policy is None or policy["mode"] == "pending_only":
            return ()
        rows = _select_pending(connection, limit=limit, after=after, now=now)
        if not rows and after is not None:
            rows = _select_pending(connection, limit=limit, after=None, now=now)
    return tuple(
        _PendingCommand(
            cast(UUID, row["tenant_id"]),
            cast(UUID, row["principal_id"]),
            cast(UUID, row["client_command_id"]),
            cast(datetime, row["created_at"]),
        )
        for row in rows
    )


def _select_pending(
    connection: psycopg.Connection[dict[str, object]],
    *,
    limit: int,
    after: FinalizerCursor | None,
    now: datetime,
) -> list[dict[str, object]]:
    cursor_time, cursor_principal, cursor_command = (None, None, None) if after is None else after
    return connection.execute(
        """
        SELECT result.tenant_id, result.principal_id, result.client_command_id,
            result.created_at
        FROM command_results AS result
        LEFT JOIN durability_acceptance_confirmations AS confirmation
          ON confirmation.tenant_id = result.tenant_id
         AND confirmation.principal_id = result.principal_id
         AND confirmation.client_command_id = result.client_command_id
        LEFT JOIN LATERAL (
            SELECT attempt.outcome, attempt.next_attempt_at
            FROM durability_finalizer_attempts AS attempt
            WHERE attempt.tenant_id = result.tenant_id
              AND attempt.principal_id = result.principal_id
              AND attempt.client_command_id = result.client_command_id
            ORDER BY attempt.attempt_number DESC
            LIMIT 1
        ) AS refusal ON true
        WHERE confirmation.client_command_id IS NULL
          AND (
              refusal.outcome IS NULL
              OR (
                  refusal.outcome = 'retry_scheduled'
                  AND refusal.next_attempt_at <= %s::timestamptz
              )
          )
          AND (
              %s::timestamptz IS NULL
              OR (result.created_at, result.principal_id, result.client_command_id)
                 > (%s::timestamptz, %s::uuid, %s::uuid)
          )
        ORDER BY result.created_at, result.principal_id, result.client_command_id
        LIMIT %s
        """,
        (now, cursor_time, cursor_time, cursor_principal, cursor_command, limit),
    ).fetchall()


def _record_refusal(
    dsn: str,
    command: _PendingCommand,
    problem_code: str,
    *,
    now: datetime,
) -> bool:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"{command.tenant_id}:{command.principal_id}:{command.command_id}",),
        )
        result = connection.execute(
            """
            SELECT created_at
            FROM command_results
            WHERE tenant_id = %s
              AND principal_id = %s
              AND client_command_id = %s
            """,
            (command.tenant_id, command.principal_id, command.command_id),
        ).fetchone()
        if result is None:
            raise RuntimeError("selected durability command disappeared")
        previous = connection.execute(
            """
            SELECT attempt_number, outcome
            FROM durability_finalizer_attempts
            WHERE tenant_id = %s
              AND principal_id = %s
              AND client_command_id = %s
            ORDER BY attempt_number DESC
            LIMIT 1
            """,
            (command.tenant_id, command.principal_id, command.command_id),
        ).fetchone()
        if previous is not None and previous["outcome"] == "quarantined":
            return True
        attempt_number = 1 if previous is None else cast(int, previous["attempt_number"]) + 1
        created_at = cast(datetime, result["created_at"])
        quarantined = (
            attempt_number >= _MAX_REFUSAL_ATTEMPTS or now - created_at >= _MAX_REFUSAL_AGE
        )
        backoff_seconds = min(2 ** (attempt_number - 1), _MAX_BACKOFF_SECONDS)
        connection.execute(
            """
            INSERT INTO durability_finalizer_attempts (
                tenant_id, principal_id, client_command_id, attempt_number, outcome,
                problem_code, attempted_at, next_attempt_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                command.tenant_id,
                command.principal_id,
                command.command_id,
                attempt_number,
                "quarantined" if quarantined else "retry_scheduled",
                problem_code,
                now,
                None if quarantined else now + timedelta(seconds=backoff_seconds),
            ),
        )
    return quarantined


def _database_now(dsn: str) -> datetime:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        row = connection.execute("SELECT clock_timestamp() AS value").fetchone()
    if row is None:
        raise RuntimeError("database clock is unavailable")
    return cast(datetime, row["value"])


def _telemetry(command: _PendingCommand) -> TelemetryContext:
    digest = hashlib.sha256(
        command.tenant_id.bytes + command.principal_id.bytes + command.command_id.bytes
    ).hexdigest()
    return TelemetryContext(
        schema="ctower.telemetry-context/v1",
        trace_id=digest[:32],
        span_id=digest[32:48],
        trace_flags=1,
        correlation_id=str(command.command_id),
        causation_id=str(command.command_id),
        tenant_id=str(command.tenant_id),
        actor_id=str(command.principal_id),
        command_id=str(command.command_id),
    )


def _reason(outcome: DurabilityDecision | RecordProblem) -> str:
    return outcome.code if isinstance(outcome, RecordProblem) else outcome.reason
