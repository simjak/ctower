"""Work-owned canonical event and exact replay receipt commit."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin, WorkChangedPayload
from ctower_kernel.record.transaction import RecordTransaction
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import WorkReceipt

__all__: tuple[str, ...] = ()
ZERO_HASH = bytes(32)


def append_change(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    receipt: WorkReceipt,
    data: Mapping[str, object],
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> WorkReceipt:
    event_id, outbox_id = _uuid7(now), _uuid7(now)
    previous = connection.execute(
        """
        SELECT event_id, event_hash FROM events
        WHERE tenant_id = %s AND stream_id = %s ORDER BY sequence DESC LIMIT 1
        """,
        (actor.tenant_id, f"ticket:{receipt.ticket_id}"),
    ).fetchone()
    previous_hash = bytes(cast(bytes, previous["event_hash"])) if previous else ZERO_HASH
    causation_id = cast(UUID, previous["event_id"]) if previous else None
    event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=receipt.ticket_id,
        causation_id=causation_id,
        client_command_id=receipt.command_id,
        correlation_id=telemetry.correlation_uuid(receipt.command_id),
        event_id=event_id,
        kind=EventKind.WORK_CHANGED,
        origin=EventOrigin.API,
        payload=WorkChangedPayload(
            operation=receipt.operation,
            ticket_id=receipt.ticket_id,
            work_version=receipt.version,
            data=data,
        ),
        prev_hash=previous_hash,
        request_sha256=request_digest,
        sequence=receipt.version,
        server_time=now,
        stream_id=f"ticket:{receipt.ticket_id}",
        tenant_id=actor.tenant_id,
    )
    committed = WorkReceipt(
        command_id=receipt.command_id,
        event_ids=(event_id,),
        operation=receipt.operation,
        ticket_id=receipt.ticket_id,
        version=receipt.version,
    )
    RecordTransaction(connection).commit(
        event,
        outbox_id=outbox_id,
        response_body=committed.response_payload(),
        status_code=200,
        telemetry=telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(receipt.command_id),
            ticket_id=str(receipt.ticket_id),
        ),
        now=now,
        subjects=(("ticket", receipt.ticket_id), ("work", receipt.ticket_id)),
    )
    return committed


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
