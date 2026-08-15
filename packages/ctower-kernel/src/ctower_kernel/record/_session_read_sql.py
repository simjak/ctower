"""Project-scoped reads that fold recorded work sessions from their own facts."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from ctower_kernel.record import Actor, RecordProblem
from ctower_kernel.record.session_events import (
    INITIAL_SESSION_STATE,
    SessionOutcome,
    SessionState,
)
from ctower_kernel.record.sessions import (
    ProjectSessionPage,
    SessionTokenUsage,
    TicketSessionList,
    WorkSession,
)
from ctower_kernel.record.transaction import project_scope_refusal

__all__: tuple[str, ...] = ()
MAX_PAGE_SIZE = 100

_SELECT_SESSIONS = """
SELECT
    work_session.session_id, work_session.ticket_id, work_session.project_key,
    work_session.seat_key, work_session.crew_name, work_session.model_ref,
    work_session.harness_ref, work_session.worktree_ref, work_session.branch_ref,
    work_session.started_at,
    COALESCE(
        (
            SELECT transition.to_state
            FROM ticket_work_session_transitions AS transition
            WHERE transition.session_id = work_session.session_id
            ORDER BY transition.transition_number DESC
            LIMIT 1
        ),
        %s
    ) AS state,
    (
        SELECT count(*) FROM ticket_work_session_transitions AS transition
        WHERE transition.session_id = work_session.session_id
    ) AS transition_count,
    closure.outcome, closure.duration_seconds, closure.input_tokens,
    closure.output_tokens, closure.evidence_ref, closure.closed_at,
    event.record_position
FROM ticket_work_sessions AS work_session
JOIN events AS event
  ON event.event_id = work_session.event_id AND event.tenant_id = work_session.tenant_id
LEFT JOIN ticket_work_session_closures AS closure
  ON closure.session_id = work_session.session_id
 AND closure.tenant_id = work_session.tenant_id
"""


def ticket_sessions(
    dsn: str,
    actor: Actor,
    ticket_id: UUID,
    project_key: str,
) -> TicketSessionList | RecordProblem:
    """Read one ticket's ordered sessions through the no-disclosure project predicate."""

    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        refusal = project_scope_refusal(
            connection,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            project_keys=(project_key,),
        )
        if refusal is not None:
            return refusal
        exists = connection.execute(
            """
            SELECT 1 FROM tickets
            WHERE tenant_id = %s AND ticket_id = %s AND project_key = %s
            """,
            (actor.tenant_id, ticket_id, project_key),
        ).fetchone()
        if exists is None:
            return RecordProblem(
                "tenant-scope-denied", "Ticket unavailable", 404, "Ticket unavailable"
            )
        rows = connection.execute(
            f"""
            {_SELECT_SESSIONS}
            WHERE work_session.tenant_id = %s AND work_session.ticket_id = %s
              AND work_session.project_key = %s
            ORDER BY event.record_position
            """,
            (INITIAL_SESSION_STATE.value, actor.tenant_id, ticket_id, project_key),
        ).fetchall()
    return TicketSessionList(ticket_id=ticket_id, sessions=tuple(_session(row) for row in rows))


def project_sessions(
    dsn: str,
    actor: Actor,
    project_key: str,
    *,
    cursor: int,
    limit: int,
) -> ProjectSessionPage | RecordProblem:
    """Read one project's sessions as a record-position cursor page."""

    if cursor < 0 or limit < 1 or limit > MAX_PAGE_SIZE:
        return RecordProblem(
            "validation-error",
            "Invalid session page cursor",
            422,
            "Invalid session page cursor",
        )
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET ROLE ctower_svc")
        refusal = project_scope_refusal(
            connection,
            tenant_id=actor.tenant_id,
            principal_id=actor.principal_id,
            project_keys=(project_key,),
        )
        if refusal is not None:
            return refusal
        rows = connection.execute(
            f"""
            {_SELECT_SESSIONS}
            WHERE work_session.tenant_id = %s AND work_session.project_key = %s
              AND event.record_position > %s
            ORDER BY event.record_position
            LIMIT %s
            """,
            (INITIAL_SESSION_STATE.value, actor.tenant_id, project_key, cursor, limit + 1),
        ).fetchall()
    page_rows = rows[:limit]
    sessions = tuple(_session(row) for row in page_rows)
    next_cursor = (
        int(cast(int, page_rows[-1]["record_position"])) if len(rows) > limit and sessions else None
    )
    return ProjectSessionPage(
        project_key=project_key,
        sessions=sessions,
        next_cursor=next_cursor,
    )


def _session(row: dict[str, object]) -> WorkSession:
    outcome = row["outcome"]
    tokens = (
        None
        if outcome is None
        else SessionTokenUsage(
            input_tokens=int(cast(int, row["input_tokens"])),
            output_tokens=int(cast(int, row["output_tokens"])),
        )
    )
    return WorkSession(
        branch_ref=str(row["branch_ref"]),
        closed_at=cast(datetime | None, row["closed_at"]),
        crew_name=str(row["crew_name"]),
        duration_seconds=(None if outcome is None else int(cast(int, row["duration_seconds"]))),
        evidence_ref=None if row["evidence_ref"] is None else str(row["evidence_ref"]),
        harness_ref=str(row["harness_ref"]),
        model_ref=str(row["model_ref"]),
        outcome=None if outcome is None else SessionOutcome(str(outcome)),
        project_key=str(row["project_key"]),
        seat_key=str(row["seat_key"]),
        session_id=cast(UUID, row["session_id"]),
        started_at=cast(datetime, row["started_at"]),
        state=SessionState(str(row["state"])),
        ticket_id=cast(UUID, row["ticket_id"]),
        tokens=tokens,
        transition_count=int(cast(int, row["transition_count"])),
        worktree_ref=str(row["worktree_ref"]),
    )
