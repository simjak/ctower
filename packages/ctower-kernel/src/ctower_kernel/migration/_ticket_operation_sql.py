"""Ticket-seed and relation operations allowed to the migration importer."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_client.models import (
    CtowerProjectImportBatchRequest,
    CtowerProjectTicketRelationOperation,
    CtowerProjectTicketSeedOperation,
    MigrationImportOperationResult,
)
from ctower_kernel.migration._operation_result_sql import (
    canonical,
    commit_result,
    source_matches,
)
from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.events import EventKind, TicketCreatedPayload, WorkChangedPayload
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()
_CYCLIC_RELATIONS = frozenset({"parent_of", "depends_on", "blocks"})
RELATION_ENDPOINT_COUNT = 2


def seed_ticket(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectTicketSeedOperation,
    *,
    now: datetime,
    telemetry: TelemetryContext,
) -> MigrationImportOperationResult | RecordProblem:
    if not source_matches(operation) or not _commander(
        connection, actor, operation.initial_commander_custodian_id
    ):
        return _problem(
            operation.identity.command_id,
            "migration-capability-denied",
            "Ticket seed authority refused",
            403,
        )
    ticket_id = _uuid7(now)
    _insert_seed_state(connection, actor, batch, operation, ticket_id=ticket_id, now=now)
    payload = TicketCreatedPayload(
        custodian_id=operation.initial_commander_custodian_id,
        priority="P2",
        source_kind="ctower-project-import",
        source_ref=_ticket_source_ref(operation),
        title=operation.title,
    )
    return commit_result(
        connection,
        actor,
        batch,
        operation,
        target_id=str(ticket_id),
        kind=EventKind.TICKET_CREATED,
        payload=payload,
        aggregate_id=ticket_id,
        sequence=1,
        stream_id=f"ticket:{ticket_id}",
        now=now,
        telemetry=telemetry,
        subjects=(("ticket", ticket_id),),
    )


def _insert_seed_state(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectTicketSeedOperation,
    *,
    ticket_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO tickets (
            ticket_id, tenant_id, title, source_kind, source_ref, priority,
            custodian_principal_id, version, durability_state, created_by, created_at
        ) VALUES (%s, %s, %s, 'ctower-project-import', %s, 'P2', %s, 1,
            'durability_pending', %s, %s)
        """,
        (
            ticket_id,
            actor.tenant_id,
            operation.title,
            _ticket_source_ref(operation),
            operation.initial_commander_custodian_id,
            actor.principal_id,
            now,
        ),
    )
    _insert_initial_facts(connection, actor, operation, ticket_id, now)
    connection.execute(
        """
        INSERT INTO ticket_project_bindings (
            ticket_id, tenant_id, project_key, run_id, source_namespace,
            immutable_source_id, bound_at
        ) VALUES (%s, %s, 'ctower', %s, %s, %s, %s)
        """,
        (
            ticket_id,
            actor.tenant_id,
            batch.run_id,
            operation.source.namespace,
            operation.source.immutable_source_id,
            now,
        ),
    )


def _ticket_source_ref(operation: CtowerProjectTicketSeedOperation) -> str:
    material = f"{operation.source.namespace}\0{operation.source.immutable_source_id}".encode()
    return f"sha256:{hashlib.sha256(material).hexdigest()}"


def add_relation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectTicketRelationOperation,
    *,
    now: datetime,
    telemetry: TelemetryContext,
) -> MigrationImportOperationResult | RecordProblem:
    endpoints = _lock_endpoints(connection, actor, batch, operation)
    if len(endpoints) != RELATION_ENDPOINT_COUNT or _relation_cycle(connection, actor, operation):
        return _problem(
            operation.identity.command_id,
            "migration-relation-invalid",
            "Relation endpoints or cycle are invalid",
        )
    source = next(row for row in endpoints if row["ticket_id"] == operation.source_ticket_id)
    next_version = int(cast(int, source["version"])) + 1
    _insert_relation(
        connection,
        actor,
        batch,
        operation,
        next_version=next_version,
        now=now,
    )
    payload = WorkChangedPayload(
        operation="relation_added",
        ticket_id=operation.source_ticket_id,
        work_version=next_version,
        data={
            "relation_kind": operation.relation_kind,
            "reason": operation.reason,
            "target_ticket_id": str(operation.target_ticket_id),
        },
    )
    return _commit_relation(
        connection,
        actor,
        batch,
        operation,
        payload=payload,
        next_version=next_version,
        now=now,
        telemetry=telemetry,
    )


def _lock_endpoints(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectTicketRelationOperation,
) -> list[dict[str, object]]:
    return connection.execute(
        """
        SELECT ticket.ticket_id, ticket.version
        FROM tickets AS ticket
        JOIN ticket_project_bindings AS binding ON binding.ticket_id = ticket.ticket_id
        WHERE ticket.tenant_id = %s AND binding.run_id = %s
          AND ticket.ticket_id = ANY(%s) ORDER BY ticket.ticket_id FOR UPDATE OF ticket
        """,
        (
            actor.tenant_id,
            batch.run_id,
            [operation.source_ticket_id, operation.target_ticket_id],
        ),
    ).fetchall()


def _insert_relation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectTicketRelationOperation,
    *,
    next_version: int,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO ticket_relations (
            relation_id, tenant_id, source_ticket_id, target_ticket_id, relation_kind,
            actor_principal_id, reason, client_command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            operation.relation_id,
            actor.tenant_id,
            operation.source_ticket_id,
            operation.target_ticket_id,
            operation.relation_kind,
            actor.principal_id,
            operation.reason,
            operation.identity.command_id,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO migration_relation_validity_facts (
            relation_id, revision, run_id, active, replacement_relation_id,
            semantic_digest, command_id, recorded_at
        ) VALUES (%s, 1, %s, true, NULL, %s, %s, %s)
        """,
        (
            operation.relation_id,
            batch.run_id,
            hashlib.sha256(canonical(operation)).digest(),
            operation.identity.command_id,
            now,
        ),
    )
    connection.execute(
        "UPDATE tickets SET version = %s WHERE ticket_id = %s AND tenant_id = %s",
        (next_version, operation.source_ticket_id, actor.tenant_id),
    )


def _commit_relation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    batch: CtowerProjectImportBatchRequest,
    operation: CtowerProjectTicketRelationOperation,
    *,
    payload: WorkChangedPayload,
    next_version: int,
    now: datetime,
    telemetry: TelemetryContext,
) -> MigrationImportOperationResult:
    return commit_result(
        connection,
        actor,
        batch,
        operation,
        target_id=str(operation.relation_id),
        kind=EventKind.WORK_CHANGED,
        payload=payload,
        aggregate_id=operation.source_ticket_id,
        sequence=next_version,
        stream_id=f"ticket:{operation.source_ticket_id}",
        now=now,
        telemetry=telemetry,
        subjects=(
            ("ticket", operation.source_ticket_id),
            ("ticket", operation.target_ticket_id),
            ("work", operation.source_ticket_id),
        ),
    )


def _insert_initial_facts(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    operation: CtowerProjectTicketSeedOperation,
    ticket_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO lifecycle_episodes (
            ticket_id, tenant_id, episode_number, state, opened_at
        ) VALUES (%s, %s, 1, 'open', %s)
        """,
        (ticket_id, actor.tenant_id, now),
    )
    connection.execute(
        """
        INSERT INTO assignment_intervals (
            ticket_id, tenant_id, interval_sequence, assignment_kind, principal_id,
            assigned_at, changed_by, reason, client_command_id, episode_number
        ) VALUES (%s, %s, 1, 'ticket_custodian', %s, %s, %s,
            'migration ticket seed', %s, 1)
        """,
        (
            ticket_id,
            actor.tenant_id,
            operation.initial_commander_custodian_id,
            now,
            actor.principal_id,
            operation.identity.command_id,
        ),
    )
    connection.execute(
        """
        INSERT INTO priority_facts (
            ticket_id, tenant_id, fact_sequence, priority, changed_by,
            reason, client_command_id, recorded_at
        ) VALUES (%s, %s, 1, 'P2', %s, 'migration ticket seed', %s, %s)
        """,
        (ticket_id, actor.tenant_id, actor.principal_id, operation.identity.command_id, now),
    )


def _relation_cycle(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    operation: CtowerProjectTicketRelationOperation,
) -> bool:
    if operation.source_ticket_id == operation.target_ticket_id:
        return True
    if operation.relation_kind not in _CYCLIC_RELATIONS:
        return False
    return (
        connection.execute(
            """
        WITH RECURSIVE reachable(ticket_id) AS (
            SELECT %s::uuid UNION
            SELECT relation.target_ticket_id FROM ticket_relations AS relation
            JOIN reachable ON relation.source_ticket_id = reachable.ticket_id
            WHERE relation.tenant_id = %s AND relation.relation_kind = %s
        )
        SELECT 1 FROM reachable WHERE ticket_id = %s LIMIT 1
        """,
            (
                operation.target_ticket_id,
                actor.tenant_id,
                operation.relation_kind,
                operation.source_ticket_id,
            ),
        ).fetchone()
        is not None
    )


def _commander(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, principal_id: UUID
) -> bool:
    return (
        connection.execute(
            """
        SELECT 1 FROM principals WHERE tenant_id = %s AND principal_id = %s
          AND kind = 'commander' AND NOT disabled
        """,
            (actor.tenant_id, principal_id),
        ).fetchone()
        is not None
    )


def _problem(command_id: UUID, code: str, title: str, status: int = 409) -> RecordProblem:
    return RecordProblem(code, title, status, title, command_id)


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
