"""Atomic Postgres choreography behind the Work Interface."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext
from ctower_kernel.work import (
    AddRelation,
    Admit,
    AssignmentInterval,
    Block,
    ChangeAssignment,
    ChangePriority,
    Defer,
    Reopen,
    Unblock,
    WorkCommand,
    WorkReadiness,
    WorkReceipt,
)
from ctower_kernel.work._assignments import change_assignment, list_assignments
from ctower_kernel.work._blockers import open_blocker, resolve_blocker
from ctower_kernel.work._event_sql import append_change
from ctower_kernel.work._intents import admit, defer, reopen
from ctower_kernel.work._priority import change_priority
from ctower_kernel.work._relations import add_relation

__all__: tuple[str, ...] = ()


def execute_work(
    dsn: str,
    actor: Actor,
    command: WorkCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> WorkReceipt | RecordProblem:
    """Reserve replay authority, serialize Ticket/Work, and append one typed event."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        reserved = _reserve_work_outcome(
            transaction,
            actor,
            command,
            request_digest=request_digest,
            now=now,
        )
        if reserved is not None:
            return reserved
        ticket = _work_ticket(
            connection,
            transaction,
            actor,
            command,
            request_digest=request_digest,
            now=now,
        )
        if isinstance(ticket, RecordProblem):
            return ticket
        version = int(cast(int, ticket["version"]))
        if command.expected_version != version:
            return _refuse(
                transaction,
                actor,
                command,
                request_digest,
                _problem(
                    command, "version-conflict", 409, "Work version conflict", version=version
                ),
                now,
            )
        operation, outcome = _mutate(connection, actor, command, ticket=ticket, now=now)
        if isinstance(outcome, RecordProblem):
            return _refuse(transaction, actor, command, request_digest, outcome, now)
        next_version = version + 1
        connection.execute(
            "UPDATE tickets SET version = %s WHERE tenant_id = %s AND ticket_id = %s",
            (next_version, actor.tenant_id, command.ticket_id),
        )
        receipt = WorkReceipt(
            command.client_command_id, (), operation, command.ticket_id, next_version
        )
        return append_change(
            connection,
            actor,
            receipt,
            outcome,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
            subjects=_touched_subjects(command),
        )


def _work_ticket(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: WorkCommand,
    *,
    request_digest: bytes,
    now: datetime,
) -> dict[str, object] | RecordProblem:
    ticket = _lock_ticket(connection, actor, command)
    if ticket is None:
        refusal = _problem(command, "tenant-scope-denied", 404, "Ticket unavailable")
        return _refuse(transaction, actor, command, request_digest, refusal, now)
    return ticket


def _reserve_work_outcome(
    transaction: RecordTransaction,
    actor: Actor,
    command: WorkCommand,
    *,
    request_digest: bytes,
    now: datetime,
) -> WorkReceipt | RecordProblem | None:
    existing = transaction.reserve_ticket_mutation(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        _command_ticket_ids(command),
        now=now,
    )
    if isinstance(existing, RecordProblem):
        return existing
    if existing is not None:
        return _receipt(existing)
    return transaction.require_durable_subjects(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        _prerequisite_subjects(command),
        now=now,
    )


def _prerequisite_subjects(command: WorkCommand) -> tuple[tuple[str, UUID], ...]:
    return tuple(("ticket", ticket_id) for ticket_id in _command_ticket_ids(command))


def _command_ticket_ids(command: WorkCommand) -> tuple[UUID, ...]:
    ticket_ids = (
        {command.ticket_id, command.target_ticket_id}
        if isinstance(command, AddRelation)
        else {command.ticket_id}
    )
    return tuple(sorted(ticket_ids, key=lambda item: item.int))


def _touched_subjects(command: WorkCommand) -> tuple[tuple[str, UUID], ...]:
    return (*_prerequisite_subjects(command), ("work", command.ticket_id))


def _lock_ticket(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, command: WorkCommand
) -> dict[str, object] | None:
    """Lock relation endpoints in UUID order; otherwise lock the source ticket."""

    ticket_ids = (
        tuple(sorted({command.ticket_id, command.target_ticket_id}, key=lambda value: value.int))
        if isinstance(command, AddRelation)
        else (command.ticket_id,)
    )
    rows = connection.execute(
        """
        SELECT ticket_id, version, priority, current_episode, custodian_principal_id
        FROM tickets
        WHERE tenant_id = %s AND ticket_id = ANY(%s) ORDER BY ticket_id FOR UPDATE
        """,
        (actor.tenant_id, list(ticket_ids)),
    ).fetchall()
    ticket = next((row for row in rows if row["ticket_id"] == command.ticket_id), None)
    if ticket is None:
        return None
    lifecycle = cast(
        dict[str, object],
        connection.execute(
            """
            SELECT state FROM lifecycle_episodes
            WHERE tenant_id = %s AND ticket_id = %s AND episode_number = %s
            """,
            (actor.tenant_id, command.ticket_id, ticket["current_episode"]),
        ).fetchone(),
    )
    return {**ticket, "lifecycle_state": lifecycle["state"]}


def assignments(
    dsn: str, actor: Actor, ticket_id: UUID
) -> tuple[AssignmentInterval, ...] | RecordProblem:
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        return list_assignments(connection, actor, ticket_id)


def readiness(dsn: str, actor: Actor, ticket_id: UUID) -> WorkReadiness | RecordProblem:
    """Read admission and every effective Board blocker from authoritative heads."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        row = connection.execute(
            "SELECT 1 FROM tickets WHERE tenant_id = %s AND ticket_id = %s",
            (actor.tenant_id, ticket_id),
        ).fetchone()
        if row is None:
            return RecordProblem(
                "tenant-scope-denied", "Ticket unavailable", 404, "Ticket unavailable"
            )
        unmet = unmet_readiness(connection, actor.tenant_id, ticket_id)
    return WorkReadiness(ready=not unmet, unmet_facts=unmet)


def unmet_readiness(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, ticket_id: UUID
) -> tuple[str, ...]:
    """Observe readiness inside a caller-owned transaction after its ticket lock."""

    row = connection.execute(
        """
            SELECT t.current_episode,
                (SELECT admitted FROM admission_facts AS a
                 WHERE a.tenant_id = t.tenant_id AND a.ticket_id = t.ticket_id
                   AND a.episode_number = t.current_episode
                 ORDER BY a.fact_sequence DESC LIMIT 1) AS admitted,
                EXISTS (
                    SELECT 1 FROM blocker_heads AS b
                    WHERE b.tenant_id = t.tenant_id AND b.ticket_id = t.ticket_id
                      AND b.board_impact AND b.resolved_at IS NULL
                ) AS blocked
            FROM tickets AS t WHERE t.tenant_id = %s AND t.ticket_id = %s
            """,
        (tenant_id, ticket_id),
    ).fetchone()
    if row is None:
        return ("work.ticket-current@1",)
    unmet: list[str] = []
    if row["admitted"] is not True:
        unmet.append("work.admitted@1")
    if row["blocked"] is True:
        unmet.append("work.unblocked@1")
    return tuple(unmet)


def _mutate(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: WorkCommand,
    *,
    ticket: dict[str, object],
    now: datetime,
) -> tuple[str, dict[str, object] | RecordProblem]:
    if isinstance(command, ChangeAssignment) and ticket["lifecycle_state"] in {
        "closed",
        "cancelled",
    }:
        return "assignment_changed", _problem(
            command,
            "work-ticket-terminal",
            409,
            "Closed ticket requires a legal reopen before assignment",
        )
    if isinstance(command, ChangePriority):
        if command.priority == str(ticket["priority"]):
            return "priority_changed", _problem(
                command, "work-priority-unchanged", 409, "Priority is already current"
            )
        return "priority_changed", change_priority(
            connection,
            actor,
            command,
            previous_priority=str(ticket["priority"]),
            episode=int(cast(int, ticket["current_episode"])),
            now=now,
        )
    if isinstance(command, ChangeAssignment):
        return "assignment_changed", change_assignment(connection, actor, command, now=now)
    return _mutate_intent(connection, actor, command, ticket=ticket, now=now)


def _mutate_intent(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: WorkCommand,
    *,
    ticket: dict[str, object],
    now: datetime,
) -> tuple[str, dict[str, object] | RecordProblem]:
    identifier = _uuid7(now)
    episode = int(cast(int, ticket["current_episode"]))
    if isinstance(command, Admit):
        return "admitted", admit(
            connection,
            actor,
            command,
            fact_id=identifier,
            lifecycle_id=_uuid7(now),
            episode=episode,
            now=now,
        )
    if isinstance(command, Defer):
        return "deferred", defer(
            connection,
            actor,
            command,
            fact_id=identifier,
            lifecycle_id=_uuid7(now),
            episode=episode,
            now=now,
        )
    if isinstance(command, Block):
        return "blocker_opened", open_blocker(
            connection, actor, command, fact_id=identifier, now=now
        )
    if isinstance(command, Unblock):
        return "blocker_resolved", resolve_blocker(
            connection, actor, command, fact_id=identifier, now=now
        )
    if isinstance(command, Reopen):
        return "reopened", reopen(
            connection,
            actor,
            command,
            lifecycle_id=identifier,
            episode=episode,
            custodian_id=cast(UUID, ticket["custodian_principal_id"]),
            priority=str(ticket["priority"]),
            now=now,
        )
    if isinstance(command, AddRelation):
        return "relation_added", add_relation(
            connection, actor, command, relation_id=identifier, now=now
        )
    raise TypeError("unsupported Work command")


def _receipt(payload: dict[str, object]) -> WorkReceipt:
    return WorkReceipt(
        command_id=UUID(str(payload["command_id"])),
        event_ids=tuple(UUID(str(item)) for item in cast(list[object], payload["event_ids"])),
        operation=str(payload["operation"]),
        ticket_id=UUID(str(payload["ticket_id"])),
        version=int(cast(int, payload["version"])),
    )


def _problem(
    command: WorkCommand,
    code: str,
    status: int,
    title: str,
    *,
    version: int | None = None,
) -> RecordProblem:
    return RecordProblem(code, title, status, title, command.client_command_id, version)


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command: WorkCommand,
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


def _uuid7(now: datetime) -> UUID:
    milliseconds = int(now.timestamp() * 1000) & ((1 << 48) - 1)
    random_bits = secrets.randbits(74)
    value = milliseconds << 80
    value |= 0x7 << 76
    value |= ((random_bits >> 62) & 0xFFF) << 64
    value |= 0b10 << 62
    value |= random_bits & ((1 << 62) - 1)
    return UUID(int=value)
