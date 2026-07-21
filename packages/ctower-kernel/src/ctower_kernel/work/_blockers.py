"""Typed multi-blocker authority owned by Work."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.work import Block, Unblock

__all__: tuple[str, ...] = ()


def open_blocker(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: Block,
    *,
    fact_id: UUID,
    now: datetime,
) -> dict[str, object] | RecordProblem:
    owner = connection.execute(
        "SELECT 1 FROM principals WHERE tenant_id = %s AND principal_id = %s AND NOT disabled",
        (actor.tenant_id, command.owner_principal_id),
    ).fetchone()
    if owner is None:
        return _problem(command, "work-blocker-owner-ineligible", "Blocker owner unavailable")
    try:
        connection.execute(
            """
            INSERT INTO blocker_heads (
                blocker_id, ticket_id, tenant_id, blocker_kind, reason_class, reason,
                owner_principal_id, source_ref, affected_stage, resolution_condition,
                next_check_at, dependency_ref, board_impact, opened_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                command.blocker_id,
                command.ticket_id,
                actor.tenant_id,
                command.blocker_kind,
                command.reason_class,
                command.reason,
                command.owner_principal_id,
                command.source_ref,
                command.affected_stage,
                command.resolution_condition,
                command.next_check_at,
                command.dependency_ref,
                command.board_impact,
                now,
            ),
        )
    except psycopg.errors.UniqueViolation:
        return _problem(command, "work-blocker-id-conflict", "Blocker identifier already exists")
    _fact(connection, actor, command, fact_id, "opened", command.reason, None, now)
    return {
        "blocker_id": str(command.blocker_id),
        "board_impact": command.board_impact,
        "reason": command.reason,
    }


def resolve_blocker(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: Unblock,
    *,
    fact_id: UUID,
    now: datetime,
) -> dict[str, object] | RecordProblem:
    row = connection.execute(
        """
        SELECT resolved_at FROM blocker_heads
        WHERE tenant_id = %s AND ticket_id = %s AND blocker_id = %s FOR UPDATE
        """,
        (actor.tenant_id, command.ticket_id, command.blocker_id),
    ).fetchone()
    if row is None:
        return _problem(command, "work-blocker-unknown", "Effective blocker not found")
    if row["resolved_at"] is not None:
        return _problem(command, "work-blocker-already-resolved", "Blocker is already resolved")
    connection.execute(
        """
        UPDATE blocker_heads SET resolved_at = %s, resolution_evidence_ref = %s
        WHERE tenant_id = %s AND blocker_id = %s
        """,
        (now, command.resolution_evidence_ref, actor.tenant_id, command.blocker_id),
    )
    _fact(
        connection,
        actor,
        command,
        fact_id,
        "resolved",
        command.reason,
        command.resolution_evidence_ref,
        now,
    )
    return {
        "blocker_id": str(command.blocker_id),
        "reason": command.reason,
        "resolution_evidence_ref": command.resolution_evidence_ref,
    }


def _fact(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: Block | Unblock,
    fact_id: UUID,
    operation: str,
    reason: str,
    evidence: str | None,
    now: datetime,
) -> None:
    sequence_row = cast(
        dict[str, object],
        connection.execute(
            "SELECT COALESCE(max(fact_sequence), 0) + 1 AS value FROM blocker_facts "
            "WHERE blocker_id = %s",
            (command.blocker_id,),
        ).fetchone(),
    )
    sequence = sequence_row["value"]
    connection.execute(
        """
        INSERT INTO blocker_facts (
            blocker_fact_id, blocker_id, tenant_id, fact_sequence, operation,
            actor_principal_id, client_command_id, reason, resolution_evidence_ref, recorded_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            fact_id,
            command.blocker_id,
            actor.tenant_id,
            sequence,
            operation,
            actor.principal_id,
            command.client_command_id,
            reason,
            evidence,
            now,
        ),
    )


def _problem(command: Block | Unblock, code: str, title: str) -> RecordProblem:
    return RecordProblem(code, title, 409, title, command.client_command_id)
