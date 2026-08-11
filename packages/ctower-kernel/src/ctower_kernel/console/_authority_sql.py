"""Shared SQL primitives that lock Console authority before durable effects."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.console.models import (
    ConsoleBackendObservation,
    ConsoleSessionRef,
    ConsoleStreamLease,
)
from ctower_kernel.record import Actor
from ctower_kernel.record.identifiers import uuid7


def authority_connection(dsn: str) -> psycopg.Connection[dict[str, object]]:
    connection = psycopg.connect(dsn, row_factory=dict_row)
    connection.execute("SET ROLE ctower_svc")
    return connection


def allowance_lock(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, allowance_id: UUID
) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"console-allowance:{tenant_id}:{allowance_id}",),
    )


def lock_authority_anchors(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, allowance_id: UUID
) -> bool:
    """Lock mutable authority anchors in one fixed order before a persisted decision."""

    if actor.human_binding_id is None or actor.human_session_id is None:
        return False
    row = connection.execute(
        "SELECT lock_console_authority_anchors(%s, %s, %s, %s, %s) AS locked",
        (
            actor.tenant_id,
            actor.principal_id,
            actor.human_binding_id,
            actor.human_session_id,
            allowance_id,
        ),
    ).fetchone()
    return row is not None and bool(row["locked"])


def stream_authority_row(
    connection: psycopg.Connection[dict[str, object]], lease: ConsoleStreamLease
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT view_grant.expires_at, view_grant.policy_revision,
            grant_revocation.grant_id IS NOT NULL AS grant_revoked,
            session_revocation.allowance_id IS NOT NULL AS session_revoked,
            human_revocation.session_id IS NOT NULL AS human_session_revoked,
            binding_revocation.binding_id IS NOT NULL AS binding_revoked,
            human_session.expires_at AS human_session_expires_at,
            COALESCE((
                SELECT enabled FROM console_global_kill_switch_facts
                WHERE tenant_id = view_grant.tenant_id
                ORDER BY recorded_at DESC, fact_id DESC LIMIT 1
            ), false) AS global_enabled,
            (
                assignment.released_at IS NULL
                AND assignment.principal_id = allowance.seat_principal_id
            ) AS assignment_current,
            (
                closure.session_id IS NULL
                AND work_session.started_by = allowance.seat_principal_id
                AND work_session.project_key = allowance.project_key
                AND work_session.crew_name = allowance.crew_name
                AND target.kind <> 'commander'
                AND NOT target.disabled
            ) AS work_session_current
        FROM console_view_grants AS view_grant
        JOIN console_session_allows AS allowance
          ON allowance.allowance_id = view_grant.allowance_id
         AND allowance.tenant_id = view_grant.tenant_id
        JOIN human_sessions AS human_session
          ON human_session.session_id = view_grant.human_session_id
         AND human_session.tenant_id = view_grant.tenant_id
        JOIN assignment_intervals AS assignment
          ON assignment.ticket_id = allowance.assignment_ticket_id
         AND assignment.assignment_kind = allowance.assignment_kind
         AND assignment.interval_sequence = allowance.assignment_interval_sequence
         AND assignment.tenant_id = allowance.tenant_id
        JOIN ticket_work_sessions AS work_session
          ON work_session.session_id = allowance.recorded_work_session_id
         AND work_session.tenant_id = allowance.tenant_id
        JOIN principals AS target
          ON target.principal_id = allowance.seat_principal_id
         AND target.tenant_id = allowance.tenant_id
        LEFT JOIN ticket_work_session_closures AS closure
          ON closure.session_id = work_session.session_id
         AND closure.tenant_id = work_session.tenant_id
        LEFT JOIN console_view_grant_revocations AS grant_revocation
          ON grant_revocation.grant_id = view_grant.grant_id
         AND grant_revocation.tenant_id = view_grant.tenant_id
        LEFT JOIN console_session_revocations AS session_revocation
          ON session_revocation.allowance_id = allowance.allowance_id
         AND session_revocation.tenant_id = allowance.tenant_id
        LEFT JOIN human_session_revocations AS human_revocation
          ON human_revocation.session_id = view_grant.human_session_id
         AND human_revocation.tenant_id = view_grant.tenant_id
        LEFT JOIN human_role_binding_revocations AS binding_revocation
          ON binding_revocation.binding_id = view_grant.human_binding_id
         AND binding_revocation.tenant_id = view_grant.tenant_id
        WHERE view_grant.grant_id = %s AND view_grant.tenant_id = %s
        """,
        (lease.grant.grant_id, lease.grant.tenant_id),
    ).fetchone()


def session_join_row(
    connection: psycopg.Connection[dict[str, object]], ref: ConsoleSessionRef
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT session.project_key, session.crew_name, session.started_by, target.kind,
            target.disabled,
            assignment.principal_id, assignment.released_at,
            closure.session_id IS NOT NULL AS closed
        FROM ticket_work_sessions AS session
        JOIN assignment_intervals AS assignment
          ON assignment.ticket_id = %s
         AND assignment.assignment_kind = %s
         AND assignment.interval_sequence = %s
         AND assignment.tenant_id = session.tenant_id
        JOIN principals AS target
          ON target.principal_id = session.started_by
         AND target.tenant_id = session.tenant_id
        LEFT JOIN ticket_work_session_closures AS closure
          ON closure.session_id = session.session_id
         AND closure.tenant_id = session.tenant_id
        WHERE session.session_id = %s AND session.tenant_id = %s
          AND session.ticket_id = %s
        """,
        (
            ref.assignment_ticket_id,
            ref.assignment_kind,
            ref.assignment_interval_sequence,
            ref.recorded_work_session_id,
            ref.tenant_id,
            ref.assignment_ticket_id,
        ),
    ).fetchone()


def record_observation(
    connection: psycopg.Connection[dict[str, object]],
    allowance_id: UUID,
    tenant_id: UUID,
    observation: ConsoleBackendObservation,
    outcome: Literal["matched", "fenced", "unavailable"],
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO console_adapter_observation_facts (
            observation_id, tenant_id, allowance_id, project_key,
            runtime_attempt_id, runner_id, runner_epoch, backend_incarnation,
            outcome, observed_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            uuid7(now),
            tenant_id,
            allowance_id,
            observation.project_key,
            observation.runtime_attempt_id,
            observation.runner_id,
            observation.runner_epoch,
            observation.backend_incarnation,
            outcome,
            now,
        ),
    )
