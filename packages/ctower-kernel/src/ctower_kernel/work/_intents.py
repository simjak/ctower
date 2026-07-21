"""Lifecycle/admission intents without a writable status field."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.work import Admit, Defer, Reopen

__all__: tuple[str, ...] = ()


def admit(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: Admit,
    *,
    fact_id: UUID,
    lifecycle_id: UUID,
    episode: int,
    now: datetime,
) -> dict[str, object] | RecordProblem:
    state = _episode_state(connection, actor, command.ticket_id, episode)
    if state not in {"open", "waiting"}:
        return _problem(
            command,
            "work-intent-unmet",
            "Open or waiting episode required",
            ("lifecycle.open-or-waiting@1",),
        )
    _admission_fact(
        connection,
        actor,
        command,
        fact_id,
        episode,
        admitted=True,
        review_after=None,
        now=now,
    )
    _lifecycle_fact(connection, actor, command, lifecycle_id, episode, "active", now)
    _set_episode(connection, actor, command.ticket_id, episode, "active")
    return {"episode_number": episode, "reason": command.reason}


def defer(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: Defer,
    *,
    fact_id: UUID,
    lifecycle_id: UUID,
    episode: int,
    now: datetime,
) -> dict[str, object] | RecordProblem:
    state = _episode_state(connection, actor, command.ticket_id, episode)
    if state not in {"open", "active", "waiting"}:
        return _problem(
            command,
            "work-intent-unmet",
            "Actionable episode required",
            ("lifecycle.actionable@1",),
        )
    _admission_fact(
        connection,
        actor,
        command,
        fact_id,
        episode,
        admitted=False,
        review_after=command.review_after,
        now=now,
    )
    _lifecycle_fact(connection, actor, command, lifecycle_id, episode, "waiting", now)
    _set_episode(connection, actor, command.ticket_id, episode, "waiting")
    return {
        "episode_number": episode,
        "reason": command.reason,
        "review_after": command.review_after.isoformat(),
    }


def reopen(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: Reopen,
    *,
    lifecycle_id: UUID,
    episode: int,
    custodian_id: UUID,
    priority: str,
    now: datetime,
) -> dict[str, object] | RecordProblem:
    state = _episode_state(connection, actor, command.ticket_id, episode)
    if state not in {"resolved", "closed"}:
        return _problem(
            command,
            "work-reopen-unmet",
            "Resolved or closed episode required",
            ("lifecycle.resolved-or-closed@1",),
        )
    if not _eligible_custodian(connection, actor, custodian_id):
        return _problem(
            command,
            "work-assignment-target-ineligible",
            "Eligible custodian required for reopened episode",
            ("custody.eligible-current@1",),
        )
    next_episode = episode + 1
    connection.execute(
        """
        INSERT INTO lifecycle_episodes (ticket_id, tenant_id, episode_number, state, opened_at)
        VALUES (%s, %s, %s, 'open', %s)
        """,
        (command.ticket_id, actor.tenant_id, next_episode, now),
    )
    connection.execute(
        "UPDATE tickets SET current_episode = %s WHERE tenant_id = %s AND ticket_id = %s",
        (next_episode, actor.tenant_id, command.ticket_id),
    )
    sequence_row = cast(
        dict[str, object],
        connection.execute(
            """
            SELECT COALESCE(max(interval_sequence), 0) + 1 AS value
            FROM assignment_intervals
            WHERE tenant_id = %s AND ticket_id = %s
              AND assignment_kind = 'ticket_custodian'
            """,
            (actor.tenant_id, command.ticket_id),
        ).fetchone(),
    )
    connection.execute(
        """
        INSERT INTO assignment_intervals (
            ticket_id, tenant_id, interval_sequence, assignment_kind, principal_id,
            assigned_at, released_at, changed_by, reason, client_command_id, episode_number
        ) VALUES (%s, %s, %s, 'ticket_custodian', %s, %s, NULL, %s, %s, %s, %s)
        """,
        (
            command.ticket_id,
            actor.tenant_id,
            sequence_row["value"],
            custodian_id,
            now,
            actor.principal_id,
            f"reopen carry-forward: {command.reason}",
            command.client_command_id,
            next_episode,
        ),
    )
    _lifecycle_fact(connection, actor, command, lifecycle_id, next_episode, "reopened", now)
    sequence_row = cast(
        dict[str, object],
        connection.execute(
            "SELECT COALESCE(max(fact_sequence), 0) + 1 AS value FROM priority_facts "
            "WHERE tenant_id = %s AND ticket_id = %s",
            (actor.tenant_id, command.ticket_id),
        ).fetchone(),
    )
    sequence = sequence_row["value"]
    connection.execute(
        """
        INSERT INTO priority_facts (
            ticket_id, tenant_id, fact_sequence, priority, changed_by,
            reason, client_command_id, recorded_at, episode_number, operation,
            previous_priority, authority, policy_ref
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'initial', NULL,
            'reopen-policy', 'ctower.reopen-carry-forward@1')
        """,
        (
            command.ticket_id,
            actor.tenant_id,
            sequence,
            priority,
            actor.principal_id,
            f"reopen carry-forward: {command.reason}",
            command.client_command_id,
            now,
            next_episode,
        ),
    )
    return {"episode_number": next_episode, "priority": priority, "reason": command.reason}


def _admission_fact(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: Admit | Defer,
    fact_id: UUID,
    episode: int,
    *,
    admitted: bool,
    review_after: datetime | None,
    now: datetime,
) -> None:
    sequence_row = cast(
        dict[str, object],
        connection.execute(
            """
        SELECT COALESCE(max(fact_sequence), 0) + 1 AS value FROM admission_facts
        WHERE tenant_id = %s AND ticket_id = %s AND episode_number = %s
        """,
            (actor.tenant_id, command.ticket_id, episode),
        ).fetchone(),
    )
    sequence = sequence_row["value"]
    connection.execute(
        """
        INSERT INTO admission_facts (
            admission_fact_id, ticket_id, tenant_id, episode_number, fact_sequence,
            admitted, review_after, reason, actor_principal_id, client_command_id, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            fact_id,
            command.ticket_id,
            actor.tenant_id,
            episode,
            sequence,
            admitted,
            review_after,
            command.reason,
            actor.principal_id,
            command.client_command_id,
            now,
        ),
    )


def _lifecycle_fact(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: Admit | Defer | Reopen,
    fact_id: UUID,
    episode: int,
    state: str,
    now: datetime,
) -> None:
    sequence_row = cast(
        dict[str, object],
        connection.execute(
            """
        SELECT COALESCE(max(fact_sequence), 0) + 1 AS value FROM lifecycle_facts
        WHERE tenant_id = %s AND ticket_id = %s AND episode_number = %s
        """,
            (actor.tenant_id, command.ticket_id, episode),
        ).fetchone(),
    )
    sequence = sequence_row["value"]
    connection.execute(
        """
        INSERT INTO lifecycle_facts (
            lifecycle_fact_id, ticket_id, tenant_id, fact_sequence, state,
            actor_principal_id, client_command_id, recorded_at, episode_number, reason
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            fact_id,
            command.ticket_id,
            actor.tenant_id,
            sequence,
            state,
            actor.principal_id,
            command.client_command_id,
            now,
            episode,
            command.reason,
        ),
    )


def _episode_state(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, ticket_id: UUID, episode: int
) -> str | None:
    row = connection.execute(
        """
        SELECT state FROM lifecycle_episodes
        WHERE tenant_id = %s AND ticket_id = %s AND episode_number = %s FOR UPDATE
        """,
        (actor.tenant_id, ticket_id, episode),
    ).fetchone()
    return str(row["state"]) if row is not None else None


def _eligible_custodian(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, principal_id: UUID
) -> bool:
    row = connection.execute(
        """
        SELECT 1 FROM principals
        WHERE tenant_id = %s AND principal_id = %s AND NOT disabled
          AND kind IN ('commander', 'operator')
        """,
        (actor.tenant_id, principal_id),
    ).fetchone()
    return row is not None


def _set_episode(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    ticket_id: UUID,
    episode: int,
    state: str,
) -> None:
    connection.execute(
        """
        UPDATE lifecycle_episodes SET state = %s
        WHERE tenant_id = %s AND ticket_id = %s AND episode_number = %s
        """,
        (state, actor.tenant_id, ticket_id, episode),
    )


def _problem(
    command: Admit | Defer | Reopen,
    code: str,
    title: str,
    unmet_facts: tuple[str, ...],
) -> RecordProblem:
    return RecordProblem(
        code,
        title,
        409,
        title,
        command.client_command_id,
        unmet_facts=unmet_facts,
    )
