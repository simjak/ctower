"""Board-context-owned authenticated label application and exact replay."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.board_context.labels import ApplyLabelCommand, ApplyLabelResult
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.context_set_events import LabelAppliedPayload
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()


def apply_label(
    dsn: str,
    actor: Actor,
    command: ApplyLabelCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> ApplyLabelResult | RecordProblem:
    """Reserve before lookup, pin the active vocabulary revision, and append one fact."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        existing = transaction.reserve_ticket_mutation(
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            (command.ticket_id,),
            now=now,
        )
        if isinstance(existing, RecordProblem):
            return existing
        if existing is not None:
            return _result_from_payload(existing)
        pending = transaction.require_durable_subjects(
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            (("ticket", command.ticket_id),),
            now=now,
        )
        if pending is not None:
            return pending
        problem = _refusal(connection, transaction, actor, command, request_digest, now)
        if problem is not None:
            return problem
        active = _active_revision(connection, actor, command.label_key)
        if active is None:
            raise RuntimeError("active label vocabulary revision disappeared after refusal check")
        return _append(
            connection,
            actor,
            command,
            active,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _refusal(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: ApplyLabelCommand,
    request_digest: bytes,
    now: datetime,
) -> RecordProblem | None:
    problem: RecordProblem | None = None
    ticket = connection.execute(
        "SELECT version FROM tickets WHERE tenant_id = %s AND ticket_id = %s FOR UPDATE",
        (actor.tenant_id, command.ticket_id),
    ).fetchone()
    if ticket is None:
        problem = RecordProblem(
            code="tenant-scope-denied",
            detail="Ticket unavailable",
            status=404,
            title="Ticket unavailable",
            command_id=command.client_command_id,
        )
    elif _active_revision(connection, actor, command.label_key) is None:
        problem = RecordProblem(
            code="label-key-unrecognized",
            detail="This label key is absent from the active label vocabulary revision.",
            status=422,
            title="Label key unrecognized",
            command_id=command.client_command_id,
        )
    elif _already_applied(connection, actor, command):
        problem = RecordProblem(
            code="label-already-applied",
            detail="This label is already applied to the ticket.",
            status=409,
            title="Label already applied",
            command_id=command.client_command_id,
        )
    if problem is not None:
        transaction.refuse(
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            problem,
            now=now,
        )
    return problem


def _active_revision(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    label_key: str,
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT revision.label_vocabulary_revision_id, revision.catalog_key,
            revision.catalog_revision, revision.catalog_digest
        FROM company_bundle_active AS active
        JOIN company_bundle_members AS member
          ON member.bundle_revision_id = active.bundle_revision_id
         AND member.tenant_id = active.tenant_id
        JOIN label_vocabulary_revisions AS revision
          ON revision.label_vocabulary_revision_id = member.component_revision_id
         AND revision.tenant_id = member.tenant_id
        JOIN label_vocabulary_members AS vmember
          ON vmember.label_vocabulary_revision_id = revision.label_vocabulary_revision_id
         AND vmember.tenant_id = revision.tenant_id
         AND vmember.label_key = %s
        WHERE active.tenant_id = %s
        """,
        (label_key, actor.tenant_id),
    ).fetchone()


def _already_applied(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: ApplyLabelCommand,
) -> bool:
    row = connection.execute(
        """
        SELECT 1 FROM ticket_applied_labels
        WHERE tenant_id = %s AND ticket_id = %s AND label_key = %s
        """,
        (actor.tenant_id, command.ticket_id, command.label_key),
    ).fetchone()
    return row is not None


def _append(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: ApplyLabelCommand,
    active: dict[str, object],
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> ApplyLabelResult:
    next_sequence = _next_ticket_sequence(connection, actor, command.ticket_id)
    previous = _previous_event(connection, actor, command.ticket_id)
    ticket_label_id, event_id, outbox_id = (_uuid7(now) for _ in range(3))
    catalog_digest = f"sha256:{bytes(cast(bytes, active['catalog_digest'])).hex()}"
    result = ApplyLabelResult(
        command_id=command.client_command_id,
        ticket_label_id=ticket_label_id,
        event_id=event_id,
        ticket_id=command.ticket_id,
        label_key=command.label_key,
    )
    connection.execute(
        "UPDATE tickets SET version = %s WHERE tenant_id = %s AND ticket_id = %s",
        (next_sequence, actor.tenant_id, command.ticket_id),
    )
    event = EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=command.ticket_id,
        causation_id=cast(UUID, previous["event_id"]),
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=event_id,
        kind=EventKind.LABEL_APPLIED,
        origin=EventOrigin.API,
        payload=LabelAppliedPayload(
            ticket_label_id=ticket_label_id,
            ticket_id=command.ticket_id,
            label_key=command.label_key,
            catalog_key=str(active["catalog_key"]),
            catalog_revision=int(cast(int, active["catalog_revision"])),
            catalog_digest=catalog_digest,
        ),
        prev_hash=bytes(cast(bytes, previous["event_hash"])),
        request_sha256=request_digest,
        sequence=next_sequence,
        server_time=now,
        stream_id=f"ticket:{command.ticket_id}",
        tenant_id=actor.tenant_id,
    )
    RecordTransaction(connection).commit(
        event,
        outbox_id=outbox_id,
        response_body=result.response_payload(),
        status_code=200,
        telemetry=telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command.client_command_id),
            ticket_id=str(command.ticket_id),
        ),
        now=now,
        subjects=(("ticket", command.ticket_id),),
    )
    _insert_applied_label(connection, actor, command, active, ticket_label_id, event_id, now)
    return result


def _next_ticket_sequence(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, ticket_id: UUID
) -> int:
    ticket_version = cast(
        dict[str, object],
        connection.execute(
            "SELECT version FROM tickets WHERE tenant_id = %s AND ticket_id = %s",
            (actor.tenant_id, ticket_id),
        ).fetchone(),
    )
    return int(cast(int, ticket_version["version"])) + 1


def _previous_event(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, ticket_id: UUID
) -> dict[str, object]:
    previous = connection.execute(
        """
        SELECT event_id, event_hash FROM events
        WHERE tenant_id = %s AND stream_id = %s
        ORDER BY sequence DESC LIMIT 1
        """,
        (actor.tenant_id, f"ticket:{ticket_id}"),
    ).fetchone()
    if previous is None:
        raise RuntimeError("locked ticket event stream is inconsistent")
    return previous


def _insert_applied_label(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: ApplyLabelCommand,
    active: dict[str, object],
    ticket_label_id: UUID,
    event_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO ticket_applied_labels (
            ticket_label_id, tenant_id, ticket_id, label_key, label_vocabulary_revision_id,
            event_id, actor_principal_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            ticket_label_id,
            actor.tenant_id,
            command.ticket_id,
            command.label_key,
            active["label_vocabulary_revision_id"],
            event_id,
            actor.principal_id,
            now,
        ),
    )


def _result_from_payload(payload: dict[str, object]) -> ApplyLabelResult:
    return ApplyLabelResult(
        command_id=UUID(str(payload["command_id"])),
        ticket_label_id=UUID(str(payload["ticket_label_id"])),
        event_id=UUID(str(payload["event_id"])),
        ticket_id=UUID(str(payload["ticket_id"])),
        label_key=str(payload["label_key"]),
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
