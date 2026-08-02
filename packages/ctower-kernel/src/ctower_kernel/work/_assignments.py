"""Gapless scoped assignment history owned by Work."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.work import AssignmentInterval, AssignmentKind, ChangeAssignment

__all__: tuple[str, ...] = ()


def change_assignment(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: ChangeAssignment,
    *,
    now: datetime,
) -> dict[str, object] | RecordProblem:
    if not _eligible(connection, actor, command):
        return _problem(
            command, "work-assignment-target-ineligible", "Assignment target unavailable"
        )
    current = connection.execute(
        """
        SELECT principal_id FROM assignment_intervals
        WHERE tenant_id = %s AND ticket_id = %s AND assignment_kind = %s
          AND scope_ref IS NOT DISTINCT FROM %s AND released_at IS NULL
        FOR UPDATE
        """,
        (actor.tenant_id, command.ticket_id, command.assignment_kind.value, command.scope_ref),
    ).fetchone()
    previous = cast(UUID, current["principal_id"]) if current is not None else None
    if previous == command.to_principal_id:
        return _problem(
            command, "work-assignment-unchanged", "Assignment target is already current"
        )
    if current is not None:
        connection.execute(
            """
            UPDATE assignment_intervals SET released_at = %s
            WHERE tenant_id = %s AND ticket_id = %s AND assignment_kind = %s
              AND scope_ref IS NOT DISTINCT FROM %s AND released_at IS NULL
            """,
            (
                now,
                actor.tenant_id,
                command.ticket_id,
                command.assignment_kind.value,
                command.scope_ref,
            ),
        )
    sequence_row = cast(
        dict[str, object],
        connection.execute(
            """
        SELECT COALESCE(max(interval_sequence), 0) + 1 AS value
        FROM assignment_intervals
        WHERE tenant_id = %s AND ticket_id = %s AND assignment_kind = %s
        """,
            (actor.tenant_id, command.ticket_id, command.assignment_kind.value),
        ).fetchone(),
    )
    sequence = sequence_row["value"]
    episode_row = cast(
        dict[str, object],
        connection.execute(
            "SELECT current_episode FROM tickets WHERE tenant_id = %s AND ticket_id = %s",
            (actor.tenant_id, command.ticket_id),
        ).fetchone(),
    )
    connection.execute(
        """
        INSERT INTO assignment_intervals (
            ticket_id, tenant_id, interval_sequence, assignment_kind, principal_id,
            assigned_at, released_at, changed_by, reason, client_command_id, scope_ref,
            episode_number
        ) VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, %s)
        """,
        (
            command.ticket_id,
            actor.tenant_id,
            sequence,
            command.assignment_kind.value,
            command.to_principal_id,
            now,
            actor.principal_id,
            command.reason,
            command.client_command_id,
            command.scope_ref,
            episode_row["current_episode"],
        ),
    )
    return {
        "assignment_kind": command.assignment_kind.value,
        "from_principal_id": str(previous) if previous else None,
        "reason": command.reason,
        "scope_ref": command.scope_ref,
        "to_principal_id": str(command.to_principal_id),
    }


def list_assignments(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    ticket_id: UUID,
    project_key: str,
) -> tuple[AssignmentInterval, ...] | RecordProblem:
    exists = connection.execute(
        """
        SELECT 1 FROM tickets
        WHERE tenant_id = %s AND ticket_id = %s AND project_key = %s
        """,
        (actor.tenant_id, ticket_id, project_key),
    ).fetchone()
    if exists is None:
        return RecordProblem("tenant-scope-denied", "Ticket unavailable", 404, "Ticket unavailable")
    rows = connection.execute(
        """
        SELECT assignment_kind, episode_number, principal_id, assigned_at, released_at,
            changed_by, reason, scope_ref, interval_sequence
        FROM assignment_intervals
        WHERE tenant_id = %s AND ticket_id = %s
        ORDER BY assignment_kind, interval_sequence
        """,
        (actor.tenant_id, ticket_id),
    ).fetchall()
    return tuple(
        AssignmentInterval(
            assignment_kind=AssignmentKind(str(row["assignment_kind"])),
            episode_number=int(cast(int, row["episode_number"])),
            principal_id=cast(UUID, row["principal_id"]),
            assigned_at=cast(datetime, row["assigned_at"]),
            released_at=cast(datetime | None, row["released_at"]),
            changed_by=cast(UUID, row["changed_by"]),
            reason=str(row["reason"]),
            scope_ref=cast(str | None, row["scope_ref"]),
            sequence=int(cast(int, row["interval_sequence"])),
        )
        for row in rows
    )


def _eligible(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: ChangeAssignment,
) -> bool:
    allowed = {
        AssignmentKind.CURRENT_ASSIGNEE: ("agent", "commander", "operator"),
        AssignmentKind.STAGE_OWNER: ("agent", "commander"),
        AssignmentKind.REVIEWER_ASSIGNMENT: ("reviewer", "operator"),
    }.get(command.assignment_kind, ())
    row = connection.execute(
        """
        SELECT kind FROM principals
        WHERE tenant_id = %s AND principal_id = %s AND NOT disabled
        """,
        (actor.tenant_id, command.to_principal_id),
    ).fetchone()
    return row is not None and str(row["kind"]) in allowed


def _problem(command: ChangeAssignment, code: str, title: str) -> RecordProblem:
    return RecordProblem(code, title, 409, title, command.client_command_id)
