"""Workflow-owned canonical event and command-result persistence."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    WorkflowChangedPayload,
)
from ctower_kernel.record.transaction import RecordTransaction
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.workflow import WorkflowActor, WorkflowReceipt

__all__: tuple[str, ...] = ()
ZERO_HASH = bytes(32)


def append_change(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    command_id: UUID,
    receipt: WorkflowReceipt,
    *,
    operation: str,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> WorkflowReceipt:
    """Commit one typed Workflow event, exact result, and outbox row."""

    event_id, outbox_id = _uuid7(now), _uuid7(now)
    event = _workflow_event(
        connection,
        actor,
        command_id,
        receipt,
        operation=operation,
        event_id=event_id,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    committed = _with_event(receipt, event_id)
    RecordTransaction(connection).commit(
        event,
        outbox_id=outbox_id,
        response_body=committed.response_payload(),
        status_code=200,
        telemetry=telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
            ticket_id=str(receipt.ticket_id),
        ),
        now=now,
    )
    return committed


def _workflow_event(
    connection: psycopg.Connection[dict[str, object]],
    actor: WorkflowActor,
    command_id: UUID,
    receipt: WorkflowReceipt,
    *,
    operation: str,
    event_id: UUID,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventEnvelope:
    sequence, previous = _next_event(connection, receipt.workflow_run_id)
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=receipt.workflow_run_id,
        causation_id=None,
        client_command_id=command_id,
        correlation_id=telemetry.correlation_uuid(command_id),
        event_id=event_id,
        kind=EventKind.WORKFLOW_CHANGED,
        origin=EventOrigin.API,
        payload=WorkflowChangedPayload(
            operation=operation,
            ticket_id=receipt.ticket_id,
            workflow_ref=receipt.workflow_ref,
            workflow_version=receipt.version,
            stage=receipt.stage,
            lifecycle_facts=receipt.lifecycle_facts,
        ),
        prev_hash=previous,
        request_sha256=request_digest,
        sequence=sequence,
        server_time=now,
        stream_id=f"workflow:{receipt.workflow_run_id}",
        tenant_id=actor.tenant_id,
    )


def _next_event(
    connection: psycopg.Connection[dict[str, object]], run_id: UUID
) -> tuple[int, bytes]:
    row = connection.execute(
        """
        SELECT sequence, event_hash FROM events
        WHERE stream_id = %s ORDER BY sequence DESC LIMIT 1
        """,
        (f"workflow:{run_id}",),
    ).fetchone()
    if row is None:
        return 1, ZERO_HASH
    return int(cast(int, row["sequence"])) + 1, bytes(cast(bytes, row["event_hash"]))


def _with_event(receipt: WorkflowReceipt, event_id: UUID) -> WorkflowReceipt:
    return WorkflowReceipt(
        command_id=receipt.command_id,
        event_ids=(event_id,),
        workflow_run_id=receipt.workflow_run_id,
        ticket_id=receipt.ticket_id,
        workflow_ref=receipt.workflow_ref,
        stage=receipt.stage,
        activity_class=receipt.activity_class,
        version=receipt.version,
        lifecycle_facts=receipt.lifecycle_facts,
    )


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
