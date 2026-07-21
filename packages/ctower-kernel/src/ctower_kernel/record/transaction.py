"""Lower Record Interface for canonical command and event commits."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from threading import Timer
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ctower_kernel.record import RecordProblem
from ctower_kernel.record._commands import reserve_command
from ctower_kernel.record._event_store import EventSubject, append_event, enqueue_event
from ctower_kernel.record.events import EventEnvelope
from ctower_kernel.telemetry import TelemetryContext

__all__ = ["RecordTransaction", "authority_connection", "recover_ambiguous_commit"]

_CONNECT_TIMEOUT_SECONDS = 2


class _AuthorityConnection(psycopg.Connection[dict[str, object]]):
    """Connection whose remote-apply commit wait has a cancellation watchdog."""

    _commit_deadline_seconds: float | None = None

    def arm_commit_deadline(self, milliseconds: int) -> None:
        self._commit_deadline_seconds = milliseconds / 1000

    def commit(self) -> None:
        deadline = self._commit_deadline_seconds
        self._commit_deadline_seconds = None
        if deadline is None:
            super().commit()
            return
        watchdog = Timer(deadline, self._cancel_commit_wait)
        watchdog.daemon = True
        watchdog.start()
        try:
            super().commit()
        finally:
            watchdog.cancel()

    def _cancel_commit_wait(self) -> None:
        with suppress(psycopg.Error):
            self.cancel_safe(timeout=_CONNECT_TIMEOUT_SECONDS)


def authority_connection(dsn: str) -> psycopg.Connection[dict[str, object]]:
    """Open the only connection type allowed to issue bounded authority commits."""

    return cast(
        psycopg.Connection[dict[str, object]],
        _AuthorityConnection.connect(
            dsn,
            connect_timeout=_CONNECT_TIMEOUT_SECONDS,
            row_factory=dict_row,
        ),
    )


def arm_remote_apply_deadline(
    connection: psycopg.Connection[dict[str, object]], milliseconds: int
) -> None:
    """Arm the connection watchdog before a remote-apply transaction commits."""

    if not isinstance(connection, _AuthorityConnection):
        raise TypeError("remote-apply authority requires a deadline-capable connection")
    connection.arm_commit_deadline(milliseconds)


def recover_ambiguous_commit[Outcome](operation: Callable[[], Outcome]) -> Outcome:
    """Discard the failed connection and replay once through command idempotency authority."""

    try:
        return operation()
    except (psycopg.errors.QueryCanceled, psycopg.OperationalError):
        return operation()


class RecordTransaction:
    """Keep idempotency ordering and canonical append choreography Record-owned."""

    def __init__(self, connection: psycopg.Connection[dict[str, object]]) -> None:
        self._connection = connection
        self._mode: str | None = None

    def reserve(
        self,
        principal_id: UUID,
        command_id: UUID,
        request_digest: bytes,
    ) -> dict[str, object] | RecordProblem | None:
        """Reserve a principal command key before any aggregate read."""

        self._configure_authority_commit()
        return reserve_command(self._connection, principal_id, command_id, request_digest)

    def require_durable_subjects(
        self,
        tenant_id: UUID,
        principal_id: UUID,
        command_id: UUID,
        request_digest: bytes,
        subjects: tuple[EventSubject, ...],
        *,
        now: datetime,
    ) -> RecordProblem | None:
        """Refuse dependency on a locally committed but unacknowledged subject head."""

        if self._mode != "cutover_rpo0":
            return None
        pending = [
            (subject_kind, subject_id)
            for subject_kind, subject_id in subjects
            if self._subject_is_pending(tenant_id, subject_kind, subject_id)
        ]
        if not pending:
            return None
        problem = RecordProblem(
            code="durability_pending",
            detail="A required subject head is not acknowledged on the named standby.",
            status=409,
            title="Subject durability pending",
            command_id=command_id,
            unmet_facts=tuple(f"{kind}:{subject_id}" for kind, subject_id in pending),
        )
        self.refuse(
            tenant_id,
            principal_id,
            command_id,
            request_digest,
            problem,
            now=now,
        )
        return problem

    def commit(
        self,
        event: EventEnvelope,
        *,
        outbox_id: UUID,
        response_body: dict[str, object],
        status_code: int,
        telemetry: TelemetryContext,
        now: datetime,
        subjects: tuple[EventSubject, ...] = (),
    ) -> None:
        """Append one event, exact result, and outbox row in the caller's transaction."""

        append_event(self._connection, event, subjects=subjects)
        self._connection.execute(
            """
            INSERT INTO command_results (
                tenant_id, principal_id, client_command_id, request_sha256, status_code,
                response_body, event_ids, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.tenant_id,
                event.actor_principal_id,
                event.client_command_id,
                event.request_sha256,
                status_code,
                Jsonb(response_body),
                [event.event_id],
                now,
            ),
        )
        enqueue_event(self._connection, outbox_id, event, telemetry, now)
        self._move_subject_heads(event, subjects, now=now)

    def refuse(
        self,
        tenant_id: UUID,
        principal_id: UUID,
        command_id: UUID,
        request_digest: bytes,
        problem: RecordProblem,
        *,
        now: datetime,
    ) -> None:
        """Persist one exact typed refusal without an event or authoritative mutation."""

        self._connection.execute(
            """
            INSERT INTO command_results (
                tenant_id, principal_id, client_command_id, request_sha256, status_code,
                response_body, event_ids, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tenant_id,
                principal_id,
                command_id,
                request_digest,
                problem.status,
                Jsonb(problem.response_payload()),
                [],
                now,
            ),
        )

    def _configure_authority_commit(self) -> None:
        policy = self._connection.execute(
            """
            SELECT mode, commit_deadline_ms
            FROM durability_policy_state WHERE singleton
            """
        ).fetchone()
        if policy is None:
            raise RuntimeError("durability policy is unavailable")
        self._mode = str(policy["mode"])
        if self._mode != "cutover_rpo0":
            return
        self._connection.execute("SELECT set_config('synchronous_commit', 'remote_apply', true)")
        self._connection.execute(
            "SELECT set_config('statement_timeout', %s, true)",
            (f"{int(cast(int, policy['commit_deadline_ms']))}ms",),
        )
        arm_remote_apply_deadline(self._connection, int(cast(int, policy["commit_deadline_ms"])))

    def _subject_is_pending(self, tenant_id: UUID, subject_kind: str, subject_id: UUID) -> bool:
        row = self._connection.execute(
            """
            SELECT acknowledgement.acceptance_position
            FROM durability_subject_heads AS head
            LEFT JOIN durability_acknowledgements AS acknowledgement
              ON acknowledgement.tenant_id = head.tenant_id
             AND acknowledgement.principal_id = head.principal_id
             AND acknowledgement.client_command_id = head.client_command_id
            WHERE head.tenant_id = %s AND head.subject_kind = %s AND head.subject_id = %s
            """,
            (tenant_id, subject_kind, subject_id),
        ).fetchone()
        return row is not None and row["acceptance_position"] is None

    def _move_subject_heads(
        self, event: EventEnvelope, subjects: tuple[EventSubject, ...], *, now: datetime
    ) -> None:
        if not subjects:
            return
        self._connection.cursor().executemany(
            """
            INSERT INTO durability_subject_heads (
                tenant_id, subject_kind, subject_id, principal_id, client_command_id, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, subject_kind, subject_id) DO UPDATE
            SET principal_id = EXCLUDED.principal_id,
                client_command_id = EXCLUDED.client_command_id,
                updated_at = EXCLUDED.updated_at
            """,
            (
                (
                    event.tenant_id,
                    subject_kind,
                    subject_id,
                    event.actor_principal_id,
                    event.client_command_id,
                    now,
                )
                for subject_kind, subject_id in subjects
            ),
        )
