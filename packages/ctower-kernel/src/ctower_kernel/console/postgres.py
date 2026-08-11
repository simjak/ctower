"""Postgres authority for append-only Console Phase-1 facts and encrypted cursors."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.console._authority_policy import (
    _allow_authority_refusal,
    _allow_request_refusal,
    _observation_from_ref,
    _observation_refusal,
    session_join_refusal,
    stream_claim_refusal,
    stream_close_reason,
)
from ctower_kernel.console._grant_sql import (
    _grant_facts_row,
    _insert_grant,
    _previous_grant_row,
)
from ctower_kernel.console.models import (
    ConsoleBackendObservation,
    ConsoleGlobalSwitchCommand,
    ConsoleGrantFacts,
    ConsoleGrantIdentifiers,
    ConsolePolicy,
    ConsoleSessionAllowance,
    ConsoleSessionAllowCommand,
    ConsoleSessionRef,
    ConsoleSessionRevocation,
    ConsoleStreamLease,
    ConsoleViewGrant,
)
from ctower_kernel.console.policy import decide_view_grant, preflight_view_grant
from ctower_kernel.record import Actor, PrincipalKind, RecordProblem
from ctower_kernel.record.identifiers import uuid7

__all__ = ["PostgresConsoleAuthority"]

type StreamCloseCode = Literal[
    "expired",
    "revoked",
    "fenced",
    "rate_limited",
    "slow_consumer",
    "reauthentication_required",
    "globally_disabled",
    "output_unavailable",
    "client_disconnected",
]


class PostgresConsoleAuthority:
    """Own Console authority facts; the runtime Adapter never receives this object."""

    def __init__(self, dsn: str, *, policy: ConsolePolicy) -> None:
        self._dsn = dsn
        self.policy = policy

    def allow_session(
        self,
        actor: Actor,
        command: ConsoleSessionAllowCommand,
        observation: ConsoleBackendObservation,
        *,
        now: datetime,
    ) -> ConsoleSessionAllowance | RecordProblem:
        ref = command.session_ref
        refusal = _allow_request_refusal(actor, ref, observation)
        if refusal is not None:
            return refusal
        allowance_id = uuid7(now)
        with _authority_connection(self._dsn) as connection:
            join_refusal = session_join_refusal(_session_join_row(connection, ref), ref)
            if join_refusal is not None:
                return join_refusal
            insert_refusal = _insert_allowance(connection, allowance_id, actor, command, now=now)
            if insert_refusal is not None:
                return insert_refusal
            _record_observation(
                connection, allowance_id, ref.tenant_id, observation, "matched", now
            )
        return ConsoleSessionAllowance(
            allowance_id=allowance_id,
            tenant_id=ref.tenant_id,
            project_key=ref.project_key,
            recorded_work_session_id=ref.recorded_work_session_id,
            crew_name=ref.crew_name,
            allowed_at=now,
        )

    def preflight_allow_session(self, actor: Actor, ref: ConsoleSessionRef) -> RecordProblem | None:
        """Refuse known durable allowance defects before runtime inspection."""

        refusal = _allow_authority_refusal(actor, ref)
        if refusal is not None:
            return refusal
        with _authority_connection(self._dsn) as connection:
            join_refusal = session_join_refusal(_session_join_row(connection, ref), ref)
            if join_refusal is not None:
                return join_refusal
            existing = connection.execute(
                "SELECT 1 FROM console_session_allows WHERE recorded_work_session_id = %s",
                (ref.recorded_work_session_id,),
            ).fetchone()
        if existing is not None:
            return _problem(
                "console-session-already-allowed",
                "The recorded work session already has its one allowlist fact.",
                409,
            )
        return None

    def session_ref(self, actor: Actor, allowance_id: UUID) -> ConsoleSessionRef | RecordProblem:
        with _authority_connection(self._dsn) as connection:
            row = connection.execute(
                """
                SELECT * FROM console_session_allows
                WHERE allowance_id = %s AND tenant_id = %s
                """,
                (allowance_id, actor.tenant_id),
            ).fetchone()
        if row is None:
            return _problem(
                "console-session-unavailable", "The console session is unavailable.", 404
            )
        return _ref_from_row(row)

    def visible_allowances(
        self, actor: Actor, *, now: datetime
    ) -> tuple[ConsoleSessionAllowance, ...] | RecordProblem:
        if actor.kind is PrincipalKind.COMMANDER:
            return _problem("console-role-refused", "Commander console viewing is absent.", 404)
        with _authority_connection(self._dsn) as connection:
            rows = connection.execute(
                """
                SELECT allowance.*
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
                LEFT JOIN console_session_revocations AS revocation
                  ON revocation.allowance_id = allowance.allowance_id
                LEFT JOIN ticket_work_session_closures AS closure
                  ON closure.session_id = session.session_id
                WHERE allowance.tenant_id = %s
                  AND allowance.project_key = ANY(%s)
                  AND assignment.released_at IS NULL
                  AND assignment.principal_id = allowance.seat_principal_id
                  AND session.started_by = allowance.seat_principal_id
                  AND target.kind <> 'commander'
                  AND NOT target.disabled
                  AND revocation.allowance_id IS NULL
                  AND closure.session_id IS NULL
                  AND NOT COALESCE((
                      SELECT enabled FROM console_global_kill_switch_facts
                      WHERE tenant_id = allowance.tenant_id
                      ORDER BY recorded_at DESC, fact_id DESC LIMIT 1
                  ), false)
                  AND NOT EXISTS (
                      SELECT 1 FROM console_view_suspensions AS suspension
                      WHERE suspension.tenant_id = allowance.tenant_id
                        AND suspension.actor_principal_id = %s
                        AND suspension.expires_at > %s
                  )
                ORDER BY allowance.allowed_at, allowance.allowance_id
                """,
                (actor.tenant_id, list(actor.project_grants), actor.principal_id, now),
            ).fetchall()
        return tuple(_allowance_from_row(row) for row in rows)

    def preflight_access(
        self,
        actor: Actor,
        allowance_id: UUID,
        *,
        operation: Literal["grant", "stream"],
        now: datetime,
    ) -> ConsoleSessionRef | RecordProblem:
        """Refuse durable grant or stream defects before runtime inspection."""

        if operation == "stream":
            grant = self._claimable_grant(actor, allowance_id, now=now, stream_id=None)
            return grant if isinstance(grant, RecordProblem) else grant.session_ref
        ref = self.session_ref(actor, allowance_id)
        if isinstance(ref, RecordProblem):
            return ref
        with _authority_connection(self._dsn) as connection:
            facts = _grant_facts(
                connection,
                actor,
                allowance_id,
                _observation_from_ref(ref),
                now=now,
                record_observation=False,
            )
        if isinstance(facts, RecordProblem):
            return facts
        refusal = preflight_view_grant(facts, now=now)
        return refusal if refusal is not None else ref

    def decide_grant(
        self,
        actor: Actor,
        allowance_id: UUID,
        observation: ConsoleBackendObservation,
        *,
        identifiers: ConsoleGrantIdentifiers,
        renewal: bool,
        now: datetime,
    ) -> ConsoleViewGrant | RecordProblem:
        """Atomically recheck authority, decide, and persist one grant."""

        with _authority_connection(self._dsn) as connection:
            _allowance_lock(connection, actor.tenant_id, allowance_id)
            facts = _grant_facts(
                connection, actor, allowance_id, observation, now=now, record_observation=True
            )
            if isinstance(facts, RecordProblem):
                return facts
            previous = _previous_grant(connection, actor, allowance_id)
            if renewal and previous is None:
                return _problem(
                    "console-renewal-unavailable", "There is no prior grant to renew.", 401
                )
            outcome = decide_view_grant(
                facts,
                identifiers,
                policy=self.policy,
                now=now,
                previous_grant=previous if renewal else None,
            )
            if isinstance(outcome, RecordProblem):
                return outcome
            if not renewal and previous is not None and previous.expires_at > now:
                return _problem(
                    "console-grant-already-current",
                    "A current grant already exists; renew it explicitly.",
                    409,
                )
            _insert_grant(connection, outcome, now=now)
        return outcome

    def record_denial(
        self, actor: Actor, allowance_id: UUID | None, code: str, *, now: datetime
    ) -> None:
        with _authority_connection(self._dsn) as connection:
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"console-denial:{actor.tenant_id}:{actor.principal_id}",),
            )
            active = connection.execute(
                """
                SELECT 1 FROM console_view_suspensions
                WHERE tenant_id = %s AND actor_principal_id = %s AND expires_at > %s
                """,
                (actor.tenant_id, actor.principal_id, now),
            ).fetchone()
            if active is not None:
                return
            safe_allowance = connection.execute(
                """
                SELECT allowance_id FROM console_session_allows
                WHERE allowance_id = %s AND tenant_id = %s
                """,
                (allowance_id, actor.tenant_id),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO console_view_denials (
                    denial_id, tenant_id, actor_principal_id, allowance_id, code, denied_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid7(now),
                    actor.tenant_id,
                    actor.principal_id,
                    None if safe_allowance is None else allowance_id,
                    code,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT count(*) AS denial_count
                FROM console_view_denials
                WHERE tenant_id = %s AND actor_principal_id = %s AND denied_at > %s
                """,
                (
                    actor.tenant_id,
                    actor.principal_id,
                    now - timedelta(seconds=self.policy.denial_window_seconds),
                ),
            ).fetchone()
            denial_count = 0 if row is None else cast(int, row["denial_count"])
            if denial_count >= self.policy.denial_limit:
                connection.execute(
                    """
                    INSERT INTO console_view_suspensions (
                        suspension_id, tenant_id, actor_principal_id, denial_count,
                        reason, suspended_at, expires_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        uuid7(now),
                        actor.tenant_id,
                        actor.principal_id,
                        denial_count,
                        "repeated console grant denials",
                        now,
                        now + timedelta(seconds=self.policy.suspension_seconds),
                    ),
                )

    def revoke_session(
        self, actor: Actor, command: ConsoleSessionRevocation, *, now: datetime
    ) -> RecordProblem | None:
        if actor.kind is not PrincipalKind.OPERATOR:
            return _problem(
                "console-revocation-refused", "Console revocation requires operator authority."
            )
        with _authority_connection(self._dsn) as connection:
            _allowance_lock(connection, actor.tenant_id, command.allowance_id)
            row = connection.execute(
                "SELECT 1 FROM console_session_allows WHERE allowance_id = %s AND tenant_id = %s",
                (command.allowance_id, actor.tenant_id),
            ).fetchone()
            if row is None:
                return _problem(
                    "console-session-unavailable", "The console session is unavailable.", 404
                )
            try:
                connection.execute(
                    """
                    INSERT INTO console_session_revocations (
                        allowance_id, tenant_id, revoked_by, reason, revoked_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        command.allowance_id,
                        actor.tenant_id,
                        actor.principal_id,
                        command.reason,
                        now,
                    ),
                )
            except psycopg.errors.UniqueViolation:
                return _problem(
                    "console-session-already-revoked",
                    "The console session is already revoked.",
                    409,
                )
        return None

    def set_global_switch(
        self, actor: Actor, command: ConsoleGlobalSwitchCommand, *, now: datetime
    ) -> RecordProblem | None:
        if actor.kind is not PrincipalKind.OPERATOR:
            return _problem(
                "console-kill-switch-refused",
                "Console kill-switch changes require operator authority.",
            )
        with _authority_connection(self._dsn) as connection:
            connection.execute(
                """
                INSERT INTO console_global_kill_switch_facts (
                    fact_id, tenant_id, enabled, reason, recorded_by, recorded_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid7(now),
                    actor.tenant_id,
                    command.enabled,
                    command.reason,
                    actor.principal_id,
                    now,
                ),
            )
        return None

    def claim_stream(
        self, actor: Actor, allowance_id: UUID, *, now: datetime
    ) -> ConsoleStreamLease | RecordProblem:
        stream_id = uuid7(now)
        grant = self._claimable_grant(actor, allowance_id, now=now, stream_id=stream_id)
        if isinstance(grant, RecordProblem):
            return grant
        return ConsoleStreamLease(stream_id=stream_id, grant=grant, opened_at=now)

    def _claimable_grant(
        self,
        actor: Actor,
        allowance_id: UUID,
        *,
        now: datetime,
        stream_id: UUID | None,
    ) -> ConsoleViewGrant | RecordProblem:
        if actor.human_session_id is None or actor.human_binding_id is None:
            return _problem(
                "console-browser-session-required", "An exact human session is required."
            )
        with _authority_connection(self._dsn) as connection:
            if stream_id is not None:
                _allowance_lock(connection, actor.tenant_id, allowance_id)
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"console:{actor.tenant_id}:{actor.principal_id}:{actor.human_session_id}",),
                )
            active = connection.execute(
                """
                SELECT 1
                FROM console_stream_opens AS opened
                JOIN console_view_grants AS view_grant
                  ON view_grant.grant_id = opened.grant_id
                LEFT JOIN console_stream_closes AS closed ON closed.stream_id = opened.stream_id
                WHERE opened.tenant_id = %s AND opened.actor_principal_id = %s
                  AND opened.human_session_id = %s AND closed.stream_id IS NULL
                  AND view_grant.expires_at > %s
                """,
                (actor.tenant_id, actor.principal_id, actor.human_session_id, now),
            ).fetchone()
            if active is not None:
                return _problem(
                    "console-stream-already-open",
                    "Only one concurrent stream is allowed for the Actor session.",
                    409,
                )
            row = connection.execute(
                """
                SELECT view_grant.*, allowance.*,
                    grant_revocation.grant_id IS NOT NULL AS grant_revoked,
                    session_revocation.allowance_id IS NOT NULL AS session_revoked,
                    used.grant_id IS NOT NULL AS grant_used,
                    human_revocation.session_id IS NOT NULL AS human_session_revoked,
                    binding_revocation.binding_id IS NOT NULL AS binding_revoked,
                    human_session.expires_at AS human_session_expires_at,
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
                    ) AS work_session_current,
                    COALESCE((
                        SELECT enabled FROM console_global_kill_switch_facts
                        WHERE tenant_id = view_grant.tenant_id
                        ORDER BY recorded_at DESC, fact_id DESC LIMIT 1
                    ), false) AS global_enabled,
                    (
                        SELECT max(expires_at) FROM console_view_suspensions
                        WHERE tenant_id = view_grant.tenant_id
                          AND actor_principal_id = %s
                          AND expires_at > %s
                    ) AS suspended_until
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
                LEFT JOIN console_session_revocations AS session_revocation
                  ON session_revocation.allowance_id = view_grant.allowance_id
                LEFT JOIN console_stream_opens AS used
                  ON used.grant_id = view_grant.grant_id
                LEFT JOIN human_session_revocations AS human_revocation
                  ON human_revocation.session_id = view_grant.human_session_id
                 AND human_revocation.tenant_id = view_grant.tenant_id
                LEFT JOIN human_role_binding_revocations AS binding_revocation
                  ON binding_revocation.binding_id = view_grant.human_binding_id
                 AND binding_revocation.tenant_id = view_grant.tenant_id
                WHERE view_grant.tenant_id = %s
                  AND view_grant.actor_principal_id = %s
                  AND view_grant.human_binding_id = %s
                  AND view_grant.human_session_id = %s
                  AND view_grant.allowance_id = %s
                ORDER BY view_grant.grant_sequence DESC LIMIT 1
                """,
                (
                    actor.principal_id,
                    now,
                    actor.tenant_id,
                    actor.principal_id,
                    actor.human_binding_id,
                    actor.human_session_id,
                    allowance_id,
                ),
            ).fetchone()
            if row is None:
                return _problem(
                    "console-grant-unavailable", "No active unused grant is available.", 401
                )
            refusal = stream_claim_refusal(row, actor, self.policy, now=now)
            if refusal is not None:
                return refusal
            grant = _grant_from_row(row)
            if stream_id is not None:
                connection.execute(
                    """
                    INSERT INTO console_stream_opens (
                        stream_id, tenant_id, grant_id, actor_principal_id,
                        human_session_id, allowance_id, opened_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        stream_id,
                        actor.tenant_id,
                        grant.grant_id,
                        actor.principal_id,
                        actor.human_session_id,
                        allowance_id,
                        now,
                    ),
                )
        return grant

    def stream_close_reason(
        self, lease: ConsoleStreamLease, *, now: datetime
    ) -> StreamCloseCode | None:
        with _authority_connection(self._dsn) as connection:
            row = connection.execute(
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
                LEFT JOIN console_session_revocations AS session_revocation
                  ON session_revocation.allowance_id = allowance.allowance_id
                LEFT JOIN human_session_revocations AS human_revocation
                  ON human_revocation.session_id = view_grant.human_session_id
                LEFT JOIN human_role_binding_revocations AS binding_revocation
                  ON binding_revocation.binding_id = view_grant.human_binding_id
                WHERE view_grant.grant_id = %s AND view_grant.tenant_id = %s
                """,
                (lease.grant.grant_id, lease.grant.tenant_id),
            ).fetchone()
        return cast(StreamCloseCode | None, stream_close_reason(row, self.policy, now=now))

    def close_stream(
        self,
        lease: ConsoleStreamLease,
        code: StreamCloseCode,
        *,
        gap_required: bool,
        now: datetime,
    ) -> None:
        with _authority_connection(self._dsn) as connection:
            connection.execute(
                """
                INSERT INTO console_stream_closes (
                    stream_id, tenant_id, code, gap_required, closed_at
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (stream_id) DO NOTHING
                """,
                (lease.stream_id, lease.grant.tenant_id, code, gap_required, now),
            )


def _authority_connection(
    dsn: str,
) -> psycopg.Connection[dict[str, object]]:
    connection = psycopg.connect(dsn, row_factory=dict_row)
    connection.execute("SET ROLE ctower_svc")
    return connection


def _allowance_lock(
    connection: psycopg.Connection[dict[str, object]], tenant_id: UUID, allowance_id: UUID
) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"console-allowance:{tenant_id}:{allowance_id}",),
    )


def _grant_facts(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    allowance_id: UUID,
    observation: ConsoleBackendObservation,
    *,
    now: datetime,
    record_observation: bool,
) -> ConsoleGrantFacts | RecordProblem:
    row = _grant_facts_row(connection, actor, allowance_id, now=now)
    if row is not None and record_observation:
        _record_observation(
            connection,
            allowance_id,
            actor.tenant_id,
            observation,
            "matched"
            if _observation_refusal(_ref_from_row(row), observation) is None
            else "fenced",
            now,
        )
    if row is None:
        return _problem("console-session-unavailable", "The console session is unavailable.", 404)
    ref = _ref_from_row(row)
    return ConsoleGrantFacts(
        actor=actor,
        allowance_id=allowance_id,
        session_ref=ref,
        allowlist_active=bool(row["allowlist_active"]),
        assignment_current=bool(row["assignment_current"]),
        session_join_current=bool(row["session_join_current"]),
        adapter_registered=True,
        global_kill_switch_enabled=bool(row["global_enabled"]),
        sensitivity_class=str(row["sensitivity_class"]),
        loop_kind=str(row["loop_kind"]),
        observed_project_key=observation.project_key,
        observed_runtime_attempt_id=observation.runtime_attempt_id,
        observed_runner_id=observation.runner_id,
        observed_runner_epoch=observation.runner_epoch,
        observed_backend_ref=observation.opaque_backend_ref,
        observed_backend_incarnation=observation.backend_incarnation,
        session_revoked=not bool(row["allowlist_active"]),
        suspended_until=cast(datetime | None, row["suspended_until"]),
    )


def _previous_grant(
    connection: psycopg.Connection[dict[str, object]], actor: Actor, allowance_id: UUID
) -> ConsoleViewGrant | None:
    row = _previous_grant_row(connection, actor, allowance_id)
    return None if row is None else _grant_from_row(row)


def _session_join_row(
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


def _insert_allowance(
    connection: psycopg.Connection[dict[str, object]],
    allowance_id: UUID,
    actor: Actor,
    command: ConsoleSessionAllowCommand,
    *,
    now: datetime,
) -> RecordProblem | None:
    ref = command.session_ref
    try:
        connection.execute(
            """
            INSERT INTO console_session_allows (
                allowance_id, tenant_id, project_key, seat_principal_id, crew_name,
                assignment_ticket_id, assignment_kind, assignment_interval_sequence,
                recorded_work_session_id, runtime_attempt_id, runner_id, runner_epoch,
                adapter_key, opaque_backend_ref, backend_incarnation,
                sensitivity_class, loop_kind, allowed_by, allowed_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                allowance_id,
                ref.tenant_id,
                ref.project_key,
                ref.seat_principal_id,
                ref.crew_name,
                ref.assignment_ticket_id,
                ref.assignment_kind,
                ref.assignment_interval_sequence,
                ref.recorded_work_session_id,
                ref.runtime_attempt_id,
                ref.runner_id,
                ref.runner_epoch,
                ref.adapter_key,
                ref.opaque_backend_ref,
                ref.backend_incarnation,
                command.sensitivity_class,
                command.loop_kind,
                actor.principal_id,
                now,
            ),
        )
    except psycopg.errors.UniqueViolation:
        return _problem(
            "console-session-already-allowed",
            "The recorded work session already has its one allowlist fact.",
            409,
        )
    return None


def _record_observation(
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


def _ref_from_row(row: dict[str, object]) -> ConsoleSessionRef:
    return ConsoleSessionRef(
        tenant_id=cast(UUID, row["tenant_id"]),
        project_key=str(row["project_key"]),
        seat_principal_id=cast(UUID, row["seat_principal_id"]),
        crew_name=str(row["crew_name"]),
        assignment_ticket_id=cast(UUID, row["assignment_ticket_id"]),
        assignment_kind=str(row["assignment_kind"]),
        assignment_interval_sequence=cast(int, row["assignment_interval_sequence"]),
        recorded_work_session_id=cast(UUID, row["recorded_work_session_id"]),
        runtime_attempt_id=cast(UUID, row["runtime_attempt_id"]),
        runner_id=str(row["runner_id"]),
        runner_epoch=cast(int, row["runner_epoch"]),
        adapter_key=str(row["adapter_key"]),
        opaque_backend_ref=str(row["opaque_backend_ref"]),
        backend_incarnation=str(row["backend_incarnation"]),
    )


def _allowance_from_row(row: dict[str, object]) -> ConsoleSessionAllowance:
    return ConsoleSessionAllowance(
        allowance_id=cast(UUID, row["allowance_id"]),
        tenant_id=cast(UUID, row["tenant_id"]),
        project_key=str(row["project_key"]),
        recorded_work_session_id=cast(UUID, row["recorded_work_session_id"]),
        crew_name=str(row["crew_name"]),
        allowed_at=cast(datetime, row["allowed_at"]),
    )


def _grant_from_row(row: dict[str, object]) -> ConsoleViewGrant:
    return ConsoleViewGrant(
        grant_id=cast(UUID, row["grant_id"]),
        nonce=cast(UUID, row["nonce"]),
        actor_principal_id=cast(UUID, row["actor_principal_id"]),
        human_binding_id=cast(UUID, row["human_binding_id"]),
        human_session_id=cast(UUID, row["human_session_id"]),
        tenant_id=cast(UUID, row["tenant_id"]),
        project_key=str(row["project_key"]),
        allowance_id=cast(UUID, row["allowance_id"]),
        session_ref=_ref_from_row(row),
        policy_revision=str(row["policy_revision"]),
        issuer="ctower-control-plane",
        not_before=cast(datetime, row["not_before"]),
        expires_at=cast(datetime, row["expires_at"]),
        maximum_uses=1,
        continuous_view_started_at=cast(datetime, row["continuous_view_started_at"]),
        renewed_from_grant_id=cast(UUID | None, row["renewed_from_grant_id"]),
    )


def _problem(code: str, detail: str, status: int = 403) -> RecordProblem:
    return RecordProblem(code=code, detail=detail, status=status, title="Console operation refused")
