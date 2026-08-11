"""Focused SQL primitives for one atomic Console grant decision."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import psycopg

from ctower_kernel.console.models import ConsoleViewGrant
from ctower_kernel.record import Actor

__all__: tuple[str, ...] = ()


def _grant_facts_row(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    allowance_id: UUID,
    *,
    now: datetime,
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT allowance.*,
            revocation.allowance_id IS NULL AS allowlist_active,
            assignment.released_at IS NULL AS assignment_current,
            (
                assignment.principal_id = allowance.seat_principal_id
                AND session.started_by = allowance.seat_principal_id
                AND session.project_key = allowance.project_key
                AND session.crew_name = allowance.crew_name
                AND target.kind <> 'commander'
                AND NOT target.disabled
                AND closure.session_id IS NULL
            ) AS session_join_current,
            COALESCE((
                SELECT enabled FROM console_global_kill_switch_facts
                WHERE tenant_id = allowance.tenant_id
                ORDER BY recorded_at DESC, fact_id DESC LIMIT 1
            ), false) AS global_enabled,
            (
                SELECT max(expires_at) FROM console_view_suspensions
                WHERE tenant_id = allowance.tenant_id
                  AND actor_principal_id = %s
                  AND expires_at > %s
            ) AS suspended_until,
            (
                human_session.expires_at > %s
                AND human_session_revocation.session_id IS NULL
            ) AS human_session_current,
            (
                human_binding.role = %s
                AND allowance.project_key = ANY(human_binding.project_keys)
                AND human_binding_revocation.binding_id IS NULL
            ) AS human_binding_current
        FROM console_session_allows AS allowance
        JOIN assignment_intervals AS assignment
          ON assignment.ticket_id = allowance.assignment_ticket_id
         AND assignment.assignment_kind = allowance.assignment_kind
         AND assignment.interval_sequence = allowance.assignment_interval_sequence
        JOIN ticket_work_sessions AS session
          ON session.session_id = allowance.recorded_work_session_id
         AND session.tenant_id = allowance.tenant_id
        JOIN principals AS target
          ON target.principal_id = allowance.seat_principal_id
         AND target.tenant_id = allowance.tenant_id
        JOIN human_sessions AS human_session
          ON human_session.session_id = %s
         AND human_session.tenant_id = allowance.tenant_id
         AND human_session.principal_id = %s
         AND human_session.binding_id = %s
        JOIN human_role_bindings AS human_binding
          ON human_binding.binding_id = human_session.binding_id
         AND human_binding.tenant_id = human_session.tenant_id
         AND human_binding.principal_id = human_session.principal_id
        LEFT JOIN ticket_work_session_closures AS closure
          ON closure.session_id = session.session_id
         AND closure.tenant_id = session.tenant_id
        LEFT JOIN console_session_revocations AS revocation
          ON revocation.allowance_id = allowance.allowance_id
        LEFT JOIN human_session_revocations AS human_session_revocation
          ON human_session_revocation.session_id = human_session.session_id
         AND human_session_revocation.tenant_id = human_session.tenant_id
        LEFT JOIN human_role_binding_revocations AS human_binding_revocation
          ON human_binding_revocation.binding_id = human_binding.binding_id
         AND human_binding_revocation.tenant_id = human_binding.tenant_id
        WHERE allowance.allowance_id = %s AND allowance.tenant_id = %s
        """,
        (
            actor.principal_id,
            now,
            now,
            actor.kind.value,
            actor.human_session_id,
            actor.principal_id,
            actor.human_binding_id,
            allowance_id,
            actor.tenant_id,
        ),
    ).fetchone()


def _previous_grant_row(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, allowance_id: UUID
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT view_grant.*, allowance.*
        FROM console_view_grants AS view_grant
        JOIN console_session_allows AS allowance
          ON allowance.allowance_id = view_grant.allowance_id
         AND allowance.tenant_id = view_grant.tenant_id
        WHERE view_grant.tenant_id = %s
          AND view_grant.actor_principal_id = %s
          AND view_grant.human_session_id = %s
          AND view_grant.allowance_id = %s
        ORDER BY view_grant.grant_sequence DESC LIMIT 1
        """,
        (actor.tenant_id, actor.principal_id, actor.human_session_id, allowance_id),
    ).fetchone()


def _insert_grant(
    connection: psycopg.Connection[dict[str, object]], grant: ConsoleViewGrant, *, now: datetime
) -> None:
    connection.execute(
        """
        INSERT INTO console_view_grants (
            grant_id, tenant_id, project_key, actor_principal_id,
            human_binding_id, human_session_id, allowance_id, policy_revision,
            issuer, not_before, expires_at, maximum_uses, nonce,
            continuous_view_started_at, renewed_from_grant_id, granted_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            grant.grant_id,
            grant.tenant_id,
            grant.project_key,
            grant.actor_principal_id,
            grant.human_binding_id,
            grant.human_session_id,
            grant.allowance_id,
            grant.policy_revision,
            grant.issuer,
            grant.not_before,
            grant.expires_at,
            grant.maximum_uses,
            grant.nonce,
            grant.continuous_view_started_at,
            grant.renewed_from_grant_id,
            now,
        ),
    )
