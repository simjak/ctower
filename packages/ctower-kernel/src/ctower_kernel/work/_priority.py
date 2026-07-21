"""Priority fact mutation owned by Work."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import psycopg

from ctower_kernel.record import Actor
from ctower_kernel.work import ChangePriority

__all__: tuple[str, ...] = ()


def change_priority(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: ChangePriority,
    *,
    previous_priority: str,
    episode: int,
    now: datetime,
) -> dict[str, object]:
    row = cast(
        dict[str, object],
        connection.execute(
            "SELECT COALESCE(max(fact_sequence), 0) + 1 AS value FROM priority_facts "
            "WHERE ticket_id = %s AND tenant_id = %s",
            (command.ticket_id, actor.tenant_id),
        ).fetchone(),
    )
    sequence = row["value"]
    connection.execute(
        """
        INSERT INTO priority_facts (
            ticket_id, tenant_id, fact_sequence, priority, changed_by,
            reason, client_command_id, recorded_at, episode_number, operation,
            previous_priority, authority, policy_ref, urgent_evidence_ref
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'change', %s, %s, %s, %s)
        """,
        (
            command.ticket_id,
            actor.tenant_id,
            sequence,
            command.priority,
            actor.principal_id,
            command.reason,
            command.client_command_id,
            now,
            episode,
            previous_priority,
            actor.kind.value,
            "ctower.priority-authority@1",
            command.urgent_evidence_ref,
        ),
    )
    connection.execute(
        "UPDATE tickets SET priority = %s WHERE tenant_id = %s AND ticket_id = %s",
        (command.priority, actor.tenant_id, command.ticket_id),
    )
    return {
        "authority": actor.kind.value,
        "from_priority": previous_priority,
        "policy_ref": "ctower.priority-authority@1",
        "reason": command.reason,
        "to_priority": command.priority,
        "urgent_evidence_ref": command.urgent_evidence_ref,
    }
