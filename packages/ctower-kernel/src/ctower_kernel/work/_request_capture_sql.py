"""Atomic native Request capture and accepted-only PostgreSQL reads."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import (
    EventEnvelope,
    EventKind,
    EventOrigin,
    InboundEventRecordedPayload,
)
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.request_events import RequestChangedPayload
from ctower_kernel.record.transaction import (
    EventCommit,
    RecordTransaction,
    authority_connection,
    project_scope_refusal,
)
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work._request_cutover_guard import request_mutation_epoch_refusal
from ctower_kernel.work._request_types import (
    RequestCapture,
    RequestCaptureResult,
)

__all__ = ["capture_request"]

_ZERO_HASH = bytes(32)


@dataclass(frozen=True, slots=True)
class _CaptureIdentity:
    request_id: UUID
    thread_id: UUID
    inbound_event_id: UUID
    event_id: UUID
    request_event_id: UUID
    source_kind: str
    source_ref: str


def capture_request(
    dsn: str,
    actor: Actor,
    command: RequestCapture,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestCaptureResult | RecordProblem:
    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        epoch = request_mutation_epoch_refusal(
            connection,
            actor.tenant_id,
            command.client_command_id,
        )
        if epoch is not None:
            return epoch
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return replay if isinstance(replay, RecordProblem) else _capture_result(replay)
        return _capture_reserved(
            connection,
            transaction,
            actor,
            command,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _capture_reserved(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: RequestCapture,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestCaptureResult | RecordProblem:
    epoch = request_mutation_epoch_refusal(connection, actor.tenant_id, command.client_command_id)
    if epoch is not None:
        return _refuse(transaction, actor, command, request_digest, epoch, now)
    refusal = _capture_scope_refusal(connection, actor, command)
    if refusal is not None:
        return _refuse(transaction, actor, command, request_digest, refusal, now)
    owner_id = _initial_owner(connection, actor, command.project_key)
    commander_id = _project_commander(connection, actor, command.project_key)
    identity = _capture_identity(actor, command, now)
    subjects = (
        ("inbound_thread", identity.thread_id),
        ("inbound_event", identity.inbound_event_id),
        ("request", identity.request_id),
    )
    durable = transaction.require_durable_subjects(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        subjects,
        now=now,
    )
    if durable is not None:
        return durable
    result = _persist_capture(
        connection,
        actor,
        command,
        identity,
        owner_id=owner_id,
        commander_id=commander_id,
        now=now,
    )
    transaction.commit_batch(
        _capture_commits(
            actor,
            command,
            result,
            identity,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        ),
        response_body=result.response_payload(),
        status_code=201,
        telemetry=telemetry,
        now=now,
        subjects=subjects,
    )
    return result


def _capture_scope_refusal(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, command: RequestCapture
) -> RecordProblem | None:
    scope = project_scope_refusal(
        connection,
        tenant_id=actor.tenant_id,
        principal_id=actor.principal_id,
        project_keys=(command.project_key,),
        command_id=command.client_command_id,
    )
    if scope is not None:
        return scope
    if _project_exists(connection, actor.tenant_id, command.project_key):
        return None
    return RecordProblem(
        code="request-project-unavailable",
        detail="The target Project is not present in the active tenant hierarchy.",
        status=404,
        title="Request Project unavailable",
        command_id=command.client_command_id,
    )


def _capture_identity(actor: Actor, command: RequestCapture, now: datetime) -> _CaptureIdentity:
    request_id, thread_id, inbound_event_id = (uuid7(now) for _ in range(3))
    return _CaptureIdentity(
        request_id,
        thread_id,
        inbound_event_id,
        uuid7(now),
        uuid7(now),
        "native",
        f"{actor.principal_id}:{command.client_command_id}",
    )


def _persist_capture(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCapture,
    identity: _CaptureIdentity,
    *,
    owner_id: UUID,
    commander_id: UUID,
    now: datetime,
) -> RequestCaptureResult:
    request_number = _allocate_number(connection, actor.tenant_id, now)
    content_digest = hashlib.sha256(command.text.encode()).digest()
    _insert_provenance(connection, actor, command, identity, content_digest=content_digest, now=now)
    _insert_request(
        connection,
        actor,
        command,
        identity,
        request_number=request_number,
        content_digest=content_digest,
        now=now,
    )
    _insert_initial_facts(
        connection,
        actor,
        command,
        identity.request_id,
        owner_id=owner_id,
        commander_id=commander_id,
        now=now,
    )
    return RequestCaptureResult(
        command.client_command_id,
        (identity.event_id, identity.request_event_id),
        identity.inbound_event_id,
        identity.request_id,
        request_number,
        command.project_key,
        actor.principal_id,
        owner_id,
    )


def _insert_provenance(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCapture,
    identity: _CaptureIdentity,
    *,
    content_digest: bytes,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO inbound_threads (
            thread_id, tenant_id, project_key, version, created_by, created_at
        ) VALUES (%s, %s, %s, 1, %s, %s)
        """,
        (identity.thread_id, actor.tenant_id, command.project_key, actor.principal_id, now),
    )
    connection.execute(
        """
        INSERT INTO inbound_events (
            inbound_event_id, tenant_id, thread_id, position, source_kind, source_ref,
            content, content_digest, taint, initial_intent, initial_outcome,
            recorded_by, recorded_at
        ) VALUES (%s, %s, %s, 1, %s, %s, %s, %s, 'authenticated',
                  'create_request', 'request_created', %s, %s)
        """,
        (
            identity.inbound_event_id,
            actor.tenant_id,
            identity.thread_id,
            identity.source_kind,
            identity.source_ref,
            command.text,
            content_digest,
            actor.principal_id,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO inbound_source_aliases (
            tenant_id, source_kind, source_ref, inbound_event_id, thread_id,
            project_key, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            actor.tenant_id,
            identity.source_kind,
            identity.source_ref,
            identity.inbound_event_id,
            identity.thread_id,
            command.project_key,
            now,
        ),
    )


def _insert_request(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCapture,
    identity: _CaptureIdentity,
    *,
    request_number: int,
    content_digest: bytes,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO requests (
            request_id, tenant_id, request_number, project_key, content, content_digest,
            source_kind, source_ref, inbound_event_id, submitted_by, capture_command_id,
            version, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)
        """,
        (
            identity.request_id,
            actor.tenant_id,
            request_number,
            command.project_key,
            command.text,
            content_digest,
            identity.source_kind,
            identity.source_ref,
            identity.inbound_event_id,
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )


def _insert_initial_facts(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestCapture,
    request_id: UUID,
    *,
    owner_id: UUID,
    commander_id: UUID,
    now: datetime,
) -> None:
    common = (request_id, actor.tenant_id, actor.principal_id, command.client_command_id, now)
    connection.execute(
        """
        INSERT INTO request_owner_facts (
            request_id, tenant_id, sequence, owner_id, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, 1, %s, 'initial accountable owner', %s, %s, %s)
        """,
        (request_id, actor.tenant_id, owner_id, actor.principal_id, command.client_command_id, now),
    )
    connection.execute(
        """
        INSERT INTO request_priority_facts (
            request_id, tenant_id, sequence, priority, is_default, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, 1, 'P2', true, 'capture safety default', %s, %s, %s)
        """,
        common,
    )
    connection.execute(
        """
        INSERT INTO request_triage_facts (
            request_id, tenant_id, sequence, disposition, reason, canonical_request_id,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, 1, 'UNTRIAGED', NULL, NULL, %s, %s, %s)
        """,
        common,
    )
    connection.execute(
        """
        INSERT INTO request_attention_facts (
            attention_id, request_id, tenant_id, kind, active, owner_id, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, %s, 'request_triage_required', true, %s,
                  'Commander disposition is required', %s, %s, %s)
        """,
        (
            uuid7(now),
            request_id,
            actor.tenant_id,
            commander_id,
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )


def _capture_commits(
    actor: Actor,
    command: RequestCapture,
    result: RequestCaptureResult,
    identity: _CaptureIdentity,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[EventCommit, ...]:
    return (
        EventCommit(
            _inbound_event(
                actor,
                command,
                result,
                identity,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            ),
            uuid7(now),
        ),
        EventCommit(
            _request_event(
                actor,
                command,
                result,
                identity,
                request_digest=request_digest,
                now=now,
                telemetry=telemetry,
            ),
            uuid7(now),
        ),
    )


def _inbound_event(
    actor: Actor,
    command: RequestCapture,
    result: RequestCaptureResult,
    identity: _CaptureIdentity,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=identity.thread_id,
        causation_id=None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=identity.event_id,
        kind=EventKind.INBOUND_EVENT_RECORDED,
        origin=EventOrigin.API,
        payload=InboundEventRecordedPayload(
            inbound_event_id=result.inbound_event_id,
            source_kind=identity.source_kind,
            source_ref=identity.source_ref,
            project_key=command.project_key,
            position=1,
            intent="create_request",
            taint="authenticated",
            outcome="request_created",
            content_digest=f"sha256:{hashlib.sha256(command.text.encode()).hexdigest()}",
            ticket_id=None,
            request_id=result.request_id,
        ),
        prev_hash=_ZERO_HASH,
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"inbound-thread:{identity.thread_id}",
        tenant_id=actor.tenant_id,
    )


def _request_event(
    actor: Actor,
    command: RequestCapture,
    result: RequestCaptureResult,
    identity: _CaptureIdentity,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=result.request_id,
        causation_id=result.inbound_event_id,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=identity.request_event_id,
        kind=EventKind.REQUEST_CHANGED,
        origin=EventOrigin.API,
        payload=RequestChangedPayload(
            operation="capture",
            request_id=result.request_id,
            request_number=result.request_number,
            project_key=command.project_key,
            version=1,
            content=command.text,
            content_digest=f"sha256:{hashlib.sha256(command.text.encode()).hexdigest()}",
            source_kind=identity.source_kind,
            source_ref=identity.source_ref,
            submitted_by=actor.principal_id,
            owner_id=result.owner_id,
            triage="UNTRIAGED",
            priority="P2",
            priority_default=True,
            required_ticket_ids=(),
            optional_ticket_ids=(),
            blockers=(),
            closure_outcome="open",
        ),
        prev_hash=_ZERO_HASH,
        request_sha256=request_digest,
        sequence=1,
        server_time=now,
        stream_id=f"request:{result.request_id}",
        tenant_id=actor.tenant_id,
    )


def _project_exists(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, project_key: str
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM (
                SELECT project_key FROM project_delivery_checkpoint_definitions
                WHERE tenant_id = %s
                UNION
                SELECT project_key FROM project_seats WHERE tenant_id = %s
            ) AS project
            WHERE project_key = %s LIMIT 1
            """,
            (tenant_id, tenant_id, project_key),
        ).fetchone()
        is not None
    )


def _initial_owner(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, project_key: str
) -> UUID:
    addressable = connection.execute(
        """
        SELECT principal_id FROM project_seats
        WHERE tenant_id = %s AND project_key = %s AND principal_id = %s
        UNION ALL
        SELECT binding.principal_id
        FROM human_role_bindings AS binding
        LEFT JOIN human_role_binding_revocations AS revocation
          ON revocation.binding_id = binding.binding_id
         AND revocation.tenant_id = binding.tenant_id
        WHERE binding.tenant_id = %s AND binding.principal_id = %s
          AND %s = ANY(binding.project_keys) AND revocation.binding_id IS NULL
        LIMIT 1
        """,
        (
            actor.tenant_id,
            project_key,
            actor.principal_id,
            actor.tenant_id,
            actor.principal_id,
            project_key,
        ),
    ).fetchone()
    if addressable is not None:
        return actor.principal_id
    return _project_commander(connection, actor, project_key)


def _project_commander(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, project_key: str
) -> UUID:
    commander = connection.execute(
        """
        SELECT principal.principal_id
        FROM project_seats AS seat
        JOIN principals AS principal
          ON principal.tenant_id = seat.tenant_id AND principal.principal_id = seat.principal_id
        WHERE seat.tenant_id = %s AND seat.project_key = %s
          AND principal.kind = 'commander' AND NOT principal.disabled
        ORDER BY principal.created_at, principal.principal_id LIMIT 1
        """,
        (actor.tenant_id, project_key),
    ).fetchone()
    if commander is None:
        raise RuntimeError("Request project has no eligible Commander")
    return cast(UUID, commander["principal_id"])


def _allocate_number(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, now: datetime
) -> int:
    row = connection.execute(
        """
        INSERT INTO request_number_allocators (tenant_id, last_number, advanced_at)
        VALUES (%s, 1, %s)
        ON CONFLICT (tenant_id) DO UPDATE
        SET last_number = request_number_allocators.last_number + 1,
            advanced_at = EXCLUDED.advanced_at
        RETURNING last_number
        """,
        (tenant_id, now),
    ).fetchone()
    if row is None:
        raise RuntimeError("Request number allocator returned no authority row")
    return int(cast(int, row["last_number"]))


def _capture_result(payload: dict[str, object]) -> RequestCaptureResult:
    return RequestCaptureResult(
        command_id=UUID(str(payload["command_id"])),
        event_ids=tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        inbound_event_id=UUID(str(payload["inbound_event_id"])),
        request_id=UUID(str(payload["request_id"])),
        request_number=int(cast(int, payload["request_number"])),
        project_key=str(payload["project_key"]),
        submitted_by=UUID(str(payload["submitted_by"])),
        owner_id=UUID(str(payload["owner_id"])),
        version=int(cast(int, payload["version"])),
    )


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command: RequestCapture,
    request_digest: bytes,
    problem: RecordProblem,
    now: datetime,
) -> RecordProblem:
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem
