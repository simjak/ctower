"""Record-owned append and exact replay for recorded work-session facts."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record._lifecycle import TERMINAL_TICKET_STATES
from ctower_kernel.record._uuid import uuid7 as _uuid7
from ctower_kernel.record.events import EventEnvelope, EventKind, EventOrigin
from ctower_kernel.record.prohibited_data import prohibited_data_refusal
from ctower_kernel.record.session_events import (
    INITIAL_SESSION_STATE,
    SessionClosedPayload,
    SessionEventPayload,
    SessionStartedPayload,
    SessionState,
    SessionTransitionedPayload,
    session_transition_allowed,
)
from ctower_kernel.record.sessions import (
    SessionCloseCommand,
    SessionFactCommand,
    SessionReceipt,
    SessionStartCommand,
    SessionTransitionCommand,
    session_authored_text,
)
from ctower_kernel.record.transaction import RecordTransaction, authority_connection
from ctower_kernel.telemetry import TelemetryContext

__all__: tuple[str, ...] = ()
_ZERO_HASH = bytes(32)


def start_session(
    dsn: str,
    actor: Actor,
    command: SessionStartCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> SessionReceipt | RecordProblem:
    """Reserve, refuse prohibited content, then append one session start fact."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        reserved = _reserve(transaction, actor, command, request_digest, now=now)
        if reserved is not None:
            return reserved
        ticket = _ticket_scope(connection, actor, command.ticket_id)
        if ticket is None:
            return _refuse(
                transaction,
                actor,
                command.client_command_id,
                request_digest,
                _problem(
                    command.client_command_id,
                    "tenant-scope-denied",
                    404,
                    "Ticket unavailable",
                ),
                now,
            )
        if str(ticket["state"]) in TERMINAL_TICKET_STATES:
            return _refuse(
                transaction,
                actor,
                command.client_command_id,
                request_digest,
                _problem(
                    command.client_command_id,
                    "session-ineligible",
                    409,
                    "Terminal ticket cannot start a work session",
                ),
                now,
            )
        return _append_start(
            connection,
            transaction,
            actor,
            command,
            project_key=str(ticket["project_key"]),
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def record_session_fact(
    dsn: str,
    actor: Actor,
    command: SessionFactCommand,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> SessionReceipt | RecordProblem:
    """Append one transition or closure to an existing live session."""

    with authority_connection(dsn) as connection:
        connection.execute("SET ROLE ctower_svc")
        transaction = RecordTransaction(connection)
        reserved = _reserve(transaction, actor, command, request_digest, now=now)
        if reserved is not None:
            return reserved
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"work-session:{actor.tenant_id}:{command.session_id}",),
        )
        session = _live_session(connection, actor, command)
        if isinstance(session, RecordProblem):
            return _refuse(
                transaction, actor, command.client_command_id, request_digest, session, now
            )
        state = SessionState(str(session["state"]))
        if isinstance(command, SessionTransitionCommand) and not session_transition_allowed(
            state, command.to_state
        ):
            return _refuse(
                transaction,
                actor,
                command.client_command_id,
                request_digest,
                _problem(
                    command.client_command_id,
                    "session-transition-invalid",
                    409,
                    f"A {state.value} session cannot move to {command.to_state.value}",
                ),
                now,
            )
        return _append_fact(
            connection,
            transaction,
            actor,
            command,
            session,
            state,
            request_digest=request_digest,
            now=now,
            telemetry=telemetry,
        )


def _reserve(
    transaction: RecordTransaction,
    actor: Actor,
    command: SessionStartCommand | SessionFactCommand,
    request_digest: bytes,
    *,
    now: datetime,
) -> SessionReceipt | RecordProblem | None:
    """Reserve the command key, replay exactly, then refuse prohibited content."""

    existing = transaction.reserve_ticket_mutation(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        (command.ticket_id,),
        now=now,
    )
    if isinstance(existing, RecordProblem):
        return existing
    if existing is not None:
        return _receipt_from_payload(existing)
    # Before any session row, event, or outbox byte: a prohibited class must not reach
    # the Record under a seat, crew, branch, worktree, reason, or evidence field.
    prohibited = prohibited_data_refusal(
        session_authored_text(command), command_id=command.client_command_id
    )
    if prohibited is not None:
        transaction.refuse(
            actor.tenant_id,
            actor.principal_id,
            command.client_command_id,
            request_digest,
            prohibited,
            now=now,
        )
        return prohibited
    return transaction.require_durable_subjects(
        actor.tenant_id,
        actor.principal_id,
        command.client_command_id,
        request_digest,
        (("ticket", command.ticket_id),),
        now=now,
    )


def _ticket_scope(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    ticket_id: UUID,
) -> dict[str, object] | None:
    return connection.execute(
        """
        SELECT ticket.project_key, episode.state
        FROM tickets AS ticket
        JOIN lifecycle_episodes AS episode
          ON episode.ticket_id = ticket.ticket_id
         AND episode.episode_number = ticket.current_episode
        WHERE ticket.tenant_id = %s AND ticket.ticket_id = %s
        """,
        (actor.tenant_id, ticket_id),
    ).fetchone()


def _live_session(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: SessionFactCommand,
) -> dict[str, object] | RecordProblem:
    row = connection.execute(
        """
        SELECT session.session_id,
            COALESCE(
                (
                    SELECT transition.to_state
                    FROM ticket_work_session_transitions AS transition
                    WHERE transition.session_id = session.session_id
                    ORDER BY transition.transition_number DESC
                    LIMIT 1
                ),
                %s
            ) AS state,
            (
                SELECT count(*) FROM ticket_work_session_transitions AS transition
                WHERE transition.session_id = session.session_id
            ) AS transitions,
            session.started_at,
            EXISTS (
                SELECT 1 FROM ticket_work_session_closures AS closure
                WHERE closure.session_id = session.session_id
            ) AS closed
        FROM ticket_work_sessions AS session
        WHERE session.tenant_id = %s AND session.session_id = %s AND session.ticket_id = %s
        """,
        (INITIAL_SESSION_STATE.value, actor.tenant_id, command.session_id, command.ticket_id),
    ).fetchone()
    if row is None:
        return _problem(
            command.client_command_id, "session-not-found", 404, "Work session unavailable"
        )
    if bool(row["closed"]):
        return _problem(
            command.client_command_id,
            "session-ineligible",
            409,
            "A closed work session accepts no further fact",
        )
    return row


def _append_start(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: SessionStartCommand,
    *,
    project_key: str,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> SessionReceipt:
    session_id, event_id, outbox_id = (_uuid7(now) for _ in range(3))
    _insert_session(
        connection,
        actor,
        command,
        project_key=project_key,
        session_id=session_id,
        event_id=event_id,
        now=now,
    )
    payload = SessionStartedPayload(
        branch_ref=command.branch_ref,
        crew_name=command.crew_name,
        harness_ref=command.harness_ref,
        model_ref=command.model_ref,
        seat_key=command.seat_key,
        session_id=session_id,
        ticket_id=command.ticket_id,
        worktree_ref=command.worktree_ref,
    )
    result = SessionReceipt(
        command_id=command.client_command_id,
        event_id=event_id,
        session_id=session_id,
        state=INITIAL_SESSION_STATE,
        ticket_id=command.ticket_id,
    )
    _commit(
        transaction,
        actor,
        command.client_command_id,
        command.ticket_id,
        result,
        _event(
            actor,
            command.client_command_id,
            EventKind.SESSION_STARTED,
            payload,
            session_id=session_id,
            event_id=event_id,
            prev_hash=_ZERO_HASH,
            sequence=1,
            request_digest=request_digest,
            telemetry=telemetry,
            now=now,
        ),
        outbox_id=outbox_id,
        telemetry=telemetry,
        now=now,
    )
    return result


def _insert_session(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: SessionStartCommand,
    *,
    project_key: str,
    session_id: UUID,
    event_id: UUID,
    now: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO ticket_work_sessions (
            session_id, tenant_id, ticket_id, project_key, seat_key, crew_name, model_ref,
            harness_ref, worktree_ref, branch_ref, started_by, started_at, event_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            session_id,
            actor.tenant_id,
            command.ticket_id,
            project_key,
            command.seat_key,
            command.crew_name,
            command.model_ref,
            command.harness_ref,
            command.worktree_ref,
            command.branch_ref,
            actor.principal_id,
            now,
            event_id,
        ),
    )


def _append_fact(
    connection: psycopg.Connection[dict[str, object]],
    transaction: RecordTransaction,
    actor: Actor,
    command: SessionFactCommand,
    session: dict[str, object],
    state: SessionState,
    *,
    request_digest: bytes,
    now: datetime,
    telemetry: TelemetryContext,
) -> SessionReceipt:
    previous = connection.execute(
        """
        SELECT event_hash, sequence
        FROM events
        WHERE tenant_id = %s AND stream_id = %s
        ORDER BY sequence DESC LIMIT 1
        """,
        (actor.tenant_id, f"session:{command.session_id}"),
    ).fetchone()
    if previous is None:
        raise RuntimeError("recorded work session has no committed event stream")
    event_id, outbox_id = (_uuid7(now) for _ in range(2))
    if isinstance(command, SessionTransitionCommand):
        kind, payload, next_state = _insert_transition(
            connection, actor, command, session, state, event_id=event_id, now=now
        )
    else:
        kind, payload, next_state = _insert_closure(
            connection, actor, command, session, state, event_id=event_id, now=now
        )
    result = SessionReceipt(
        command_id=command.client_command_id,
        event_id=event_id,
        session_id=command.session_id,
        state=next_state,
        ticket_id=command.ticket_id,
    )
    _commit(
        transaction,
        actor,
        command.client_command_id,
        command.ticket_id,
        result,
        _event(
            actor,
            command.client_command_id,
            kind,
            payload,
            session_id=command.session_id,
            event_id=event_id,
            prev_hash=bytes(cast(bytes, previous["event_hash"])),
            sequence=int(cast(int, previous["sequence"])) + 1,
            request_digest=request_digest,
            telemetry=telemetry,
            now=now,
        ),
        outbox_id=outbox_id,
        telemetry=telemetry,
        now=now,
    )
    return result


def _insert_transition(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: SessionTransitionCommand,
    session: dict[str, object],
    state: SessionState,
    *,
    event_id: UUID,
    now: datetime,
) -> tuple[EventKind, SessionEventPayload, SessionState]:
    """Append one authored state move; the number is the Record's own count, not a claim."""

    transition_number = int(cast(int, session["transitions"])) + 1
    connection.execute(
        """
        INSERT INTO ticket_work_session_transitions (
            session_id, tenant_id, transition_number, from_state, to_state, reason,
            occurred_at, event_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            command.session_id,
            actor.tenant_id,
            transition_number,
            state.value,
            command.to_state.value,
            command.reason,
            now,
            event_id,
        ),
    )
    payload = SessionTransitionedPayload(
        from_state=state.value,
        reason=command.reason,
        session_id=command.session_id,
        ticket_id=command.ticket_id,
        to_state=command.to_state.value,
        transition_number=transition_number,
    )
    return EventKind.SESSION_TRANSITIONED, payload, command.to_state


def _insert_closure(
    connection: psycopg.Connection[dict[str, object]],
    actor: Actor,
    command: SessionCloseCommand,
    session: dict[str, object],
    state: SessionState,
    *,
    event_id: UUID,
    now: datetime,
) -> tuple[EventKind, SessionEventPayload, SessionState]:
    """Append the terminal fact, pricing the session from committed Record timestamps."""

    duration = _duration_seconds(cast(datetime, session["started_at"]), now)
    connection.execute(
        """
        INSERT INTO ticket_work_session_closures (
            session_id, tenant_id, outcome, duration_seconds, input_tokens,
            output_tokens, evidence_ref, closed_at, event_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            command.session_id,
            actor.tenant_id,
            command.outcome.value,
            duration,
            command.input_tokens,
            command.output_tokens,
            command.evidence_ref,
            now,
            event_id,
        ),
    )
    payload = SessionClosedPayload(
        duration_seconds=duration,
        evidence_ref=command.evidence_ref,
        input_tokens=command.input_tokens,
        outcome=command.outcome.value,
        output_tokens=command.output_tokens,
        session_id=command.session_id,
        ticket_id=command.ticket_id,
    )
    return EventKind.SESSION_CLOSED, payload, state


def _duration_seconds(started_at: datetime, now: datetime) -> int:
    """Record-owned duration: never a caller claim, never negative."""

    return max(int((now - started_at).total_seconds()), 0)


def _event(
    actor: Actor,
    command_id: UUID,
    kind: EventKind,
    payload: SessionEventPayload,
    *,
    session_id: UUID,
    event_id: UUID,
    prev_hash: bytes,
    sequence: int,
    request_digest: bytes,
    telemetry: TelemetryContext,
    now: datetime,
) -> EventEnvelope:
    return EventEnvelope(
        actor_principal_id=actor.principal_id,
        aggregate_id=session_id,
        causation_id=None,
        client_command_id=command_id,
        correlation_id=telemetry.correlation_uuid(command_id),
        event_id=event_id,
        kind=kind,
        origin=EventOrigin.API,
        payload=payload,
        prev_hash=prev_hash,
        request_sha256=request_digest,
        sequence=sequence,
        server_time=now,
        stream_id=f"session:{session_id}",
        tenant_id=actor.tenant_id,
    )


def _commit(
    transaction: RecordTransaction,
    actor: Actor,
    command_id: UUID,
    ticket_id: UUID,
    result: SessionReceipt,
    event: EventEnvelope,
    *,
    outbox_id: UUID,
    telemetry: TelemetryContext,
    now: datetime,
) -> None:
    transaction.commit(
        event,
        outbox_id=outbox_id,
        response_body=result.response_payload(),
        status_code=200,
        telemetry=telemetry.bind(
            tenant_id=str(actor.tenant_id),
            actor_id=str(actor.principal_id),
            command_id=str(command_id),
            ticket_id=str(ticket_id),
        ),
        now=now,
        subjects=(("ticket", ticket_id),),
    )


def _receipt_from_payload(payload: dict[str, object]) -> SessionReceipt:
    return SessionReceipt(
        command_id=UUID(str(payload["command_id"])),
        event_id=UUID(str(payload["event_id"])),
        session_id=UUID(str(payload["session_id"])),
        state=SessionState(str(payload["state"])),
        ticket_id=UUID(str(payload["ticket_id"])),
    )


def _refuse(
    transaction: RecordTransaction,
    actor: Actor,
    command_id: UUID,
    request_digest: bytes,
    problem: RecordProblem,
    now: datetime,
) -> RecordProblem:
    transaction.refuse(
        actor.tenant_id,
        actor.principal_id,
        command_id,
        request_digest,
        problem,
        now=now,
    )
    return problem


def _problem(command_id: UUID, code: str, status: int, title: str) -> RecordProblem:
    return RecordProblem(
        code=code,
        detail=title,
        status=status,
        title=title,
        command_id=command_id,
    )
