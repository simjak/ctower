"""Typed ticket relations and cycle refusals owned by Work."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.work import AddRelation, RelationKind

__all__: tuple[str, ...] = ()


def add_relation(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: AddRelation,
    *,
    relation_id: UUID,
    now: datetime,
) -> dict[str, object] | RecordProblem:
    target = connection.execute(
        "SELECT 1 FROM tickets WHERE tenant_id = %s AND ticket_id = %s FOR SHARE",
        (actor.tenant_id, command.target_ticket_id),
    ).fetchone()
    if target is None:
        return _problem(command, "tenant-scope-denied", 404, "Target ticket unavailable")
    if command.ticket_id == command.target_ticket_id:
        return _problem(command, "work-relation-cycle", 409, "Relation cycle refused")
    if command.relation_kind in {
        RelationKind.PARENT_OF,
        RelationKind.DEPENDS_ON,
        RelationKind.BLOCKS,
    } and _reaches_source(connection, actor, command):
        return _problem(command, "work-relation-cycle", 409, "Relation cycle refused")
    inserted = connection.execute(
        """
        INSERT INTO ticket_relations (
            relation_id, tenant_id, source_ticket_id, target_ticket_id, relation_kind,
            actor_principal_id, reason, client_command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING relation_id
        """,
        (
            relation_id,
            actor.tenant_id,
            command.ticket_id,
            command.target_ticket_id,
            command.relation_kind.value,
            actor.principal_id,
            command.reason,
            command.client_command_id,
            now,
        ),
    ).fetchone()
    if inserted is None:
        return _problem(command, "work-relation-exists", 409, "Relation already exists")
    return {
        "relation_kind": command.relation_kind.value,
        "reason": command.reason,
        "target_ticket_id": str(command.target_ticket_id),
    }


def _reaches_source(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, command: AddRelation
) -> bool:
    row = connection.execute(
        """
        WITH RECURSIVE reachable(ticket_id) AS (
            SELECT %s::uuid
            UNION
            SELECT relation.target_ticket_id
            FROM ticket_relations AS relation
            JOIN reachable ON relation.source_ticket_id = reachable.ticket_id
            WHERE relation.tenant_id = %s AND relation.relation_kind = %s
        )
        SELECT 1 FROM reachable WHERE ticket_id = %s LIMIT 1
        """,
        (
            command.target_ticket_id,
            actor.tenant_id,
            command.relation_kind.value,
            command.ticket_id,
        ),
    ).fetchone()
    return row is not None


def _problem(command: AddRelation, code: str, status: int, title: str) -> RecordProblem:
    return RecordProblem(code, title, status, title, command.client_command_id)
