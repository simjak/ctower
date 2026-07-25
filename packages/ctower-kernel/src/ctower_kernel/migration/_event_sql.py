"""Canonical event commits owned by the restricted Migration Module."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, PrincipalKind
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    MigrationChangedPayload,
    TicketCreatedPayload,
    WorkChangedPayload,
)
from ctower_kernel.record.transaction import RecordTransaction
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()
ZERO_HASH = bytes(32)
type ImportPayload = MigrationChangedPayload | TicketCreatedPayload | WorkChangedPayload


def commit_event(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    *,
    aggregate_id: UUID,
    command_id: UUID,
    kind: EventKind,
    payload: ImportPayload,
    request_digest: bytes,
    sequence: int,
    stream_id: str,
    now: datetime,
    telemetry: TelemetryContext,
    response: Callable[[UUID, int], dict[str, object]],
    subjects: tuple[tuple[str, UUID], ...] = (),
) -> tuple[UUID, int]:
    """Append one typed allowlisted event and its exact replay result."""

    previous = connection.execute(
        """
        SELECT event_id, event_hash FROM events
        WHERE tenant_id = %s AND stream_id = %s ORDER BY sequence DESC LIMIT 1
        """,
        (actor.tenant_id, stream_id),
    ).fetchone()
    position = _next_position(connection)
    event_id, outbox_id = _uuid7(now), _uuid7(now)
    event = _envelope(
        actor,
        aggregate_id=aggregate_id,
        command_id=command_id,
        event_id=event_id,
        kind=kind,
        payload=payload,
        previous=previous,
        request_digest=request_digest,
        sequence=sequence,
        stream_id=stream_id,
        now=now,
        telemetry=telemetry,
    )
    RecordTransaction(connection).commit(
        event,
        outbox_id=outbox_id,
        response_body=response(event_id, position),
        status_code=202,
        telemetry=telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
        ),
        now=now,
        subjects=subjects,
    )
    return event_id, position


def _envelope(
    actor: Actor,
    *,
    aggregate_id: UUID,
    command_id: UUID,
    event_id: UUID,
    kind: EventKind,
    payload: ImportPayload,
    previous: dict[str, object] | None,
    request_digest: bytes,
    sequence: int,
    stream_id: str,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=aggregate_id,
        causation_id=cast(UUID, previous["event_id"]) if previous else None,
        client_command_id=command_id,
        correlation_id=telemetry.correlation_uuid(command_id),
        event_id=event_id,
        kind=kind,
        origin=_origin(actor),
        payload=payload,
        prev_hash=bytes(cast(bytes, previous["event_hash"])) if previous else ZERO_HASH,
        request_sha256=request_digest,
        sequence=sequence,
        server_time=now,
        stream_id=stream_id,
        tenant_id=actor.tenant_id,
    )


def migration_payload(
    operation: str,
    *,
    run_id: UUID | None,
    cutover_id: UUID | None,
    target_id: str,
) -> MigrationChangedPayload:
    return MigrationChangedPayload(operation, run_id, cutover_id, "ctower", target_id)


def _next_position(connection: psycopg.Connection[dict[str, object]]) -> int:
    row = connection.execute(
        "SELECT last_position + 1 AS position FROM record_position_ledger FOR UPDATE"
    ).fetchone()
    if row is None:
        raise RuntimeError("record position ledger is unavailable")
    return int(cast(int, row["position"]))


def _origin(actor: Actor) -> EventOrigin:
    if actor.kind is PrincipalKind.MIGRATION_IMPORTER:
        return EventOrigin.MIGRATION_IMPORTER
    return EventOrigin.API


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
