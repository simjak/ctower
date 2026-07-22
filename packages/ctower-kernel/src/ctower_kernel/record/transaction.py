"""Lower Record Interface for canonical command and event commits."""

from __future__ import annotations

import hashlib
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
        """Serialize subject heads before aggregate locks and refuse unacknowledged heads.

        The global order is sorted absent-head advisory locks, sorted existing
        ``durability_subject_heads`` row locks, then caller-owned aggregate locks. The
        transaction retains every lock through refusal or committed head movement.
        """

        if self._mode != "cutover_rpo0":
            return None
        ordered = self._ordered_subjects(subjects)
        self._lock_absent_subject_identities(tenant_id, ordered)
        pending = [
            (subject_kind, subject_id)
            for subject_kind, subject_id in ordered
            if self._lock_subject_head(tenant_id, subject_kind, subject_id)
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
        topic: str = "record.events",
    ) -> None:
        """Append one event, exact result, and outbox row in the caller's transaction."""

        ordered_subjects = self._ordered_subjects(subjects)
        append_event(self._connection, event, subjects=ordered_subjects)
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
        enqueue_event(self._connection, outbox_id, event, telemetry, now, topic=topic)
        self._move_subject_heads(event, ordered_subjects, now=now)

    def commit_control(
        self,
        event: EventEnvelope,
        *,
        outbox_id: UUID,
        response_body: dict[str, object],
        status_code: int,
        now: datetime,
        topic: str,
        job_id: UUID | None = None,
    ) -> None:
        """Append a trusted control-plane event without exporting Telemetry upward."""

        trace = hashlib.sha256(event.client_command_id.bytes + b"trace").hexdigest()
        telemetry = TelemetryContext(
            schema="ctower.telemetry-context/v1",
            trace_id=trace[:32],
            span_id=trace[32:48],
            trace_flags=1,
            correlation_id=str(event.correlation_id),
            causation_id=str(event.client_command_id),
            tenant_id=str(event.tenant_id),
            actor_id=str(event.actor_principal_id),
            command_id=str(event.client_command_id),
            job_id=str(job_id) if job_id is not None else None,
        )
        self.commit(
            event,
            outbox_id=outbox_id,
            response_body=response_body,
            status_code=status_code,
            telemetry=telemetry,
            now=now,
            topic=topic,
        )

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

    @staticmethod
    def _ordered_subjects(subjects: tuple[EventSubject, ...]) -> tuple[EventSubject, ...]:
        return tuple(sorted(set(subjects), key=lambda item: (item[0], item[1].int)))

    def _lock_absent_subject_identities(
        self, tenant_id: UUID, subjects: tuple[EventSubject, ...]
    ) -> None:
        for subject_kind, subject_id in subjects:
            exists = self._connection.execute(
                """
                SELECT 1 FROM durability_subject_heads
                WHERE tenant_id = %s AND subject_kind = %s AND subject_id = %s
                """,
                (tenant_id, subject_kind, subject_id),
            ).fetchone()
            if exists is not None:
                continue
            identity = f"{tenant_id}:{subject_kind}:{subject_id}"
            self._connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (identity,),
            )

    def _lock_subject_head(self, tenant_id: UUID, subject_kind: str, subject_id: UUID) -> bool:
        row = self._connection.execute(
            """
            SELECT acknowledgement.acceptance_position
            FROM durability_subject_heads AS head
            LEFT JOIN durability_acknowledgements AS acknowledgement
              ON acknowledgement.tenant_id = head.tenant_id
             AND acknowledgement.principal_id = head.principal_id
             AND acknowledgement.client_command_id = head.client_command_id
            WHERE head.tenant_id = %s AND head.subject_kind = %s AND head.subject_id = %s
            FOR UPDATE OF head
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
