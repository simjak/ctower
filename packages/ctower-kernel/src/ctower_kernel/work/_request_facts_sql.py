"""Append-only Request fact mutations and semantic refusals."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg import sql

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.identifiers import uuid7
from ctower_kernel.work._request_state_sql import (
    closure_outcome,
    dependency_digest,
    latest_triage,
)
from ctower_kernel.work._request_types import (
    RequestBlocker,
    RequestChange,
    RequestClosureEvaluation,
    RequestOwner,
    RequestPriority,
    RequestTicketRelation,
    RequestTriage,
)

__all__ = ["append_fact", "current_owner", "request_problem"]


def current_owner(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> UUID:
    row = connection.execute(
        """
        SELECT owner_id FROM request_owner_facts
        WHERE tenant_id = %s AND request_id = %s ORDER BY sequence DESC LIMIT 1
        """,
        (tenant_id, request_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("Request has no accountable owner fact")
    return cast(UUID, row["owner_id"])


def append_fact(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestChange,
    request: dict[str, object],
    *,
    now: datetime,
) -> RecordProblem | None:
    if isinstance(command, RequestPriority):
        _append_priority(connection, actor, command, now=now)
        return None
    if isinstance(command, RequestTriage):
        return _append_triage(connection, actor, command, request, now=now)
    if isinstance(command, RequestOwner):
        return _append_owner(connection, actor, command, request, now=now)
    if isinstance(command, RequestTicketRelation):
        return _append_relation(connection, actor, command, request, now=now)
    if isinstance(command, RequestBlocker):
        return _append_blocker(connection, actor, command, now=now)
    _append_closure(connection, actor, command, now=now)
    return None


def _append_priority(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestPriority,
    *,
    now: datetime,
) -> None:
    sequence = _next_sequence(connection, "request_priority_facts", command.request_id)
    connection.execute(
        """
        INSERT INTO request_priority_facts (
            request_id, tenant_id, sequence, priority, is_default, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, false, %s, %s, %s, %s)
        """,
        (
            command.request_id,
            actor.tenant_id,
            sequence,
            command.priority,
            command.reason,
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )


def _append_triage(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestTriage,
    request: dict[str, object],
    *,
    now: datetime,
) -> RecordProblem | None:
    refusal = _triage_refusal(connection, actor, command, request)
    if refusal is not None:
        return refusal
    _insert_triage(connection, actor, command, now=now)
    owner_id = current_owner(connection, actor.tenant_id, command.request_id)
    _attention(
        connection,
        actor,
        command,
        owner_id,
        "request_triage_required",
        active=False,
        reason="Commander disposition recorded",
        now=now,
    )
    if command.disposition == "ACCEPTED":
        _attention(
            connection,
            actor,
            command,
            owner_id,
            "request_execution_link_required",
            active=True,
            reason="Accepted Request requires at least one fulfillment Ticket",
            now=now,
        )
    return None


def _triage_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestTriage,
    request: dict[str, object],
) -> RecordProblem | None:
    if command.disposition == "ACCEPTED" and _priority_is_default(
        connection, actor.tenant_id, command.request_id
    ):
        return request_problem(
            command,
            "request-triage-forbidden",
            409,
            "Accepted triage requires an explicit priority assignment",
        )
    if _is_canonical_target(connection, actor.tenant_id, command.request_id):
        return request_problem(
            command,
            "request-triage-forbidden",
            409,
            "A canonical duplicate target cannot itself become a duplicate",
        )
    if command.disposition == "DUPLICATE":
        return _duplicate_target(connection, actor, command, request)
    return None


def _priority_is_default(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> bool:
    priority = connection.execute(
        """
        SELECT is_default FROM request_priority_facts
        WHERE tenant_id = %s AND request_id = %s ORDER BY sequence DESC LIMIT 1
        """,
        (tenant_id, request_id),
    ).fetchone()
    return priority is None or bool(priority["is_default"])


def _insert_triage(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestTriage,
    *,
    now: datetime,
) -> None:
    sequence = _next_sequence(connection, "request_triage_facts", command.request_id)
    connection.execute(
        """
        INSERT INTO request_triage_facts (
            request_id, tenant_id, sequence, disposition, reason, canonical_request_id,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            command.request_id,
            actor.tenant_id,
            sequence,
            command.disposition,
            command.reason,
            command.canonical_request_id,
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )


def _duplicate_target(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestTriage,
    request: dict[str, object],
) -> RecordProblem | None:
    if command.canonical_request_id == command.request_id:
        return request_problem(
            command, "request-triage-forbidden", 409, "A Request cannot duplicate itself"
        )
    target = connection.execute(
        """
        SELECT request_id, project_key FROM requests
        WHERE tenant_id = %s AND request_id = %s FOR UPDATE
        """,
        (actor.tenant_id, command.canonical_request_id),
    ).fetchone()
    if target is None or str(target["project_key"]) != str(request["project_key"]):
        return request_problem(
            command,
            "request-triage-forbidden",
            409,
            "Canonical Request must exist in the same Project",
        )
    if latest_triage(connection, actor.tenant_id, cast(UUID, target["request_id"])) == "DUPLICATE":
        return request_problem(
            command,
            "request-triage-forbidden",
            409,
            "A duplicate Request cannot be a canonical target",
        )
    return None


def _is_canonical_target(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, request_id: UUID
) -> bool:
    return (
        connection.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (request_id) disposition, canonical_request_id
                FROM request_triage_facts WHERE tenant_id = %s
                ORDER BY request_id, sequence DESC
            )
            SELECT 1 FROM latest
            WHERE disposition = 'DUPLICATE' AND canonical_request_id = %s LIMIT 1
            """,
            (tenant_id, request_id),
        ).fetchone()
        is not None
    )


def _append_owner(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestOwner,
    request: dict[str, object],
    *,
    now: datetime,
) -> RecordProblem | None:
    if not _addressable_owner(
        connection, actor.tenant_id, command.owner_id, str(request["project_key"])
    ):
        return request_problem(
            command,
            "request-owner-forbidden",
            409,
            "Accountable owner must be an existing addressable Project Actor",
        )
    sequence = _next_sequence(connection, "request_owner_facts", command.request_id)
    connection.execute(
        """
        INSERT INTO request_owner_facts (
            request_id, tenant_id, sequence, owner_id, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            command.request_id,
            actor.tenant_id,
            sequence,
            command.owner_id,
            command.reason,
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )
    return None


def _addressable_owner(
    connection: psycopg.Connection[dict[str, object]],
    tenant_id: UUID,
    owner_id: UUID,
    project_key: str,
) -> bool:
    return (
        connection.execute(
            """
            SELECT 1 FROM project_seats AS seat
            JOIN principals AS principal
              ON principal.tenant_id = seat.tenant_id AND principal.principal_id = seat.principal_id
            WHERE seat.tenant_id = %s AND seat.principal_id = %s
              AND seat.project_key = %s AND principal.kind = 'commander'
              AND NOT principal.disabled
            UNION ALL
            SELECT 1 FROM human_role_bindings AS binding
            JOIN principals AS principal
              ON principal.tenant_id = binding.tenant_id
             AND principal.principal_id = binding.principal_id
            LEFT JOIN human_role_binding_revocations AS revocation
              ON revocation.binding_id = binding.binding_id
             AND revocation.tenant_id = binding.tenant_id
            WHERE binding.tenant_id = %s AND binding.principal_id = %s
              AND binding.role IN ('operator', 'commander')
              AND %s = ANY(binding.project_keys) AND revocation.binding_id IS NULL
              AND NOT principal.disabled
            LIMIT 1
            """,
            (tenant_id, owner_id, project_key, tenant_id, owner_id, project_key),
        ).fetchone()
        is not None
    )


def _append_relation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestTicketRelation,
    request: dict[str, object],
    *,
    now: datetime,
) -> RecordProblem | None:
    refusal = _relation_refusal(connection, actor, command, request)
    if refusal is not None:
        return refusal
    _insert_relation(connection, actor, command, now=now)
    if command.active:
        _clear_link_attention(connection, actor, command, now=now)
    return None


def _relation_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestTicketRelation,
    request: dict[str, object],
) -> RecordProblem | None:
    if latest_triage(connection, actor.tenant_id, command.request_id) != "ACCEPTED":
        return request_problem(
            command,
            "request-transition-forbidden",
            409,
            "Fulfillment Tickets require an accepted Request",
        )
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"request-ticket:{actor.tenant_id}:{command.ticket_id}",),
    )
    ticket = connection.execute(
        """
        SELECT project_key, version FROM tickets
        WHERE tenant_id = %s AND ticket_id = %s FOR UPDATE
        """,
        (actor.tenant_id, command.ticket_id),
    ).fetchone()
    if ticket is None or str(ticket["project_key"]) != str(request["project_key"]):
        return request_problem(
            command,
            "request-transition-forbidden",
            409,
            "Fulfillment Ticket must exist in the same Project",
        )
    if int(cast(int, ticket["version"])) != command.expected_ticket_version:
        return request_problem(
            command,
            "version-conflict",
            409,
            "Fulfillment Ticket version is stale",
            current_version=int(cast(int, ticket["version"])),
        )
    return _relation_state_refusal(connection, actor, command)


def _relation_state_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestTicketRelation,
) -> RecordProblem | None:
    current = _current_relation(connection, actor.tenant_id, command.ticket_id)
    if command.active and current is not None and current != command.request_id:
        return request_problem(
            command,
            "request-transition-forbidden",
            409,
            "A fulfillment Ticket belongs to one accepted Request",
        )
    if not command.active and current != command.request_id:
        return request_problem(
            command,
            "request-transition-forbidden",
            409,
            "The active fulfillment relation does not exist",
        )
    return None


def _insert_relation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestTicketRelation,
    *,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO request_ticket_relation_facts (
            relation_fact_id, request_id, tenant_id, request_version, ticket_id, purpose, active,
            reason, recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            uuid7(now),
            command.request_id,
            actor.tenant_id,
            command.expected_version + 1,
            command.ticket_id,
            command.purpose,
            command.active,
            command.reason,
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )


def _clear_link_attention(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestTicketRelation,
    *,
    now: datetime,
) -> None:
    owner_id = current_owner(connection, actor.tenant_id, command.request_id)
    _attention(
        connection,
        actor,
        command,
        owner_id,
        "request_execution_link_required",
        active=False,
        reason="At least one fulfillment Ticket is related",
        now=now,
    )


def _current_relation(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, ticket_id: UUID
) -> UUID | None:
    row = connection.execute(
        """
        SELECT request_id FROM request_ticket_holders
        WHERE tenant_id = %s AND ticket_id = %s
        """,
        (tenant_id, ticket_id),
    ).fetchone()
    return cast(UUID, row["request_id"]) if row is not None else None


def _append_blocker(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestBlocker,
    *,
    now: datetime,
) -> RecordProblem | None:
    current = connection.execute(
        """
        SELECT active FROM request_blocker_facts
        WHERE tenant_id = %s AND request_id = %s AND blocker_key = %s
        ORDER BY request_version DESC LIMIT 1
        """,
        (actor.tenant_id, command.request_id, command.blocker_key),
    ).fetchone()
    if not command.active and (current is None or not bool(current["active"])):
        return request_problem(
            command,
            "request-transition-forbidden",
            409,
            "The active Request blocker does not exist",
        )
    connection.execute(
        """
        INSERT INTO request_blocker_facts (
            blocker_fact_id, request_id, tenant_id, request_version, blocker_key, active, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            uuid7(now),
            command.request_id,
            actor.tenant_id,
            command.expected_version + 1,
            command.blocker_key,
            command.active,
            command.reason,
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )
    return None


def _append_closure(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestClosureEvaluation,
    *,
    now: datetime,
) -> None:
    outcome = closure_outcome(connection, actor.tenant_id, command.request_id)
    connection.execute(
        """
        INSERT INTO request_closure_evaluations (
            evaluation_id, request_id, tenant_id, request_version, outcome, reason,
            dependency_digest, recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            uuid7(now),
            command.request_id,
            actor.tenant_id,
            command.expected_version + 1,
            outcome,
            command.reason,
            dependency_digest(connection, actor.tenant_id, command.request_id),
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )


def _next_sequence(
    connection: psycopg.Connection[dict[str, object]], table: str, request_id: UUID
) -> int:
    if table not in {"request_owner_facts", "request_priority_facts", "request_triage_facts"}:
        raise ValueError("Request fact table is not authored")
    query = sql.SQL(
        "SELECT COALESCE(max(sequence), 0) AS value FROM {} WHERE request_id = %s"
    ).format(sql.Identifier(table))
    row = connection.execute(query, (request_id,)).fetchone()
    if row is None:
        raise RuntimeError("Request fact sequence aggregate returned no row")
    return int(cast(int, row["value"])) + 1


def _attention(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: RequestChange,
    owner_id: UUID,
    kind: str,
    *,
    active: bool,
    reason: str,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO request_attention_facts (
            attention_id, request_id, tenant_id, kind, active, owner_id, reason,
            recorded_by, command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            uuid7(now),
            command.request_id,
            actor.tenant_id,
            kind,
            active,
            owner_id,
            reason,
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )


def request_problem(
    command: RequestChange,
    code: str,
    status: int,
    detail: str,
    *,
    current_version: int | None = None,
) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=detail,
        status=status,
        title="Request command refused",
        command_id=command.client_command_id,
        current_version=current_version,
    )
