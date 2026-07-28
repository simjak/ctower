"""Bounded ordinary reconciliation of committed durability-pending commands."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
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


@dataclass(frozen=True, slots=True)
class _PendingCommand:
    tenant_id: UUID
    principal_id: UUID
    command_id: UUID


def finalize_pending(
    primary_dsn: str,
    standby_dsn: str | None,
    *,
    limit: int,
    telemetry: Telemetry | None = None,
) -> DurabilityFinalizationBatch:
    """Reconcile one bounded oldest-first batch through Record's existing authority."""

    if not 1 <= limit <= _MAX_BATCH_SIZE:
        raise ValueError("durability finalizer limit must be between 1 and 1000")
    pending = _pending_commands(primary_dsn, limit=limit)
    recorder = telemetry or NoopTelemetry()
    accepted = 0
    still_pending = 0
    refused = 0
    for command in pending:
        outcome = reconcile_durability(
            primary_dsn,
            standby_dsn,
            command.tenant_id,
            command.principal_id,
            command.command_id,
            now=_database_now(primary_dsn),
        )
        recorder.emit(
            "record.finalize_pending",
            _telemetry(command),
            outcome="error" if isinstance(outcome, RecordProblem) else "ok",
            reason=_reason(outcome),
        )
        if isinstance(outcome, RecordProblem):
            refused += 1
        elif outcome.state is DurabilityState.ACCEPTED:
            accepted += 1
        else:
            still_pending += 1
    return DurabilityFinalizationBatch(
        attempted=len(pending),
        accepted=accepted,
        pending=still_pending,
        refused=refused,
    )


def _pending_commands(dsn: str, *, limit: int) -> tuple[_PendingCommand, ...]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        policy = connection.execute(
            "SELECT mode FROM durability_policy_state WHERE singleton"
        ).fetchone()
        if policy is None or policy["mode"] == "pending_only":
            return ()
        rows = connection.execute(
            """
            SELECT result.tenant_id, result.principal_id, result.client_command_id
            FROM command_results AS result
            LEFT JOIN durability_acceptance_confirmations AS confirmation
              ON confirmation.tenant_id = result.tenant_id
             AND confirmation.principal_id = result.principal_id
             AND confirmation.client_command_id = result.client_command_id
            WHERE confirmation.client_command_id IS NULL
            ORDER BY result.created_at, result.principal_id, result.client_command_id
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return tuple(
        _PendingCommand(row["tenant_id"], row["principal_id"], row["client_command_id"])
        for row in rows
    )


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
