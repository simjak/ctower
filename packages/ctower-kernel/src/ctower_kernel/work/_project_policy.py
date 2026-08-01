"""Server-derived project authorization for authoritative ticket writes."""

from __future__ import annotations

from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, PrincipalKind, RecordProblem

__all__: tuple[str, ...] = ()


def project_mutation_refusal(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    ticket_ids: tuple[UUID, ...],
    command_id: UUID,
) -> RecordProblem | None:
    """Refuse any existing ticket outside the actor's persisted project grant."""

    if actor.kind is PrincipalKind.OPERATOR:
        return None
    foreign = connection.execute(
        """
        SELECT ticket.project_key
        FROM tickets AS ticket
        LEFT JOIN project_seats AS seat
          ON seat.tenant_id = ticket.tenant_id
         AND seat.principal_id = %s
         AND seat.project_key = ticket.project_key
        WHERE ticket.tenant_id = %s AND ticket.ticket_id = ANY(%s)
          AND seat.principal_id IS NULL
        ORDER BY ticket.project_key
        LIMIT 1
        """,
        (actor.principal_id, actor.tenant_id, list(ticket_ids)),
    ).fetchone()
    if foreign is None:
        return None
    return RecordProblem(
        code="project-scope-denied",
        detail="The authenticated project seat cannot mutate a ticket from another project.",
        status=403,
        title="Project scope denied",
        command_id=command_id,
    )
