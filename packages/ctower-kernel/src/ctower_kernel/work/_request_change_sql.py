"""Atomic Request change orchestration and authority enforcement."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.record.request_events import RequestChangedPayload
from ctower_kernel.record.transaction import (
    RecordTransaction,
    authority_connection,
    project_scope_refusal,
)
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work._request_cutover_guard import request_mutation_epoch_refusal
from ctower_kernel.work._request_facts_sql import append_fact, current_owner, request_problem
from ctower_kernel.work._request_state_sql import (
    active_blocker_keys,
    active_relations,
    derived_state,
    latest_triage,
)
from ctower_kernel.work._request_types import (
    RequestBlocker,
    RequestChange,
    RequestChangeResult,
    RequestOwner,
    RequestPriority,
    RequestTicketRelation,
    RequestTriage,
)

__all__ = ["change_request"]


def change_request(
    dsn: str,
    actor: Actor,
    command: RequestChange,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestChangeResult | RecordProblem:
    """Reserve, authorize, append, and event one exact Request command."""

    with authority_connection(dsn) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        replay = transaction.reserve(actor.principal_id, command.client_command_id, request_digest)
        if replay is not None:
            return replay if isinstance(replay, RecordProblem) else _result(replay)
        return _change_reserved(
            connection,
            transaction,
            actor,
            command,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _change_reserved(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: RequestChange,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> RequestChangeResult | RecordProblem:
    authorized = _authorized_request(
        connection, transaction, actor, command, request_digest=request_digest, now=now
    )
    if isinstance(authorized, RecordProblem):
        return authorized
    request, current_version = authorized
    semantic = append_fact(connection, actor, command, request, now=now)
    if semantic is not None:
        return _refuse(transaction, actor, command, request_digest, semantic, now)
    receipt, event = _committed_change(
        connection,
        actor,
        command,
        request,
        current_version=current_version,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    transaction.commit(
        event,
        outbox_id=uuid7(now),
        response_body=receipt.response_payload(),
        status_code=200,
        telemetry=telemetry,
        now=now,
        subjects=_subjects(command),
    )
    return receipt


def _authorized_request(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: RequestChange,
    *,
    request_digest: bytes,
    now: datetime,
) -> tuple[dict[str, object], int] | RecordProblem:
    locked = _lock_in_mutation_epoch(
        connection,
        transaction,
        actor,
        command,
        request_digest=request_digest,
        now=now,
    )
    if isinstance(locked, RecordProblem):
        return locked
    request = locked
    project_key = str(request["project_key"])
    scope = project_scope_refusal(
        connection,
        tenant_id=actor.tenant_id,
        principal_id=actor.principal_id,
        project_keys=(project_key,),
        command_id=command.client_command_id,
    )
    if scope is not None:
        return _refuse(transaction, actor, command, request_digest, scope, now)
    pending = transaction.require_durable_subjects(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        _subjects(command),
        now=now,
    )
    if pending is not None:
        return pending
    current_version = int(cast(int, request["version"]))
    if command.expected_version != current_version:
        problem = request_problem(
            command,
            "version-conflict",
            409,
            "Request version is stale",
            current_version=current_version,
        )
        return _refuse(transaction, actor, command, request_digest, problem, now)
    authority = _authority_refusal(connection, actor, command, project_key)
    if authority is not None:
        return _refuse(transaction, actor, command, request_digest, authority, now)
    return request, current_version


def _lock_in_mutation_epoch(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: RequestChange,
    *,
    request_digest: bytes,
    now: datetime,
) -> dict[str, object] | RecordProblem:
    epoch = request_mutation_epoch_refusal(
        connection,
        actor.tenant_id,
        command.client_command_id,
    )
    if epoch is not None:
        return _refuse(transaction, actor, command, request_digest, epoch, now)
    request = _lock_request(connection, actor.tenant_id, command.request_id)
    if request is not None:
        return request
    problem = request_problem(command, "tenant-scope-denied", 404, "Request not found")
    return _refuse(transaction, actor, command, request_digest, problem, now)


def _committed_change(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestChange,
    request: dict[str, object],
    *,
    current_version: int,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> tuple[RequestChangeResult, EventEnvelope]:
    next_version = current_version + 1
    connection.execute(
        "UPDATE requests SET version = %s WHERE tenant_id = %s AND request_id = %s",
        (next_version, actor.tenant_id, command.request_id),
    )
    event_id = uuid7(now)
    receipt = RequestChangeResult(
        command.client_command_id,
        (event_id,),
        _operation(command),
        command.request_id,
        int(cast(int, request["request_number"])),
        next_version,
        derived_state(connection, actor.tenant_id, command.request_id),
    )
    event = _event(
        connection,
        actor,
        command,
        request,
        receipt,
        event_id=event_id,
        request_digest=request_digest,
        now=now,
        telemetry=telemetry,
    )
    return receipt, event


def _lock_request(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT request_id, request_number, project_key, content, content_digest,
               source_kind, source_ref, submitted_by, version
        FROM requests WHERE tenant_id = %s AND request_id = %s FOR UPDATE
        """,
        (tenant_id, request_id),
    ).fetchone()


def _subjects(command: RequestChange) -> tuple[tuple[str, UUID], ...]:
    if isinstance(command, RequestTicketRelation):
        return (("request", command.request_id), ("ticket", command.ticket_id))
    return (("request", command.request_id),)


def _authority_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestChange,
    project_key: str,
) -> RecordProblem | None:
    operator = actor.kind is PrincipalKind.OPERATOR
    exact_commander = _is_exact_commander(connection, actor, project_key)
    human_commander = _is_human_commander(connection, actor, project_key)
    owns_request = (
        current_owner(connection, actor.tenant_id, command.request_id) == actor.principal_id
    )
    allowed, code = _authority_decision(
        command,
        operator=operator,
        exact_commander=exact_commander,
        human_commander=human_commander,
        owns_request=owns_request,
    )
    if allowed:
        return None
    return request_problem(command, code, 403, "Request command authority is not granted")


def _authority_decision(
    command: RequestChange,
    *,
    operator: bool,
    exact_commander: bool,
    human_commander: bool,
    owns_request: bool,
) -> tuple[bool, str]:
    commander = exact_commander or human_commander
    if isinstance(command, RequestTriage):
        return commander, "request-triage-forbidden"
    if isinstance(command, RequestPriority):
        return operator or commander, "request-transition-forbidden"
    if isinstance(command, RequestOwner):
        return operator or human_commander, "request-owner-forbidden"
    return operator or commander or owns_request, "request-transition-forbidden"


def _is_exact_commander(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, project_key: str
) -> bool:
    if actor.kind is not PrincipalKind.COMMANDER:
        return False
    return (
        connection.execute(
            """
            SELECT 1 FROM project_seats
            WHERE tenant_id = %s AND principal_id = %s AND project_key = %s
              AND seat_key = %s
            """,
            (actor.tenant_id, actor.principal_id, project_key, f"{project_key}-commander"),
        ).fetchone()
        is not None
    )


def _is_human_commander(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, project_key: str
) -> bool:
    if actor.kind is not PrincipalKind.COMMANDER:
        return False
    return (
        connection.execute(
            """
            SELECT 1
            FROM human_role_bindings AS binding
            LEFT JOIN human_role_binding_revocations AS revocation
              ON revocation.binding_id = binding.binding_id
             AND revocation.tenant_id = binding.tenant_id
            WHERE binding.tenant_id = %s AND binding.principal_id = %s
              AND binding.role = 'commander' AND %s = ANY(binding.project_keys)
              AND revocation.binding_id IS NULL
            """,
            (actor.tenant_id, actor.principal_id, project_key),
        ).fetchone()
        is not None
    )


def _event(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestChange,
    request: dict[str, object],
    receipt: RequestChangeResult,
    *,
    event_id: UUID,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> EventEnvelope:
    previous = connection.execute(
        """
        SELECT event_id, event_hash FROM events
        WHERE tenant_id = %s AND stream_id = %s ORDER BY sequence DESC LIMIT 1
        """,
        (actor.tenant_id, f"request:{command.request_id}"),
    ).fetchone()
    snapshot = _snapshot(connection, actor.tenant_id, command.request_id)
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=command.request_id,
        causation_id=cast(UUID, previous["event_id"]) if previous is not None else None,
        client_command_id=command.client_command_id,
        correlation_id=telemetry.correlation_uuid(command.client_command_id),
        event_id=event_id,
        kind=EventKind.REQUEST_CHANGED,
        origin=EventOrigin.API,
        payload=RequestChangedPayload(
            operation=receipt.operation,
            request_id=command.request_id,
            request_number=receipt.request_number,
            project_key=str(request["project_key"]),
            version=receipt.version,
            content=str(request["content"]),
            content_digest=f"sha256:{bytes(cast(bytes, request['content_digest'])).hex()}",
            source_kind=str(request["source_kind"]),
            source_ref=str(request["source_ref"]),
            submitted_by=cast(UUID, request["submitted_by"]),
            owner_id=cast(UUID, snapshot["owner_id"]),
            triage=str(snapshot["triage"]),
            priority=str(snapshot["priority"]),
            priority_default=bool(snapshot["priority_default"]),
            required_ticket_ids=cast(tuple[UUID, ...], snapshot["required"]),
            optional_ticket_ids=cast(tuple[UUID, ...], snapshot["optional"]),
            blockers=cast(tuple[str, ...], snapshot["blockers"]),
            closure_outcome="done" if receipt.state == "DONE" else "open",
        ),
        prev_hash=bytes(cast(bytes, previous["event_hash"])) if previous is not None else bytes(32),
        request_sha256=request_digest,
        sequence=receipt.version,
        server_time=now,
        stream_id=f"request:{command.request_id}",
        tenant_id=actor.tenant_id,
    )


def _snapshot(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> dict[str, object]:
    owner = connection.execute(
        """SELECT owner_id FROM request_owner_facts
           WHERE tenant_id = %s AND request_id = %s ORDER BY sequence DESC LIMIT 1""",
        (tenant_id, request_id),
    ).fetchone()
    priority = connection.execute(
        """SELECT priority, is_default FROM request_priority_facts
           WHERE tenant_id = %s AND request_id = %s ORDER BY sequence DESC LIMIT 1""",
        (tenant_id, request_id),
    ).fetchone()
    if owner is None or priority is None:
        raise RuntimeError("Request has no initial owner or priority fact")
    return {
        "blockers": tuple(active_blocker_keys(connection, tenant_id, request_id)),
        "optional": tuple(active_relations(connection, tenant_id, request_id, purpose="optional")),
        "owner_id": cast(UUID, owner["owner_id"]),
        "priority": str(priority["priority"]),
        "priority_default": bool(priority["is_default"]),
        "required": tuple(active_relations(connection, tenant_id, request_id, purpose="required")),
        "triage": latest_triage(connection, tenant_id, request_id),
    }


def _operation(command: RequestChange) -> str:
    if isinstance(command, RequestPriority):
        return "priority"
    if isinstance(command, RequestTriage):
        return "triage"
    if isinstance(command, RequestOwner):
        return "owner"
    if isinstance(command, RequestTicketRelation):
        return "ticket_relation"
    if isinstance(command, RequestBlocker):
        return "blocker"
    return "closure_evaluation"


def _result(payload: dict[str, object]) -> RequestChangeResult:
    return RequestChangeResult(
        command_id=UUID(str(payload["command_id"])),
        event_ids=tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        operation=str(payload["operation"]),
        request_id=UUID(str(payload["request_id"])),
        request_number=int(cast(int, payload["request_number"])),
        version=int(cast(int, payload["version"])),
        state=str(payload["state"]),
    )


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command: RequestChange,
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
